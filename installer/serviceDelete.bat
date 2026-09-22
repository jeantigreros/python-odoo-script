@echo off
REM Inno [UninstallRun]: stop + remove the NSSM service.
setlocal
net stop OdooPrinter >nul 2>&1
if exist "%~dp0nssm.exe" "%~dp0nssm.exe" remove OdooPrinter confirm >nul 2>&1
sc delete OdooPrinter >nul 2>&1
echo OdooPrinter service removed. Config in %%ProgramData%%\OdooPrinter kept.
