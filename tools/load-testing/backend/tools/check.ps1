# Run the same quality gates as CI: lint, format check, type check, tests with coverage.
$ErrorActionPreference = "Stop"
Push-Location (Join-Path $PSScriptRoot "..")
try {
    ruff check src tests tools; if ($LASTEXITCODE) { exit $LASTEXITCODE }
    black --check src tests tools; if ($LASTEXITCODE) { exit $LASTEXITCODE }
    mypy; if ($LASTEXITCODE) { exit $LASTEXITCODE }
    pytest -q --cov=lt --cov-report=term @args; if ($LASTEXITCODE) { exit $LASTEXITCODE }
} finally {
    Pop-Location
}
