@echo off
REM Called by Inno Setup AFTER files are copied, with admin rights.
REM Usage: serviceRegister.bat "IP" "PrinterName"
setlocal
set BRIDGE_IP=%~1
set PRINTER_NAME=%~2
if "%BRIDGE_IP%"=="" set BRIDGE_IP=0.0.0.0
if "%PRINTER_NAME%"=="" set PRINTER_NAME=POS-80

set APPDIR=%~dp0
set NSSM=%APPDIR%nssm.exe
set EXE=%APPDIR%odoo-epos-bridge.exe
set DATADIR=%ProgramData%\OdooPrinter
if not exist "%DATADIR%" mkdir "%DATADIR%"

REM Persist config outside {app} so Velopack updates don't wipe it.
(
  echo [bridge]
  echo host=%BRIDGE_IP%
  echo port=5000
  echo printer_name=%PRINTER_NAME%
  echo printer_width_dots=576
  echo raster_scale_x=1.0
  echo raster_scale_y=1.5
  echo end_blank_lines=2
) > "%DATADIR%\config.ini"

if not exist "%NSSM%" (
  echo ERROR: nssm.exe not found in %APPDIR%
  exit /b 1
)
if not exist "%EXE%" (
  echo ERROR: %EXE% not found
  exit /b 1
)

net stop OdooPrinter >nul 2>&1
"%NSSM%" remove OdooPrinter confirm >nul 2>&1

"%NSSM%" install OdooPrinter "%EXE%"
"%NSSM%" set OdooPrinter DisplayName "OdooPrinter"
"%NSSM%" set OdooPrinter Description "Odoo POS ePOS receipt bridge"
"%NSSM%" set OdooPrinter AppDirectory "%APPDIR%"
"%NSSM%" set OdooPrinter Start SERVICE_AUTO_START
"%NSSM%" set OdooPrinter AppStdout "%DATADIR%\bridge.log"
"%NSSM%" set OdooPrinter AppStderr "%DATADIR%\bridge.log"
"%NSSM%" set OdooPrinter AppStdoutCreationDisposition 4
"%NSSM%" set OdooPrinter AppStderrCreationDisposition 4
"%NSSM%" set OdooPrinter AppRotateFiles 1
"%NSSM%" set OdooPrinter AppRotateOnline 1
"%NSSM%" set OdooPrinter AppRotateBytes 1048576

net start OdooPrinter
echo Service OdooPrinter installed. IP=%BRIDGE_IP% Printer=%PRINTER_NAME%
