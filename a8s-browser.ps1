$Entry = Join-Path $PSScriptRoot "src/__main__.py"

$Python = Get-Command python3 -ErrorAction SilentlyContinue
if ($Python) { & $Python.Source $Entry @args; exit $LASTEXITCODE }
$Python = Get-Command python -ErrorAction SilentlyContinue
if ($Python) { & $Python.Source $Entry @args; exit $LASTEXITCODE }
$Python = Get-Command py -ErrorAction SilentlyContinue
if ($Python) { & $Python.Source -3 $Entry @args; exit $LASTEXITCODE }

Write-Error "Could not find python3, python, or py on PATH."
exit 127
