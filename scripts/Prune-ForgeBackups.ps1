<#
.SYNOPSIS
  Remove old Forge-owned update backups and abandoned failed stage directories.

.DESCRIPTION
  Update-Forge.ps1 keeps every backup it has ever made, so a machine that
  updates weekly grows one 12-17 MB copy per release. This helper keeps the
  newest -Retain product backups and deletes only directories Forge can prove
  it owns:

    * the exact name .forge-backup-<32 lowercase hex>;
    * a VERSION.txt whose first line is "Skyrim Forge <x.y.z>";
    * a MANIFEST.json beside it;
    * not a reparse point.

  Anything else in the parent directory is left untouched, including legacy
  "Skyrim-Forge.backup-*" copies and the live install. Failed stage directories
  older than -StageDays are removed, keeping the newest one for diagnosis.

  -WhatIf prints the plan without deleting anything.
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [Parameter(Mandatory = $true)][string]$Parent,
    [int]$Retain = 2,
    [int]$StageDays = 7
)
$ErrorActionPreference = 'Stop'
if ($Retain -lt 1) { throw 'Retain must be at least 1.' }
if ($StageDays -lt 1) { throw 'StageDays must be at least 1.' }
$Parent = [IO.Path]::GetFullPath($Parent).TrimEnd('\')
if (-not (Test-Path -LiteralPath $Parent -PathType Container)) { throw "Backup parent does not exist: $Parent" }
if ($Parent -eq [IO.Path]::GetPathRoot($Parent).TrimEnd('\')) { throw 'Refusing to prune beside a drive root.' }
$parentItem = Get-Item -LiteralPath $Parent -Force
if (($parentItem.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw "Refusing to prune through a reparse point: $Parent" }

$removed = New-Object System.Collections.Generic.List[string]
$backups = @(Get-ChildItem -LiteralPath $Parent -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -cmatch '^\.forge-backup-[0-9a-f]{32}$' } |
    Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 } |
    Where-Object {
        (Test-Path -LiteralPath (Join-Path $_.FullName 'VERSION.txt') -PathType Leaf) -and
        (Test-Path -LiteralPath (Join-Path $_.FullName 'MANIFEST.json') -PathType Leaf) -and
        ((Get-Content -LiteralPath (Join-Path $_.FullName 'VERSION.txt') -TotalCount 1) -match '^Skyrim Forge [0-9]+\.[0-9]+\.[0-9]+$')
    } | Sort-Object LastWriteTime -Descending)
foreach ($dir in @($backups | Select-Object -Skip $Retain)) {
    if ($PSCmdlet.ShouldProcess($dir.FullName, 'Remove old Forge backup')) {
        try { Remove-Item -LiteralPath $dir.FullName -Recurse -Force; $removed.Add($dir.FullName) }
        catch { Write-Warning "Could not remove $($dir.FullName): $($_.Exception.Message)" }
    } else { $removed.Add("would remove $($dir.FullName)") }
}

$cutoff = (Get-Date).AddDays(-$StageDays)
$stages = @(Get-ChildItem -LiteralPath $Parent -Directory -Force -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -cmatch '^\.forge-stage-[0-9a-f]+-failed$' } |
    Where-Object { ($_.Attributes -band [IO.FileAttributes]::ReparsePoint) -eq 0 -and $_.LastWriteTime -lt $cutoff } |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip 1)
foreach ($dir in $stages) {
    if ($PSCmdlet.ShouldProcess($dir.FullName, 'Remove abandoned Forge stage')) {
        try { Remove-Item -LiteralPath $dir.FullName -Recurse -Force; $removed.Add($dir.FullName) }
        catch { Write-Warning "Could not remove $($dir.FullName): $($_.Exception.Message)" }
    } else { $removed.Add("would remove $($dir.FullName)") }
}

$removed
