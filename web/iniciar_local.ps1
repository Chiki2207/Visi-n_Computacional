# Arranca la web en esta PC (cada servicio en su ventana):
#   IA    http://127.0.0.1:8001   (solo la usa el servidor web)
#   web   http://127.0.0.1:3000   (abrir este en el navegador)
# Uso, desde la raiz del proyecto:   powershell -ExecutionPolicy Bypass -File .\web\iniciar_local.ps1

$Web = $PSScriptRoot
$Raiz = Split-Path $Web -Parent

if (-not (Test-Path "$Web\.env")) {
    $token = & "$Raiz\.venv\Scripts\python.exe" -c "import secrets;print(secrets.token_urlsafe(32))"
    (Get-Content "$Web\.env.ejemplo") -replace '^IA_TOKEN=.*', "IA_TOKEN=$token" | Set-Content -Encoding utf8 "$Web\.env"
    Write-Host "[web] Se creo web\.env con una clave nueva" -ForegroundColor Yellow
}
if (-not (Test-Path "$Web\frontend\.venv\Scripts\python.exe")) {
    Write-Host "[web] Falta el entorno de la web. Crearlo una vez:" -ForegroundColor Red
    Write-Host "      python -m venv web\frontend\.venv"
    Write-Host "      web\frontend\.venv\Scripts\python.exe -m pip install -r web\frontend\requisitos.txt"
    exit 1
}
if (-not (Test-Path "$Web\usuarios.json")) {
    Write-Host "[web] Todavia no hay docentes. Crear uno:" -ForegroundColor Yellow
    Write-Host "      web\frontend\.venv\Scripts\python.exe web\frontend\gestionar.py crear-usuario --usuario profe --nombre ""Su Nombre"""
}

Start-Process -FilePath "$Raiz\.venv\Scripts\python.exe" -ArgumentList "`"$Web\ia_servicio\servicio.py`"" -WorkingDirectory $Raiz
Start-Process -FilePath "$Web\frontend\.venv\Scripts\python.exe" -ArgumentList "`"$Web\frontend\servidor.py`"" -WorkingDirectory $Raiz
Write-Host "[web] IA :8001 (tarda ~20 s en cargar modelos) y web :3000" -ForegroundColor Green
Write-Host "[web] Abrir http://localhost:3000"
