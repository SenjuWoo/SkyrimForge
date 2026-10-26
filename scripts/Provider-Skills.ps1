# Forge owns its provider paths, skill digests and recoverable swaps independently of the AI bundle.
function Get-ForgeProviderSkillsRoot([string]$Provider) {
    $profileRoot = if ($env:USERPROFILE) { $env:USERPROFILE } else { [Environment]::GetFolderPath('UserProfile') }
    switch ($Provider) {
        'Codex' { return (Join-Path $profileRoot '.agents\skills') }
        'Claude' { $homeRoot = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $profileRoot '.claude' } }
        'Grok' { $homeRoot = if ($env:GROK_HOME) { $env:GROK_HOME } else { Join-Path $profileRoot '.grok' } }
        'Kimi' { $homeRoot = if ($env:KIMI_CODE_HOME) { $env:KIMI_CODE_HOME } else { Join-Path $profileRoot '.kimi-code' } }
        'Antigravity' { $homeRoot = if ($env:ANTIGRAVITY_HOME) { $env:ANTIGRAVITY_HOME } elseif ($env:ANTIGRAVITY_CONFIG_DIR) { $env:ANTIGRAVITY_CONFIG_DIR } else { Join-Path $profileRoot '.gemini\config' } }
        'Hermes' {
            $homeRoot = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' }
            $parent = Split-Path -Parent $homeRoot
            if ((Split-Path -Leaf $parent) -eq 'profiles') {
                $realRoot = Split-Path -Parent $parent
                if (Test-Path -LiteralPath (Join-Path $realRoot 'config.yaml') -PathType Leaf) { $homeRoot = $realRoot }
            }
        }
        default { throw "Unknown provider: $Provider" }
    }
    return (Join-Path $homeRoot 'skills')
}

# Refuse links before descending, so a source or target cannot escape into another owner's tree.
function Assert-ForgeSkillTree([string]$Path) {
    $pending = New-Object 'System.Collections.Generic.Stack[string]'
    $pending.Push($Path)
    while ($pending.Count) {
        $item = Get-Item -LiteralPath $pending.Pop() -Force -ErrorAction Stop
        if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing reparse point: $($item.FullName)" }
        if ($item.PSIsContainer) { foreach ($child in @(Get-ChildItem -LiteralPath $item.FullName -Force)) { $pending.Push($child.FullName) } }
    }
}

# Keep the established bundle/Forge digest format so unchanged legacy copies can transfer safely.
function Get-ForgeSkillDigest([string]$Path) {
    $root = [IO.Path]::GetFullPath($Path).TrimEnd('\') + '\'
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $rows = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force | ForEach-Object {
            $stream = [IO.File]::OpenRead($_.FullName)
            try { $hash = [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') } finally { $stream.Dispose() }
            $_.FullName.Substring($root.Length).Replace('\', '/') + '=' + $hash
        } | Sort-Object)
        return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($rows -join "`n")))).Replace('-', '')
    } finally { $sha.Dispose() }
}

function Sync-ForgeProviderSkills {
    param([string]$Provider, [string]$Source, [string]$Descriptor, [string[]]$Skills, [switch]$Check, [string]$SkillsRoot)
    $skillsRoot = if ($SkillsRoot) { [IO.Path]::GetFullPath($SkillsRoot) } else { [IO.Path]::GetFullPath((Get-ForgeProviderSkillsRoot $Provider)) }
    $stateRoot = Join-Path $env:LOCALAPPDATA 'Skyrim-Forge'
    $stateDir = Join-Path $stateRoot 'managed-skills'
    $logDir = Join-Path $stateRoot 'logs'
    New-Item -ItemType Directory -Force -Path $stateDir, $logDir | Out-Null
    $sha = [Security.Cryptography.SHA256]::Create()
    try { $key = [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($skillsRoot.ToLowerInvariant()))).Replace('-', '').Substring(0, 16) } finally { $sha.Dispose() }
    $ledgerPath = Join-Path $stateDir ($Provider.ToLowerInvariant() + '-' + $key + '.json')
    $lock = [IO.File]::Open($ledgerPath + '.lock', [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
    $work = Join-Path (Split-Path -Parent $skillsRoot) '.skyrim-forge-skill-work'
    $changes = New-Object 'System.Collections.Generic.List[object]'
    $stages = New-Object 'System.Collections.Generic.List[string]'
    $owned = @{}; $preserved = @{}; $legacy = @{}
    $committed = $false
    $oldBytes = $null; $tempLedger = $ledgerPath + '.' + [guid]::NewGuid().ToString('N') + '.tmp'
    try {
        if (Test-Path -LiteralPath $ledgerPath -PathType Leaf) {
            if ((Get-Item -LiteralPath $ledgerPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing linked ownership ledger.' }
            $oldBytes = [IO.File]::ReadAllBytes($ledgerPath)
            $previous = [Text.Encoding]::UTF8.GetString($oldBytes) | ConvertFrom-Json
            if ($previous.schema -ne 1 -or $previous.skills_dir -ne $skillsRoot) { throw "Invalid Forge ownership ledger: $ledgerPath" }
            foreach ($entry in @($previous.skills)) { if ($entry.name -notmatch '^[a-z0-9][a-z0-9-]*$' -or $entry.digest -notmatch '^[A-Fa-f0-9]{64}$') { throw 'Invalid owned skill digest.' }; $owned[[string]$entry.name] = [string]$entry.digest }
            foreach ($entry in @($previous.preserved)) { $preserved[[string]$entry.name] = [string]$entry.digest }
        }
        # Legacy UABS proof is read-only. Forge never rewrites another product's ledger.
        foreach ($folder in @('managed-skills', 'external-skills')) {
            $path = Join-Path $env:LOCALAPPDATA ('Ultimate-AI-Starter-Bundle\' + $folder + '\' + $Provider.ToLowerInvariant() + '.json')
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                $doc = [IO.File]::ReadAllText($path) | ConvertFrom-Json
                if ($doc.PSObject.Properties['path'] -and $doc.path -and [IO.Path]::GetFullPath([string]$doc.path) -ne $skillsRoot) { continue }
                foreach ($entry in @($doc.skills)) { $legacy[[string]$entry.name] = [string]$entry.digest }
            }
        }
        $dirs = @(Get-ChildItem -LiteralPath $Source -Directory | Where-Object { -not $Skills -or $Skills -contains $_.Name })
        if (-not $dirs.Count -or ($Skills -and @($Skills | Where-Object { $dirs.Name -notcontains $_ }).Count)) { throw 'Requested Skyrim skill source is missing.' }
        if (Test-Path -LiteralPath $skillsRoot) {
            if ((Get-Item -LiteralPath $skillsRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Refusing skills root reparse point: $skillsRoot" }
        } elseif ($Check) { throw "Provider skills root missing: $skillsRoot" }
        else { New-Item -ItemType Directory -Force -Path $skillsRoot | Out-Null }
        New-Item -ItemType Directory -Force -Path $work | Out-Null
        $updated = 0; $kept = 0
        foreach ($dir in $dirs) {
            Assert-ForgeSkillTree $dir.FullName
            if (-not (Test-Path -LiteralPath (Join-Path $dir.FullName 'SKILL.md') -PathType Leaf)) { throw "Skill source has no SKILL.md: $($dir.Name)" }
            $target = Join-Path $skillsRoot $dir.Name
            $current = $null
            if (Test-Path -LiteralPath $target) { Assert-ForgeSkillTree $target; $current = Get-ForgeSkillDigest $target }
            if ($Check) {
                if (-not $current -or ($current -cne $owned[$dir.Name] -and $current -cne $preserved[$dir.Name])) { throw "Skill missing or changed since install: $target" }
                if ($preserved.ContainsKey($dir.Name)) { Write-Warning "Personal skill preserved; source equality not claimed: $target" }
                continue
            }
            $stage = Join-Path $work ('stage-' + $dir.Name + '-' + [guid]::NewGuid().ToString('N'))
            $stages.Add($stage)
            Copy-Item -LiteralPath $dir.FullName -Destination $stage -Recurse
            if ((Get-ForgeSkillDigest $stage) -cne (Get-ForgeSkillDigest $dir.FullName)) { throw "Staged skill verification failed: $($dir.Name)" }
            if ($dir.Name -eq 'skyrim-forge' -and (Test-Path -LiteralPath $Descriptor -PathType Leaf)) { Copy-Item -LiteralPath $Descriptor -Destination (Join-Path $stage 'INSTALLATION.json') -Force }
            $wanted = Get-ForgeSkillDigest $stage
            if ($current -ceq $wanted) { $owned[$dir.Name] = $wanted; [void]$preserved.Remove($dir.Name); continue }
            $proof = if ($owned.ContainsKey($dir.Name)) { $owned[$dir.Name] } else { $legacy[$dir.Name] }
            if ($current -and $current -cne $proof) {
                $preserved[$dir.Name] = $current; $kept++
                Write-Warning "Personal or unowned skill preserved: $target"
                continue
            }
            $backup = Join-Path $work ('backup-' + $dir.Name + '-' + [guid]::NewGuid().ToString('N'))
            $change = [pscustomobject]@{ Target=$target; Backup=$backup; HadOriginal=[bool]$current; Swapped=$false }
            if ($current) { Move-Item -LiteralPath $target -Destination $backup }
            $changes.Add($change)
            Move-Item -LiteralPath $stage -Destination $target
            $change.Swapped = $true
            if ((Get-ForgeSkillDigest $target) -cne $wanted) { throw "Installed skill verification failed: $target" }
            $owned[$dir.Name] = $wanted; [void]$preserved.Remove($dir.Name); $updated++
        }
        # Retire the old shared name only with this owner's previous digest proof.
        if ($dirs.Name -contains 'skyrim-tooling-stack') {
            $oldName = 'ai-tooling-stack'
            $oldTarget = Join-Path $skillsRoot $oldName
            if (Test-Path -LiteralPath $oldTarget) {
                Assert-ForgeSkillTree $oldTarget
                $oldDigest = Get-ForgeSkillDigest $oldTarget
                if ($owned.ContainsKey($oldName) -and $oldDigest -ceq $owned[$oldName]) {
                    if ($Check) { throw "Legacy Forge skill needs migration: $oldTarget" }
                    $backup = Join-Path $work ('backup-' + $oldName + '-' + [guid]::NewGuid().ToString('N'))
                    $change = [pscustomobject]@{ Target=$oldTarget; Backup=$backup; HadOriginal=$true; Swapped=$false }
                    Move-Item -LiteralPath $oldTarget -Destination $backup
                    $changes.Add($change)
                    [void]$owned.Remove($oldName); [void]$preserved.Remove($oldName)
                    Write-Host "Legacy Forge skill recovered at $backup; general namespace released."
                } elseif (-not $Check) {
                    [void]$owned.Remove($oldName)
                    $preserved[$oldName] = $oldDigest
                    Write-Warning "Edited or unowned legacy skill preserved: $oldTarget"
                }
            } elseif (-not $Check) { [void]$owned.Remove($oldName); [void]$preserved.Remove($oldName) }
        }
        if (-not $Check) {
            $ledger = [ordered]@{ schema=1; owner='SkyrimForge'; provider=$Provider; skills_dir=$skillsRoot;
                skills=@($owned.Keys | Sort-Object | ForEach-Object { @{ name=$_; digest=$owned[$_] } });
                preserved=@($preserved.Keys | Sort-Object | ForEach-Object { @{ name=$_; digest=$preserved[$_] } }) }
            [IO.File]::WriteAllText($tempLedger, (($ledger | ConvertTo-Json -Depth 6) + "`n"), (New-Object Text.UTF8Encoding $false))
            if ($oldBytes) { [IO.File]::Replace($tempLedger, $ledgerPath, [NullString]::Value) } else { [IO.File]::Move($tempLedger, $ledgerPath) }
        }
        $committed = $true
        if ($env:SKYRIM_FORGE_DEBUG -eq '1') { Add-Content -LiteralPath (Join-Path $logDir 'skill-install.log') -Value ("$(Get-Date -Format o) provider=$Provider root=$skillsRoot check=$Check updated=$updated preserved=$kept") }
        Write-Host ("${Provider}: Skyrim skills checked={0} updated={1} personal-preserved={2}; ledger={3}" -f $dirs.Count,$updated,$kept,$ledgerPath)
    } catch {
        $cause = $_.Exception.Message
        for ($i=$changes.Count-1; -not $committed -and $i -ge 0; $i--) {
            $change = $changes[$i]
            try {
                if ($change.Swapped -and (Test-Path -LiteralPath $change.Target)) { Remove-Item -LiteralPath $change.Target -Recurse -Force }
                if ($change.HadOriginal -and (Test-Path -LiteralPath $change.Backup)) { Move-Item -LiteralPath $change.Backup -Destination $change.Target }
            } catch { $cause += "; rollback failed; recover backup $($change.Backup): $($_.Exception.Message)" }
        }
        Add-Content -LiteralPath (Join-Path $logDir 'skill-install.log') -Value ("$(Get-Date -Format o) failure=$cause")
        throw $cause
    } finally {
        # Backups stay outside the indexed root, including when rollback itself fails.
        foreach ($stage in $stages) { if (Test-Path -LiteralPath $stage) { Remove-Item -LiteralPath $stage -Recurse -Force } }
        if (Test-Path -LiteralPath $tempLedger) { Remove-Item -LiteralPath $tempLedger -Force }
        $lock.Dispose()
    }
}
