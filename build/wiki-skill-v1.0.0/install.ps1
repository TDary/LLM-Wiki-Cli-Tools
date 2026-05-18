param(
    [switch]$Local,
    [string]$Dir = "$env:USERPROFILE\.local\bin",
    [string]$Skill,
    [string]$Agents
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistDir = Join-Path $ScriptDir "dist"

$BinName = "wiki-tools.exe"
$Binary = if ($Local) { "wiki-tools-local-windows-amd64.exe" } else { "wiki-tools-windows-amd64.exe" }
$Src = Join-Path $DistDir $Binary

if (-not (Test-Path $Src)) {
    Write-Host "Binary not found: $Src"
    Write-Host "Available:"
    Get-ChildItem $DistDir | ForEach-Object { Write-Host "  $($_.Name)" }
    exit 1
}

# Ensure target dir
New-Item -ItemType Directory -Force -Path $Dir | Out-Null
$Dst = Join-Path $Dir $BinName
Copy-Item -Force $Src $Dst

Write-Host "Installed: $Dst"

# PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$Dir*") {
    [Environment]::SetEnvironmentVariable("Path", "$userPath;$Dir", "User")
    $env:Path = "$env:Path;$Dir"
    Write-Host ""
    Write-Host "Added to user PATH (new terminals will pick it up)."
}

# Skill
if ($Skill) {
    $SkillSrc = Join-Path $ScriptDir "skills\wiki.md"
    $SkillDst = Join-Path $Skill ".claude\skills\wiki.md"
    New-Item -ItemType Directory -Force -Path (Split-Path $SkillDst -Parent) | Out-Null
    Copy-Item -Force $SkillSrc $SkillDst
    Write-Host "Skill installed: $SkillDst"
}

# AGENTS.md
if ($Agents) {
    $AgentsSrc = Join-Path $ScriptDir "platform-adapters\AGENTS.md"
    $AgentsDst = Join-Path $Agents "AGENTS.md"
    Copy-Item -Force $AgentsSrc $AgentsDst
    Write-Host "AGENTS.md installed: $AgentsDst"
}

Write-Host ""
Write-Host "Done. Try: wiki-tools init ~\my-wiki 'My Domain'"
