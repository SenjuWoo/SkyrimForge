# Update only this owner's installed release; logs and recoverable backups stay outside the payload.
[CmdletBinding()]
param(
    [string]$Root,
    [switch]$CheckOnly,
    [string]$Archive,
    [string]$SourceDir,
    [string]$Sha256,
    [string]$ReleaseVersion,
    [switch]$SkipSetup
)
$ErrorActionPreference='Stop'
if (-not $Root) { $Root=if($env:SKYRIM_FORGE_ROOT) {$env:SKYRIM_FORGE_ROOT} else {$PSScriptRoot} }
$Root=[IO.Path]::GetFullPath($Root).TrimEnd('\')
if ($Root -eq [IO.Path]::GetPathRoot($Root).TrimEnd('\')) { throw 'Refusing drive-root update.' }
# Reject linked/game paths before even creating the sibling lock.
$ancestor=Get-Item -LiteralPath $Root
while($ancestor) {
    if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing linked update path: $($ancestor.FullName)" }
    if (Test-Path -LiteralPath (Join-Path $ancestor.FullName 'SkyrimSE.exe')) { throw 'Forge updates cannot target a game installation.' }
    $ancestor=$ancestor.Parent
}
# Keep one stable sibling lock through validation, private moves, setup and rollback.
$lockPath=Join-Path (Split-Path -Parent $Root) ('.'+(Split-Path -Leaf $Root)+'.forge-update.lock')
try { $ownerLock=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
catch { throw "Forge owner update lock is unavailable (another update may be running): $lockPath" }
try {
    if (Test-Path -LiteralPath (Join-Path $Root '.git')) { Write-Host 'Git development checkout preserved; update this source with Git.'; return }
    foreach($required in @('VERSION.txt','MANIFEST.json','Install-AI-Bridge.ps1')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Root $required) -PathType Leaf)) { throw "Not an installed Forge owner root: $Root" }
    }
    $installedText=[IO.File]::ReadAllText((Join-Path $Root 'VERSION.txt')).Trim()
    if ($installedText -notmatch '^Skyrim Forge (\d+\.\d+\.\d+)$') { throw 'Installed Forge version is unknown; preserve and inspect.' }
    $current=[version]$Matches[1]
    if ($SourceDir) {
        if ($Archive) { throw 'Choose an archive or a local source payload, not both.' }
        $SourceDir=[IO.Path]::GetFullPath($SourceDir).TrimEnd('\')
        if ($SourceDir -eq $Root -or $SourceDir.StartsWith($Root+'\',[StringComparison]::OrdinalIgnoreCase) -or $Root.StartsWith($SourceDir+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Source payload and installed owner root must be separate.' }
        $sourceVersion=[IO.File]::ReadAllText((Join-Path $SourceDir 'VERSION.txt')).Trim()
        if ($sourceVersion -notmatch '^Skyrim Forge (\d+\.\d+\.\d+)$') { throw 'Local source version is unknown.' }
        $ReleaseVersion=$Matches[1]
    }
    $logs=Join-Path $env:LOCALAPPDATA 'Skyrim-Forge\logs'
    $work=Join-Path ([IO.Path]::GetTempPath()) ('forge-update-'+[guid]::NewGuid().ToString('N'))
    $stage=Join-Path (Split-Path -Parent $Root) ('.forge-stage-'+[guid]::NewGuid().ToString('N'))
    $backup=Join-Path (Split-Path -Parent $Root) ('.forge-backup-'+[guid]::NewGuid().ToString('N'))
    $swapped=$false; $originalMoved=$false
    $preserved=New-Object 'System.Collections.Generic.List[string]'
    # Owner manifests delimit traversal; unknown directories are private and move intact.
    function Add-OwnerPaths($Manifest,$Files,$Directories) {
        foreach($file in @($Manifest.files)) {
            $relative=([string]$file.path).Replace('\','/')
            if (-not $relative -or $relative -match '(^|/)\.\.?(/|$)|:|^/|//' -or $Files.ContainsKey($relative)) { throw 'Unsafe or duplicate owner manifest path.' }
            if ($file.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Owner manifest has an invalid file digest.' }
            $Files[$relative]=[string]$file.sha256
            $index=$relative.LastIndexOf('/')
            while($index -gt 0) { $Directories[$relative.Substring(0,$index)]=$true; $index=$relative.LastIndexOf('/',$index-1) }
        }
    }
    $priorEnv=@{}
    foreach($name in @('SKYRIM_FORGE_ROOT','SKYRIM_FORGE_PYTHON','UABS_PYTHON','HOUSECARL_ROOT','HOUSECARL_MCP')) {
        $priorEnv[$name]=[Environment]::GetEnvironmentVariable($name,'User')
    }
    try {
        if (-not $Archive -and -not $SourceDir) {
            $release=Invoke-RestMethod 'https://api.github.com/repos/SenjuWoo/SkyrimForge/releases/latest' -Headers @{ 'User-Agent'='SkyrimForge-owner-update'; Accept='application/vnd.github+json' }
            if ($release.draft -or $release.prerelease -or $release.tag_name -notmatch '^v(\d+\.\d+\.\d+)$') { throw 'Latest owner release is not a stable semantic version.' }
            $ReleaseVersion=$Matches[1]
            $name="Skyrim-Forge-$ReleaseVersion.zip"
            $assets=@($release.assets | Where-Object name -eq $name)
            if ($assets.Count -ne 1 -or $assets[0].digest -notmatch '^sha256:([a-fA-F0-9]{64})$') { throw 'Owner release needs exactly one archive with a GitHub SHA-256 digest.' }
            $Sha256=$Matches[1]
            $url=[string]$assets[0].browser_download_url
            if ($url -cne "https://github.com/SenjuWoo/SkyrimForge/releases/download/v$ReleaseVersion/$name") { throw 'Unexpected owner release archive URL.' }
        }
        if ($ReleaseVersion -notmatch '^\d+\.\d+\.\d+$' -or (-not $SourceDir -and $Sha256 -notmatch '^[a-fA-F0-9]{64}$')) { throw 'Release version and SHA-256 are required.' }
        if ([version]$ReleaseVersion -lt $current) { Write-Host "Installed Forge $current kept; selected owner release is $ReleaseVersion."; return }
        if ($CheckOnly) {
            if ([version]$ReleaseVersion -eq $current) { Write-Host "Installed Forge $current kept; selected owner release has the same version." }
            else { Write-Host "Forge update available: $current -> $ReleaseVersion" }
            return
        }
        New-Item -ItemType Directory -Force -Path $work,$logs | Out-Null
        if ($SourceDir) { $payload=$SourceDir } else {
            if (-not $Archive) { $Archive=Join-Path $work 'release.zip'; Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $Archive }
            if ((Get-FileHash -LiteralPath $Archive -Algorithm SHA256).Hash -ine $Sha256) { throw 'Forge release archive SHA-256 mismatch.' }
            # Reject traversal and links before extraction, including Windows path separators.
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            $zip=[IO.Compression.ZipFile]::OpenRead($Archive)
            try {
                if ($zip.Entries.Count -gt 20000) { throw 'Forge release archive contains too many entries.' }
                $total=0L
                foreach($entry in $zip.Entries) {
                    $name=$entry.FullName.Replace('\','/')
                    if ($name -notlike "Skyrim-Forge-$ReleaseVersion/*" -or $name -match '(^|/)\.\.(/|$)|:|^/' -or (($entry.ExternalAttributes -shr 16) -band 0xF000) -eq 0xA000) { throw "Unsafe release member: $name" }
                    $total+=$entry.Length
                    if ($total -gt 2GB) { throw 'Forge release archive exceeds size limit.' }
                }
            } finally { $zip.Dispose() }
            $extract=Join-Path $work 'extract'; Expand-Archive -LiteralPath $Archive -DestinationPath $extract
            $payload=Join-Path $extract "Skyrim-Forge-$ReleaseVersion"
        }
        if ([IO.File]::ReadAllText((Join-Path $payload 'VERSION.txt')).Trim() -cne "Skyrim Forge $ReleaseVersion") { throw 'Release archive version does not match its owner tag.' }
        $ancestor=Get-Item -LiteralPath (Join-Path $payload 'MANIFEST.json')
        while($ancestor) {
            if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Release manifest path is linked.' }
            $ancestor=$ancestor.Parent
        }
        $manifest=[IO.File]::ReadAllText((Join-Path $payload 'MANIFEST.json')) | ConvertFrom-Json
        if ($manifest.product -ne 'Skyrim Forge' -or $manifest.version -ne $ReleaseVersion) { throw 'Release manifest identity mismatch.' }
        $oldManifest=[IO.File]::ReadAllText((Join-Path $Root 'MANIFEST.json')) | ConvertFrom-Json
        if ($oldManifest.product -ne 'Skyrim Forge' -or [string]$oldManifest.version -notmatch '^\d+\.\d+\.\d+$') { throw 'Installed owner manifest identity mismatch.' }
        $oldFiles=@{}; $oldDirs=@{}; $newFiles=@{}; $newDirs=@{}
        Add-OwnerPaths $oldManifest $oldFiles $oldDirs
        Add-OwnerPaths $manifest $newFiles $newDirs
        foreach($file in @($manifest.files)) {
            $path=([string]$file.path).Replace('\','/')
            if ($file.sha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'Unsafe release manifest digest.' }
            $target=Join-Path $payload $path
            if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw "Release manifest file is missing: $path" }
            $ancestor=Get-Item -LiteralPath $target
            while($ancestor) {
                if ($ancestor.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Release payload contains a linked path: $path" }
                $ancestor=$ancestor.Parent
            }
            if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ine $file.sha256) { throw "Release manifest verification failed: $path" }
        }
        foreach($required in @('VERSION.txt','Install-AI-Bridge.ps1')) { if (-not $newFiles.ContainsKey($required)) { throw "Release manifest is missing $required" } }
        foreach($name in @('MANIFEST.json','BUILD-RECEIPT.json','SBOM.spdx.json','VALIDATION.json','CHECKSUMS-SHA256.txt')) { $oldFiles[$name]=$true; $newFiles[$name]=$true }
        $private=New-Object 'System.Collections.Generic.List[string]'
        $pending=New-Object 'System.Collections.Generic.Stack[string]'; $pending.Push('')
        while($pending.Count) {
            $directory=$pending.Pop()
            foreach($item in @(Get-ChildItem -LiteralPath (Join-Path $Root $directory) -Force)) {
                $relative=if($directory) { $directory+'/'+$item.Name } else { $item.Name }
                if ($oldFiles.ContainsKey($relative) -or $oldDirs.ContainsKey($relative)) {
                    if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $item.PSIsContainer -ne $oldDirs.ContainsKey($relative)) { throw "Owned release path is a link or changed type: $relative" }
                    if ($item.PSIsContainer) { $pending.Push($relative) }
                    elseif ($relative -ne 'VERSION.txt' -and [string]$oldFiles[$relative] -match '^[a-fA-F0-9]{64}$' -and (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash -ine $oldFiles[$relative]) {
                        throw "Edited owner file preserved; inspect before updating: $relative"
                    }
                } else {
                    # Old timestamp-based bytecode can shadow equal-size new source; keep it in the rollback tree.
                    if ($item.PSIsContainer -and $item.Name -eq '__pycache__') { continue }
                    if ($newFiles.ContainsKey($relative) -or $newDirs.ContainsKey($relative)) { throw "Private path conflicts with the new release: $relative" }
                    $private.Add($relative)
                }
            }
        }
        if ([version]$ReleaseVersion -eq $current) {
            $samePayload=$oldFiles.Count -eq $newFiles.Count
            foreach($file in @($manifest.files)) {
                $path=([string]$file.path).Replace('\','/')
                $target=Join-Path $Root $path
                if (-not $oldFiles.ContainsKey($path) -or $oldFiles[$path] -ine $file.sha256 -or -not (Test-Path -LiteralPath $target -PathType Leaf) -or (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ine $file.sha256) { $samePayload=$false; break }
            }
            if (-not $samePayload) { throw 'Same-version owner payload differs; preserve it and use a newer verified release or inspect the installation.' }
            Write-Host "Forge $current already matches the verified owner payload."
            return
        }
        # Copy only the verified release, then rename private trees without reading their contents.
        New-Item -ItemType Directory -Path $stage | Out-Null
        foreach($relative in $newFiles.Keys) {
            $source=Join-Path $payload $relative
            if (Test-Path -LiteralPath $source -PathType Leaf) {
                if ((Get-Item -LiteralPath $source).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Release report path is linked: $relative" }
                $destination=Join-Path $stage $relative
                New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
                Copy-Item -LiteralPath $source -Destination $destination
            }
        }
        foreach($file in @($manifest.files)) {
            if ((Get-FileHash -LiteralPath (Join-Path $stage $file.path) -Algorithm SHA256).Hash -ine $file.sha256) { throw "Staged release verification failed: $($file.path)" }
        }
        Move-Item -LiteralPath $Root -Destination $backup; $originalMoved=$true
        Move-Item -LiteralPath $stage -Destination $Root; $swapped=$true
        foreach($relative in $private) {
            $destination=Join-Path $Root $relative
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Move-Item -LiteralPath (Join-Path $backup $relative) -Destination $destination
            $preserved.Add($relative)
        }
        if (-not $SkipSetup) {
            $LASTEXITCODE=0
            & (Join-Path $Root 'Install-AI-Bridge.ps1') -Provider All -BootstrapPython -Yes
            if ($LASTEXITCODE -ne 0) { throw "Forge setup failed with exit code $LASTEXITCODE" }
        }
        Add-Content -LiteralPath (Join-Path $logs 'owner-update.log') -Value ("$(Get-Date -Format o) version=$ReleaseVersion root=$Root backup=$backup result=PASS")
        Write-Host "Forge $ReleaseVersion installed. Last good release: $backup"
    } catch {
        $cause=$_.Exception.Message
        if ($originalMoved) {
            try {
                # Return every moved private entry before restoring the prior owner payload.
                foreach($relative in $preserved) {
                    $destination=Join-Path $backup $relative
                    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
                    Move-Item -LiteralPath (Join-Path $Root $relative) -Destination $destination
                }
                if ($swapped -and (Test-Path -LiteralPath $Root)) { Move-Item -LiteralPath $Root -Destination ($stage+'-failed') }
                Move-Item -LiteralPath $backup -Destination $Root
                foreach($name in $priorEnv.Keys) {
                    if ([Environment]::GetEnvironmentVariable($name,'User') -cne $priorEnv[$name]) { [Environment]::SetEnvironmentVariable($name,$priorEnv[$name],'User') }
                }
            } catch { $cause+="; rollback failed: $($_.Exception.Message); recover $backup" }
        }
        New-Item -ItemType Directory -Force -Path $logs | Out-Null
        Add-Content -LiteralPath (Join-Path $logs 'owner-update.log') -Value ("$(Get-Date -Format o) root=$Root failure=$cause")
        throw $cause
    } finally {
        if (Test-Path -LiteralPath $work) { Remove-Item -LiteralPath $work -Recurse -Force }
        if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force }
    }
} finally {
    # Retain the lock file so another caller cannot acquire a different file during cleanup.
    $ownerLock.Dispose()
}
