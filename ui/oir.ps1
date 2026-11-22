# Escucha una frase por el micrófono y la escribe. Sale 2 si Windows no tiene reconocedor.
$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Speech
$recs = @([System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers())
if (-not $recs -or $recs.Count -eq 0) {
    [Console]::Error.WriteLine("SIN_RECONOCEDOR")
    exit 2
}
$cultura = $null
foreach ($r in $recs) {
    if ($r.Culture.Name -like "es*") { $cultura = $r.Culture; break }
}
if (-not $cultura) { $cultura = $recs[0].Culture }
try {
    $motor = New-Object System.Speech.Recognition.SpeechRecognitionEngine($cultura)
    $motor.SetInputToDefaultAudioDevice()
    $motor.LoadGrammar((New-Object System.Speech.Recognition.DictationGrammar))
    $dicho = $motor.Recognize([TimeSpan]::FromSeconds(8))
    if ($dicho) { Write-Output $dicho.Text }
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 3
}
