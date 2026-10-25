[CmdletBinding()]
param(
    [ValidateSet('All', 'Codex', 'Claude', 'Grok', 'Kimi', 'Hermes', 'Antigravity')]
    [string]$Provider = 'All',
    [switch]$WithHouseCarl
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$PackRoot = Join-Path $Root 'integrations\skyrim-pack'
$SkillsSource = Join-Path $PackRoot 'skills'
$InstallationDescriptorPath = Join-Path $Root 'INSTALLATION.json'

if (-not (Test-Path -LiteralPath $SkillsSource -PathType Container)) {
    throw "Bundled Skyrim skill pack is missing: $SkillsSource"
}

function Test-ReparsePoint {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $false }
    return [bool]((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Get-TreeDigest {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = (Resolve-Path -LiteralPath $Path).Path.TrimEnd('\') + '\'
    $fileSha = [Security.Cryptography.SHA256]::Create()
    try {
        $rows = @(Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction Stop | ForEach-Object {
            $stream = [IO.File]::OpenRead($_.FullName)
            try { $hex = [BitConverter]::ToString($fileSha.ComputeHash($stream)).Replace('-', '') } finally { $stream.Dispose() }
            $_.FullName.Substring($resolved.Length).Replace('\', '/') + '=' + $hex
        } | Sort-Object)
    } finally { $fileSha.Dispose() }
    $bytes = [Text.Encoding]::UTF8.GetBytes(($rows -join "`n"))
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-', '') } finally { $sha.Dispose() }
}

function Get-ProviderSkillsRoot {
    param([Parameter(Mandatory = $true)][string]$Name)
    $UserProfile = [Environment]::GetFolderPath('UserProfile')
    switch ($Name) {
        'Codex' {
            if ($env:CODEX_HOME) { return (Join-Path $env:CODEX_HOME 'skills') }
            $AgentsSkills = Join-Path (Join-Path $UserProfile '.agents') 'skills'
            if (Test-Path -LiteralPath $AgentsSkills -PathType Container) { return $AgentsSkills }
            return (Join-Path (Join-Path $UserProfile '.codex') 'skills')
        }
        'Claude' {
            $HomeDir = if ($env:CLAUDE_CONFIG_DIR) { $env:CLAUDE_CONFIG_DIR } else { Join-Path $UserProfile '.claude' }
            return (Join-Path $HomeDir 'skills')
        }
        'Grok' {
            $HomeDir = if ($env:GROK_HOME) { $env:GROK_HOME } else { Join-Path $UserProfile '.grok' }
            return (Join-Path $HomeDir 'skills')
        }
        'Kimi' {
            $HomeDir = if ($env:KIMI_CODE_HOME) { $env:KIMI_CODE_HOME } else { Join-Path $UserProfile '.kimi-code' }
            return (Join-Path $HomeDir 'skills')
        }
        'Antigravity' {
            $HomeDir = if ($env:ANTIGRAVITY_CONFIG_DIR) { $env:ANTIGRAVITY_CONFIG_DIR } else { Join-Path (Join-Path $UserProfile '.gemini') 'config' }
            return (Join-Path $HomeDir 'skills')
        }
        'Hermes' {
            if ($env:HERMES_HOME) { return (Join-Path $env:HERMES_HOME 'skills') }
            $LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath('LocalApplicationData') }
            return (Join-Path (Join-Path $LocalAppData 'hermes') 'skills')
        }
        default { throw "Unknown AI provider: $Name" }
    }
}

$Selected = if ($Provider -eq 'All') {
    @('Codex', 'Claude', 'Grok', 'Kimi', 'Hermes', 'Antigravity')
} else {
    @($Provider)
}

$SkillDirs = @(Get-ChildItem -LiteralPath $SkillsSource -Directory -Force | Sort-Object Name)
if ($SkillDirs.Count -eq 0) {
    throw "No skills found in $SkillsSource"
}

$LocalAppDataRoot = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath('LocalApplicationData') }
$UabsLedgerRoot = Join-Path $LocalAppDataRoot 'Ultimate-AI-Starter-Bundle\managed-skills'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

foreach ($Name in $Selected) {
    $SkillsRoot = [IO.Path]::GetFullPath((Get-ProviderSkillsRoot -Name $Name))
    New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null
    if (Test-ReparsePoint -Path $SkillsRoot) {
        throw "Refusing provider skills directory that is a reparse point: $SkillsRoot"
    }

    $UpdatedDigests = @{}
    foreach ($SkillDir in $SkillDirs) {
        $SkillName = $SkillDir.Name
        $Target = Join-Path $SkillsRoot $SkillName
        $Stage = Join-Path $SkillsRoot ('.' + $SkillName + '.stage-' + [Guid]::NewGuid().ToString('N'))
        $Backup = Join-Path $SkillsRoot ('.' + $SkillName + '.backup-' + [Guid]::NewGuid().ToString('N'))

        if ((Test-Path -LiteralPath $Target) -and (Test-ReparsePoint -Path $Target)) {
            throw "Refusing existing skill target that is a reparse point: $Target"
        }

        $MovedExisting = $false
        try {
            Copy-Item -LiteralPath $SkillDir.FullName -Destination $Stage -Recurse
            if ($SkillName -eq 'skyrim-forge' -and (Test-Path -LiteralPath $InstallationDescriptorPath -PathType Leaf)) {
                Copy-Item -LiteralPath $InstallationDescriptorPath -Destination (Join-Path $Stage 'INSTALLATION.json') -Force
            }
            if (Test-Path -LiteralPath $Target) {
                Move-Item -LiteralPath $Target -Destination $Backup
                $MovedExisting = $true
            }
            try {
                Move-Item -LiteralPath $Stage -Destination $Target
            } catch {
                if ($MovedExisting -and -not (Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $Backup)) {
                    Move-Item -LiteralPath $Backup -Destination $Target
                    $MovedExisting = $false
                }
                throw
            }
            if (Test-Path -LiteralPath $Backup) {
                Remove-Item -LiteralPath $Backup -Recurse -Force
                $MovedExisting = $false
            }
            $UpdatedDigests[$SkillName] = Get-TreeDigest -Path $Target
        } finally {
            Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
            if ($MovedExisting -and -not (Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $Backup)) {
                Move-Item -LiteralPath $Backup -Destination $Target -ErrorAction SilentlyContinue
            }
            Remove-Item -LiteralPath $Backup -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    # Parallel-development bridge: if Ultimate-AI-Starter-Bundle's managed-skill
    # ledger is present on this machine, record the updated digests for the
    # Forge-installed Skyrim skills so the bundle's doctor recognizes them.
    $LedgerPath = Join-Path $UabsLedgerRoot ($Name.ToLowerInvariant() + '.json')
    if (Test-Path -LiteralPath $LedgerPath -PathType Leaf) {
        try {
            $Ledger = [IO.File]::ReadAllText($LedgerPath) | ConvertFrom-Json
            if ($Ledger -and $Ledger.skills) {
                foreach ($Entry in @($Ledger.skills)) {
                    if ($UpdatedDigests.ContainsKey([string]$Entry.name)) {
                        $Entry.digest = [string]$UpdatedDigests[[string]$Entry.name]
                    }
                }
                [IO.File]::WriteAllText($LedgerPath, (($Ledger | ConvertTo-Json -Depth 10) + "`n"), $Utf8NoBom)
            }
        } catch {}
    }

    Write-Host ('{0}: installed {1} Skyrim pack skills -> {2}' -f $Name, $SkillDirs.Count, $SkillsRoot) -ForegroundColor Green
}

if ($WithHouseCarl) {
    $SetupHc = Join-Path $SkillsSource 'housecarl\scripts\Setup-HouseCarl.ps1'
    if (Test-Path -LiteralPath $SetupHc -PathType Leaf) {
        & $SetupHc
    }
}
