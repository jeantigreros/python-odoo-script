# Re-run the IP/printer wizard after installation (Start Menu shortcut).
# Edits %ProgramData%\OdooPrinter\config.ini and restarts the service. Admin required.
$ErrorActionPreference = "Stop"

$ini = "$env:ProgramData\OdooPrinter\config.ini"
$currentIp = "0.0.0.0"
$currentPrinter = "POS-80"
if (Test-Path $ini) {
    $content = Get-Content $ini -Raw
    if ($content -match '(?m)^host\s*=\s*(.+)\s*$') { $currentIp = $Matches[1].Trim() }
    if ($content -match '(?m)^printer_name\s*=\s*(.+)\s*$') { $currentPrinter = $Matches[1].Trim() }
}

# Printer picker: list installed printers, default to current.
try {
    $printers = Get-CimInstance Win32_Printer | Select-Object -ExpandProperty Name
} catch { $printers = @() }
if ($printers) {
    Write-Host "Impresoras instaladas:"
    $printers | ForEach-Object { Write-Host "  - $_" }
}

$ip = Read-Host "IP del bridge [$currentIp]"
if ([string]::IsNullOrWhiteSpace($ip)) { $ip = $currentIp }
$printer = Read-Host "Nombre impresora [$currentPrinter]"
if ([string]::IsNullOrWhiteSpace($printer)) { $printer = $currentPrinter }

& "$PSScriptRoot\serviceRegister.bat" $ip $printer
Write-Host "Listo. Comprueba http://$($ip):5000/health"
