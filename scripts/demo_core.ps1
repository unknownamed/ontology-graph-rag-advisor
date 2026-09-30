$candidate = if ($env:CURRICULUM_PYTHON) { $env:CURRICULUM_PYTHON } else { Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' }
if (-not (Test-Path -LiteralPath $candidate)) { throw "Python not found. Set CURRICULUM_PYTHON to a Python 3.12+ executable." }
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
& $candidate (Join-Path $PSScriptRoot 'demo_core.py')
exit $LASTEXITCODE
