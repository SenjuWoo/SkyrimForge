# Install the Forge-owned houseCARL payload; keep newer copies and user settings.
[CmdletBinding()]
param([string]$SourceZip, [switch]$SkipSetup, [switch]$CheckOnly)
$ErrorActionPreference='Stop'
$version=[version]'2.1.1'
$digest='1cb9fda834590d367e9907c35e5053624be050c316424d1f917f74e004c4816c'
function Get-HouseCarlCandidates([string[]]$McpPaths,[string[]]$Roots) {
    $all=@($McpPaths)
    foreach ($hint in $Roots) {
        if (-not $hint) { continue }
        foreach ($relative in @('server\housecarl-mcp.exe','housecarl-mcp.exe','housecarl\server\housecarl-mcp.exe')) { $all+=Join-Path $hint $relative }
    }
    return @($all | Where-Object { $_ -and (Test-Path -LiteralPath $_ -PathType Leaf) } | Select-Object -Unique)
}
function Get-HouseCarlLocation([string]$Executable) {
    $directory=Split-Path -Parent $Executable
    $owner=if ((Split-Path -Leaf $directory) -ieq 'server') { Split-Path -Parent $directory } else { $directory }
    return [pscustomobject]@{root=$owner;server=$directory;mcp=$Executable}
}
$candidates=Get-HouseCarlCandidates -McpPaths @($env:HOUSECARL_MCP,[Environment]::GetEnvironmentVariable('HOUSECARL_MCP','User')) -Roots @($env:HOUSECARL_ROOT,[Environment]::GetEnvironmentVariable('HOUSECARL_ROOT','User'),(Join-Path $env:LOCALAPPDATA 'houseCARL'))
$existing=@($candidates | ForEach-Object {
    $text=[Diagnostics.FileVersionInfo]::GetVersionInfo($_).FileVersion
    if ($text -notmatch '(\d+\.\d+\.\d+)') { throw "Cannot determine houseCARL version; preserve and inspect: $_" }
    [pscustomobject]@{path=$_;version=[version]$Matches[1]}
} | Sort-Object version -Descending) | Select-Object -First 1
$location=if($existing) { Get-HouseCarlLocation $existing.path } else { Get-HouseCarlLocation (Join-Path $env:LOCALAPPDATA 'houseCARL\server\housecarl-mcp.exe') }
$root=$location.root; $server=$location.server; $mcp=$location.mcp
if ($CheckOnly) { if (-not $existing -or $existing.version -lt $version) { throw 'houseCARL install/update required.' }; Write-Host "houseCARL $($existing.version) verified: $mcp"; return }
$work=Join-Path $env:LOCALAPPDATA ('Skyrim-Forge\housecarl-work\'+[guid]::NewGuid().ToString('N'))
try {
    if (-not $existing -or $existing.version -lt $version) {
        New-Item -ItemType Directory -Force -Path $work | Out-Null
        if (-not $SourceZip) {
            $SourceZip=Join-Path $work 'houseCARL-2.1.1.zip'
            Invoke-WebRequest 'https://github.com/Avick3110/houseCARL/releases/download/v2.1.1/houseCARL-2.1.1.zip' -OutFile $SourceZip -UseBasicParsing
        }
        if ((Get-FileHash -LiteralPath $SourceZip -Algorithm SHA256).Hash -ine $digest) { throw 'houseCARL archive checksum mismatch.' }
        $extract=Join-Path $work 'extract'
        Expand-Archive -LiteralPath $SourceZip -DestinationPath $extract
        $payload=@(Get-ChildItem -LiteralPath $extract -Filter housecarl-mcp.exe -File -Recurse)
        if ($payload.Count -ne 1) { throw 'houseCARL archive must contain one server.' }
        $stage=Join-Path (Split-Path -Parent $server) ('.housecarl-stage-'+[guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Force -Path $root | Out-Null
        if (Test-Path -LiteralPath (Join-Path $root '.git')) { throw 'Update this houseCARL source checkout with Git; installer will not replace it.' }
        if (Test-Path -LiteralPath $server) { Copy-Item -LiteralPath $server -Destination $stage -Recurse } else { New-Item -ItemType Directory -Path $stage | Out-Null }
        Copy-Item -Path (Join-Path $payload[0].DirectoryName '*') -Destination $stage -Recurse -Force
        # App settings are user-owned; payload updates never replace them.
        if (Test-Path -LiteralPath $server) {
            Get-ChildItem -LiteralPath $server -Filter 'appsettings*.json' -File | ForEach-Object { Copy-Item -LiteralPath $_.FullName -Destination $stage -Force }
        }
        $backup=Join-Path (Split-Path -Parent $server) ('.housecarl-backup-'+[guid]::NewGuid().ToString('N'))
        $hadServer=Test-Path -LiteralPath $server
        if ([IO.Path]::GetFullPath($server).TrimEnd('\') -eq [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($server)).TrimEnd('\')) { throw 'Refusing a drive-root tool installation.' }
        try {
            if ($hadServer) { Move-Item -LiteralPath $server -Destination $backup }
            Move-Item -LiteralPath $stage -Destination $server
            if (-not (Test-Path -LiteralPath (Join-Path $server 'housecarl-mcp.exe'))) { throw 'Installed houseCARL server missing.' }
        } catch {
            if ($hadServer -and (Test-Path -LiteralPath $backup)) {
                if (Test-Path -LiteralPath $server) { Remove-Item -LiteralPath $server -Recurse -Force }
                Move-Item -LiteralPath $backup -Destination $server
            }
            throw
        }
        Write-Host "houseCARL $version installed; last good server retained at $backup"
    } else { Write-Host "houseCARL $($existing.version) kept: $root" }
    [Environment]::SetEnvironmentVariable('HOUSECARL_ROOT',$root,'User')
    [Environment]::SetEnvironmentVariable('HOUSECARL_MCP',$mcp,'User')
    $env:HOUSECARL_ROOT=$root; $env:HOUSECARL_MCP=$mcp
    if (-not $SkipSetup) {
        & (Join-Path $PSScriptRoot 'integrations\skyrim-pack\skills\housecarl\scripts\Setup-HouseCarl.ps1') -WireGrok:$false -WireCodex:$false -Quiet
    }
} catch {
    $logs=Join-Path $env:LOCALAPPDATA 'Skyrim-Forge\logs'
    New-Item -ItemType Directory -Force -Path $logs | Out-Null
    Add-Content -LiteralPath (Join-Path $logs 'housecarl-install.log') -Value ("$(Get-Date -Format o) version=$version root=$root failure="+$_.Exception.Message)
    throw
} finally {
    $workRoot=[IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'Skyrim-Forge\housecarl-work'))+'\'
    if ([IO.Path]::GetFullPath($work).StartsWith($workRoot,[StringComparison]::OrdinalIgnoreCase) -and (Test-Path -LiteralPath $work)) { Remove-Item -LiteralPath $work -Recurse -Force }
}
