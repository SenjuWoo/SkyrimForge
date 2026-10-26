@echo off
setlocal EnableExtensions
set "PSModulePath="
powershell -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0Update-Forge.ps1" %*
exit /b %ERRORLEVEL%
