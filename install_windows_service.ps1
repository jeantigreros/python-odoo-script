param(
    [string]$ServiceName = "OdooPrint",
    [string]$DisplayName = "Odoo Printer",
    [string]$Description = "Odoo POS ePOS receipt bridge service",
    [string]$PrinterName = "",
    [switch]$AskPrinter,
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

# Determine printer name
if ($AskPrinter) {
    $PrinterName = Read-Host "Enter printer name (example: POS-80)"

    if ([string]::IsNullOrWhiteSpace($PrinterName)) {
        throw "Printer name cannot be empty."
    }
}
elseif ([string]::IsNullOrWhiteSpace($PrinterName)) {
    $PrinterName = "POS-80"
}

Write-Host ""
Write-Host "Installing service '$ServiceName' using NSSM..."
Write-Host "Printer name: $PrinterName"
Write-Host ""

$serviceExists = Get-CimInstance Win32_Service -Filter "Name = '$ServiceName'" -ErrorAction SilentlyContinue

if ($serviceExists) {
    Write-Host "Service '$ServiceName' already exists. Removing the existing service first."
    & $nssmPath remove $ServiceName confirm

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove existing service '$ServiceName'."
    }
}

# Install service
& $nssmPath install $ServiceName $exePath

if ($LASTEXITCODE -ne 0) {
    throw "NSSM install failed for '$ServiceName'."
}

# Configure service
& $nssmPath set $ServiceName DisplayName $DisplayName
& $nssmPath set $ServiceName Description $Description
& $nssmPath set $ServiceName AppDirectory $PSScriptRoot
& $nssmPath set $ServiceName Start SERVICE_AUTO_START

# Configure printer environment variable
$environmentValue = "POS_PRINTER_NAME=$PrinterName"

Write-Host "Setting printer environment variable:"
Write-Host "  $environmentValue"

& $nssmPath set $ServiceName AppEnvironmentExtra $environmentValue

if ($LASTEXITCODE -ne 0) {
    throw "Failed to configure POS_PRINTER_NAME."
}

# Optionally start service
if ($StartService) {
    Write-Host "Starting service '$ServiceName'..."

    & $nssmPath start $ServiceName

    if ($LASTEXITCODE -ne 0) {
        throw "NSSM start failed for '$ServiceName'."
    }
}

Write-Host ""
Write-Host "Service '$ServiceName' is configured."
Write-Host "Printer: $PrinterName"
Write-Host ""
Write-Host "Start manually:"
Write-Host "  nssm start $ServiceName"
Write-Host ""
Write-Host "Check service:"
Write-Host "  Get-Service -Name $ServiceName"

