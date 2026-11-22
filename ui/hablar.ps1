# Lee el texto por la entrada y lo dice con la voz en español de Windows.
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$voz = New-Object System.Speech.Synthesis.SpeechSynthesizer
try { $voz.SelectVoice("Microsoft Sabina Desktop") } catch {}
$texto = [Console]::In.ReadToEnd()
if ($texto) { $voz.Speak($texto) }
