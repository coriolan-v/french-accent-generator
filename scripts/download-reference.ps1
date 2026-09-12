$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$assets = Join-Path $projectRoot "assets"
New-Item -ItemType Directory -Path $assets -Force | Out-Null

foreach ($reference in @("french23", "french8")) {
    $destination = Join-Path $assets "$reference.mp3"
    Invoke-WebRequest -Uri "https://accent.gmu.edu/audio/$reference.mp3" -OutFile $destination
    Write-Host "Downloaded $reference to $destination"
}

Write-Host "Source: Speech Accent Archive, french23 and french8, CC BY-NC-SA 4.0"
