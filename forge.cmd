@echo off
rem Skyrim Forge command shim. Runs the CLI that lives beside this file, so
rem "forge doctor" works without activating the virtual environment or editing PATH.
setlocal EnableExtensions DisableDelayedExpansion
set "FORGE_ROOT=%~dp0"
rem Put the install root on the child's import path; the caller's working directory stays intact.
set "PYTHONPATH=%FORGE_ROOT%;%PYTHONPATH%"
if exist "%FORGE_ROOT%.venv\Scripts\python.exe" (
  "%FORGE_ROOT%.venv\Scripts\python.exe" -m skyrim_forge %*
) else (
  python -m skyrim_forge %*
)
exit /b %ERRORLEVEL%
