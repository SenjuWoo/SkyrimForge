# Preserve the single-skill entrypoint while using the same canonical pack writer and provider paths.
[CmdletBinding()]
param([ValidateSet('All','Codex','Claude','Grok','Kimi','Hermes','Antigravity')][string]$Provider='All')
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'Install-Skyrim-Pack.ps1') -Provider $Provider -Skills @('skyrim-forge')
