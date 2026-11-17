"""Ronda 19 — RetinaFace (biubug6/Pytorch_Retinaface, licencia MIT; pesos MobileNet0.25 o ResNet50) en ONNX.
Se usa como 2º detector: (a) consenso para caras NO reconocidas, (b) caras que YuNet no vio.
Por teselas de 1024 px → memoria acotada en fotos 4K."""
import numpy as np, cv2, os
from ia import acelerador
_S={}
from pathlib import Path
_DEF=str(Path(__file__).resolve().parent.parent/'models'/os.environ.get('RETINA_MODELO','retinaface_r50.onnx'))
def sesion(ruta=None, hilos=None):
    """La red, lista para correr(x). En la GPU dedicada si la hay y da lo mismo que la CPU (ia/acelerador.py); si no, en CPU."""
    ruta=ruta or _DEF
    if ruta not in _S:
        n=int(hilos or os.environ.get('RETINA_HILOS') or os.environ.get('ORT_HILOS','0') or 0)
        _S[ruta]=acelerador.Red(ruta,n,control=acelerador.CONTROL_RETINA,sin_arena=True)
    return _S[ruta]
def _priors(h,w):
    out=[]
    for step,ms in ((8,(16,32)),(16,(64,128)),(32,(256,512))):
        fh,fw=int(np.ceil(h/step)),int(np.ceil(w/step))
        jj,ii=np.meshgrid(np.arange(fw),np.arange(fh))
        cx=((jj+0.5)*step/w).ravel(); cy=((ii+0.5)*step/h).ravel()
        # orden: por celda, por min_size
        a=np.stack([np.stack([cx,cy,np.full_like(cx,m/w),np.full_like(cx,m/h)],1) for m in ms],1).reshape(-1,4)
        out.append(a)
    return np.concatenate(out)
def nms(b,s,thr):
    x1,y1,x2,y2=b[:,0],b[:,1],b[:,2],b[:,3]; ar=(x2-x1)*(y2-y1); o=s.argsort()[::-1]; keep=[]
    while o.size:
        i=o[0]; keep.append(i)
        xx1=np.maximum(x1[i],x1[o[1:]]); yy1=np.maximum(y1[i],y1[o[1:]]); xx2=np.minimum(x2[i],x2[o[1:]]); yy2=np.minimum(y2[i],y2[o[1:]])
        inter=np.clip(xx2-xx1,0,None)*np.clip(yy2-yy1,0,None); iou=inter/(ar[i]+ar[o[1:]]-inter+1e-9)
        o=o[1:][iou<=thr]
    return np.array(keep,int)
def detectar(img, escala=1.0, umbral=0.2, nms_thr=0.4, ruta=None):
    """img BGR uint8. Devuelve N×15 como YuNet: x,y,w,h, 5 landmarks (ojoD? orden retina: ojo izq, ojo der, nariz, boca izq, boca der), score."""
    s=sesion(ruta)
    im=img if escala==1.0 else cv2.resize(img,None,fx=escala,fy=escala,interpolation=cv2.INTER_LINEAR if escala>1 else cv2.INTER_AREA)
    h,w=im.shape[:2]
    x=(im.astype(np.float32)-np.array([104,117,123],np.float32)).transpose(2,0,1)[None]
    loc,conf,lm=s.correr(x)
    P=_priors(h,w); loc,conf,lm=loc[0],conf[0][:,1],lm[0]
    k=conf>umbral
    if not k.any(): return np.empty((0,15),np.float32)
    P,loc,conf,lm=P[k],loc[k],conf[k],lm[k]
    c=P[:,:2]+loc[:,:2]*0.1*P[:,2:]; wh=P[:,2:]*np.exp(loc[:,2:]*0.2)
    b=np.concatenate([c-wh/2,c+wh/2],1)*np.array([w,h,w,h])
    L=(P[:,None,:2]+lm.reshape(-1,5,2)*0.1*P[:,None,2:])*np.array([w,h])
    kk=nms(b,conf,nms_thr); b,conf,L=b[kk],conf[kk],L[kk]
    out=np.zeros((len(b),15),np.float32)
    out[:,0:2]=b[:,0:2]; out[:,2:4]=b[:,2:4]-b[:,0:2]; out[:,4:14]=L.reshape(-1,10); out[:,14]=conf
    out[:,:14]/=escala
    return out
def detectar_teselas(img, escala=1.0, lado=1024, solape=192, umbral=0.2, nms_thr=0.4, ruta=None):
    """RetinaFace por teselas de lado×lado (en la escala de trabajo) → memoria acotada en fotos 4K."""
    im=img if escala==1.0 else cv2.resize(img,None,fx=escala,fy=escala,interpolation=cv2.INTER_LINEAR if escala>1 else cv2.INTER_AREA)
    H,W=im.shape[:2]
    if max(H,W)<=lado*1.15:
        o=detectar(im,1.0,umbral,nms_thr,ruta); o[:,:14]/=escala; return o
    paso=lado-solape; outs=[]
    for y0 in range(0,max(1,H-solape),paso):
        for x0 in range(0,max(1,W-solape),paso):
            t=im[y0:y0+lado,x0:x0+lado]
            if t.shape[0]<32 or t.shape[1]<32: continue
            o=detectar(t,1.0,umbral,nms_thr,ruta)
            if len(o):
                o[:,0]+=x0; o[:,1]+=y0; o[:,4:14:2]+=x0; o[:,5:14:2]+=y0
                # descarta cajas cortadas por el borde interior de la tesela
                bx=(o[:,0]>x0+2)|(x0==0); by=(o[:,1]>y0+2)|(y0==0)
                ex=(o[:,0]+o[:,2]<x0+t.shape[1]-2)|(x0+t.shape[1]>=W); ey=(o[:,1]+o[:,3]<y0+t.shape[0]-2)|(y0+t.shape[0]>=H)
                outs.append(o[bx&by&ex&ey])
    # pasada global reducida (caras grandes que no caben enteras en una tesela)
    eg=lado/max(H,W); g=detectar(im,eg,umbral,nms_thr,ruta)
    if len(g): outs.append(g[g[:,2]>=solape*0.5])
    if not outs: return np.empty((0,15),np.float32)
    o=np.concatenate(outs); b=np.concatenate([o[:,:2],o[:,:2]+o[:,2:4]],1)
    o=o[nms(b,o[:,14],nms_thr)]; o[:,:14]/=escala
    return o
