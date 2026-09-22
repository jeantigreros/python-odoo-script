# Instalación Windows (setup.exe)

Ya no se instala a mano con `install_windows_service.ps1` (se conserva solo
como referencia). El flujo actual es:

1. Tag `git tag v1.0.1 && git push --tags` (o dispatch manual con versión).
2. CI (`build-windows-exe.yml`): tests → PyInstaller **onedir** → `vpk pack`
   (feed Velopack) → Inno Setup → `Output/OdooPrinter-Setup-1.0.1.exe` →
   GitHub Release con `Setup.exe` + `Releases/*`.
3. En el PC del cliente: ejecutar el `Setup.exe` **como administrador**.
   El wizard pregunta **IP** (ej. `0.0.0.0` o `192.168.18.92`) y **nombre de
   impresora** (ej. `POS-80`), escribe `%ProgramData%\OdooPrinter\config.ini`,
   instala el servicio `OdooPrinter` con NSSM y lo arranca.
4. Verificar: `http://<IP>:5000/health` → `{"status":"ok",...}`.
5. Reconfigurar después: menú inicio → "Reconfigurar IP e impresora".

## Auto-updater silencioso

El bridge lleva Velopack integrado (`main.py: check_for_updates_once`):
check al minuto de arrancar + cada 4h contra `update_url` del config
(por defecto, la Release de GitHub). Descarga silenciosa y aplica al
reiniciar el servicio. La config vive en `%ProgramData%`, no se pierde.

## Firma (pruebas)

Ver `installer/SIGNING.md`: self-signed con `signtool` + importar el PFX en
`Cert:\LocalMachine\Root` de cada PC de prueba. Para producción, mismos pasos
con Azure Trusted Signing o certificado OV vía secrets `WINDOWS_SIGN_PFX_B64`.
