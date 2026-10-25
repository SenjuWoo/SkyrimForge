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

function Get-ProviderHome {
    param([Parameter(Mandatory = $true)][string]$Name)
    $UserProfile = [Environment]::GetFolderPath('UserProfile')
    switch ($Name) {
        'Codex'       { if ($env:CODEX_HOME) { return $env:CODEX_HOME }; return (Join-Path $UserProfile '.codex') }
        'Claude'      { if ($env:CLAUDE_CONFIG_DIR) { return $env:CLAUDE_CONFIG_DIR }; return (Join-Path $UserProfile '.claude') }
        'Grok'        { if ($env:GROK_HOME) { return $env:GROK_HOME }; return (Join-Path $UserProfile '.grok') }
        'Kimi'        { if ($env:KIMI_CODE_HOME) { return $env:KIMI_CODE_HOME }; return (Join-Path $UserProfile '.kimi-code') }
        'Antigravity' { if ($env:ANTIGRAVITY_CONFIG_DIR) { return $env:ANTIGRAVITY_CONFIG_DIR }; return (Join-Path (Join-Path $UserProfile '.gemini') 'config') }
        'Hermes' {
            if ($env:HERMES_HOME) { return $env:HERMES_HOME }
            $LocalAppData = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { [Environment]::GetFolderPath('LocalApplicationData') }
            return (Join-Path $LocalAppData 'hermes')
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

foreach ($Name in $Selected) {
    $ProviderHome = [IO.Path]::GetFullPath((Get-ProviderHome -Name $Name))
    $SkillsRoot = Join-Path $ProviderHome 'skills'
    New-Item -ItemType Directory -Force -Path $SkillsRoot | Out-Null
    if (Test-ReparsePoint -Path $SkillsRoot) {
        throw "Refusing provider skills directory that is a reparse point: $SkillsRoot"
    }

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
        } finally {
            Remove-Item -LiteralPath $Stage -Recurse -Force -ErrorAction SilentlyContinue
            if ($MovedExisting -and -not (Test-Path -LiteralPath $Target) -and (Test-Path -LiteralPath $Backup)) {
                Move-Item -LiteralPath $Backup -Destination $Target -ErrorAction SilentlyContinue
            }
            Remove-Item -LiteralPath $Backup -Recurse -Force -ErrorAction SilentlyContinue
        }
    }

    Write-Host ('{0}: installed {1} Skyrim pack skills -> {2}' -f $Name, $SkillDirs.Count, $SkillsRoot) -ForegroundColor Green
}

if ($WithHouseCarl) {
    $SetupHc = Join-Path $SkillsSource 'housecarl\scripts\Setup-HouseCarl.ps1'
    if (Test-Path -LiteralPath $SetupHc -PathType Leaf) {
        & $SetupHc
    }
}
