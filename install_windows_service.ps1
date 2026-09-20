param(
    [string]$ServiceName = "OdooPrinter",
    [string]$DisplayName = "Odoo Printer",
    [string]$Description = "Odoo POS ePOS receipt bridge service",
    [switch]$StartService
)

$ErrorActionPreference = "Stop"

$exePath = Join-Path $PSScriptRoot "odoo-epos-bridge.exe"
$nssmPath = Join-Path $PSScriptRoot "nssm.exe"

if (-not (Test-Path $exePath)) {
    throw "Executable not found at $exePath. Make sure the bundle was extracted from the release ZIP."
}

if (-not (Test-Path $nssmPath)) {
    throw "NSSM was not found at $nssmPath. Download the release ZIP and extract it before running this script."
}

Write-Host "Installing service '$ServiceName' using NSSM..."

$serviceExists = Get-CimInstance Win32_Service -Filter "Name = '$ServiceName'" -ErrorAction SilentlyContinue
if ($serviceExists) {
    Write-Host "Service '$ServiceName' already exists. Removing the existing service first."
    & $nssmPath remove $ServiceName confirm
}

& $nssmPath install $ServiceName $exePath
if ($LASTEXITCODE -ne 0) {
    throw "nssm install failed for '$ServiceName'."
}

& $nssmPath set $ServiceName DisplayName $DisplayName
& $nssmPath set $ServiceName Description $Description
& $nssmPath set $ServiceName AppDirectory $PSScriptRoot
& $nssmPath set $ServiceName Start SERVICE_AUTO_START

if ($StartService) {
    Write-Host "Starting service '$ServiceName'..."
    & $nssmPath start $ServiceName
    if ($LASTEXITCODE -ne 0) {
        throw "nssm start failed for '$ServiceName'."
    }
}

Write-Host "Service '$ServiceName' is configured."
Write-Host "Use: nssm start $ServiceName"
Write-Host "Use: Get-Service -Name $ServiceName | Select-Object Name,Status,StartType"
