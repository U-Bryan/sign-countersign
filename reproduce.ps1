# Windows wrapper: .\reproduce.ps1 [--mock-full | --full --budget 60]
$env:PYTHONUTF8 = "1"
& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\reproduce.py" @args
exit $LASTEXITCODE
