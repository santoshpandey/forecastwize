@echo off
REM Windows stand-in when GNU Make is not on PATH. Run from the repo root.
REM GNU Make reads Makefile on Unix/macOS and on Windows if installed.
setlocal
set PYTHON=python
if not "%PYTHON_CMD%"=="" set PYTHON=%PYTHON_CMD%

if "%1"=="" goto help
if /I "%1"=="help" goto help
if /I "%1"=="setup" goto setup
if /I "%1"=="install" goto setup
if /I "%1"=="test" goto test
if /I "%1"=="dev" goto dev
if /I "%1"=="evaluate-baseline" goto evaluate_baseline
if /I "%1"=="evaluate-agent" goto evaluate_agent
if /I "%1"=="compare" goto compare
if /I "%1"=="check" goto check
if /I "%1"=="versions" goto versions
if /I "%1"=="docker-up" goto docker_up
if /I "%1"=="docker-down" goto docker_down
if /I "%1"=="generate-cases" goto generate_cases
echo Unknown target "%1". Try: make help
exit /b 1

:help
echo ForecastWize targets:
echo   make setup                 .env from example if missing; pip + npm ci
echo   make test                  Backend pytest + frontend typecheck
echo   make dev                   API :8000 and UI :3000 together
echo   make evaluate-baseline     Writes evaluation/results/baseline.json
echo   make evaluate-agent        Writes evaluation/results/agent.json
echo   make compare               Writes evaluation/results/comparison.json
echo   make check                 Ruff + pytest + frontend typecheck and build
exit /b 0

:setup
%PYTHON% scripts\setup.py
exit /b %ERRORLEVEL%

:test
%PYTHON% scripts\test.py
exit /b %ERRORLEVEL%

:dev
%PYTHON% scripts\dev.py
exit /b %ERRORLEVEL%

:evaluate_baseline
%PYTHON% evaluation\run_baseline.py
exit /b %ERRORLEVEL%

:evaluate_agent
%PYTHON% evaluation\run_agent.py
exit /b %ERRORLEVEL%

:compare
%PYTHON% evaluation\compare.py
exit /b %ERRORLEVEL%

:check
%PYTHON% -m ruff check backend
if errorlevel 1 exit /b %ERRORLEVEL%
%PYTHON% -m ruff format --check backend
if errorlevel 1 exit /b %ERRORLEVEL%
%PYTHON% -m ruff check --config backend\pyproject.toml evaluation scripts
if errorlevel 1 exit /b %ERRORLEVEL%
%PYTHON% -m ruff format --check --config backend\pyproject.toml evaluation scripts
if errorlevel 1 exit /b %ERRORLEVEL%
pushd backend
%PYTHON% -m pytest
if errorlevel 1 (
  popd
  exit /b %ERRORLEVEL%
)
popd
pushd frontend
call npm run typecheck
if errorlevel 1 (
  popd
  exit /b %ERRORLEVEL%
)
call npm run build
set ERR=%ERRORLEVEL%
popd
exit /b %ERR%

:versions
%PYTHON% --version
node -v
%PYTHON% -c "from importlib import metadata; print('pandas', metadata.version('pandas')); print('numpy', metadata.version('numpy')); print('scipy', metadata.version('scipy')); print('statsmodels', metadata.version('statsmodels'))"
exit /b %ERRORLEVEL%

:docker_up
docker compose up --build
exit /b %ERRORLEVEL%

:docker_down
docker compose down
exit /b %ERRORLEVEL%

:generate_cases
%PYTHON% -m evaluation.cases.generators
exit /b %ERRORLEVEL%
