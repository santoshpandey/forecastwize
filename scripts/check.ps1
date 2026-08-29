# Runs the same checks as Makefile `check`. Use this on Windows if `make` is not installed.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
if (-not $root) { $root = Get-Location }

Set-Location $root

Write-Host "Ruff check..."
python -m ruff check backend
python -m ruff format --check backend
python -m ruff check --config backend/pyproject.toml evaluation scripts
python -m ruff format --check --config backend/pyproject.toml evaluation scripts

Write-Host "Pytest..."
Set-Location "$root\backend"
python -m pytest
Set-Location $root

Write-Host "Frontend typecheck..."
Set-Location "$root\frontend"
npm run typecheck

Write-Host "Frontend build..."
npm run build
Set-Location $root

Write-Host "All checks finished."
