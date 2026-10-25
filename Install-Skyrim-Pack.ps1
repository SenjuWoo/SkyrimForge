# Install or check the Forge-owned Skyrim pack while preserving personal and independently managed skills.
[CmdletBinding()]
param(
    [ValidateSet('All','Codex','Claude','Grok','Kimi','Hermes','Antigravity')][string]$Provider='All',
    [string[]]$Skills,
    [switch]$WithHouseCarl,
    [switch]$Check
)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot 'scripts\Provider-Skills.ps1')
$source=Join-Path $PSScriptRoot 'integrations\skyrim-pack\skills'
$descriptor=Join-Path $PSScriptRoot 'INSTALLATION.json'
$selected=if($Provider -eq 'All') { @('Codex','Claude','Grok','Kimi','Hermes','Antigravity') } else { @($Provider) }
foreach($name in $selected) {
    Sync-ForgeProviderSkills -Provider $name -Source $source -Descriptor $descriptor -Skills $Skills -Check:$Check
    if ($name -eq 'Hermes') {
        $homeRoot = Split-Path -Parent (Get-ForgeProviderSkillsRoot 'Hermes')
        $profileSkills = Join-Path $homeRoot 'profiles\skyrim\skills'
        if (Test-Path -LiteralPath $profileSkills -PathType Container) {
            Sync-ForgeProviderSkills -Provider $name -Source $source -Descriptor $descriptor -Skills $Skills -SkillsRoot $profileSkills -Check:$Check
        }
    }
}
if($WithHouseCarl -and -not $Check) {
    & (Join-Path $PSScriptRoot 'Install-HouseCarl.ps1')
}
