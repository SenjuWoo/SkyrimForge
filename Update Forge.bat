@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "PSModulePath="
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Forge.ps1" %*
exit /b %ERRORLEVEL%
