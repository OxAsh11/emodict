$wav = Join-Path $PSScriptRoot "test_input.wav"
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.SetOutputToWaveFile($wav)
$s.Rate = 0
$s.Speak("This is a test of the emotion dictation pipeline. Um, you know, it should transcribe just fine. Flyt base drone operations.")
$s.Dispose()
Write-Host "wrote $wav"
