# Firmar la app de forma simple (self-signed para pruebas)

> Esto es para **pruebas internas**. Con self-signed, Windows seguirá mostrando
> SmartScreen la primera vez salvo que instales el certificado en raíz confiable
> (paso 3). Para producción sin avisos usa Azure Trusted Signing o un OV
> (Sectigo/SSL.com) — el `.iss` y el workflow ya están preparados, solo cambia
> el `SignTool`/secret.

## 1. Crear el certificado (una vez, en tu PC)

```powershell
$cert = New-SelfSignedCertificate -Type CodeSigningCert `
  -Subject "CN=OdooPrinter Test" -CertStoreLocation Cert:\CurrentUser\My
$pass = ConvertTo-SecureString "1234" -AsPlainText -Force
Export-PfxCertificate $cert C:\certs\test.pfx -Password $pass
```

## 2. Firmar a mano (prueba local)

```powershell
signtool sign /f C:\certs\test.pfx /p 1234 /fd SHA256 `
  /tr http://timestamp.digicert.com /td SHA256 `
  dist\odoo-epos-bridge\odoo-epos-bridge.exe
signtool sign /f C:\certs\test.pfx /p 1234 /fd SHA256 `
  /tr http://timestamp.digicert.com /td SHA256 `
  Output\OdooPrinter-Setup-1.0.0.exe
signtool verify /pa Output\OdooPrinter-Setup-1.0.0.exe
```

## 3. Quitar el aviso en PCs de prueba (admin)

```powershell
Import-PfxCertificate C:\certs\test.pfx Cert:\LocalMachine\Root
```

## 4. Firma automática en CI

1. Convierte el pfx a base64: `[Convert]::ToBase64String([IO.File]::ReadAllBytes("C:\certs\test.pfx"))`
2. GitHub repo → Settings → Secrets → Actions → añade `WINDOWS_SIGN_PFX_B64` y `WINDOWS_SIGN_PASSWORD`.
3. El workflow firma el bridge EXE y el `Setup.exe` solo si existen esos secrets; si no, publica unsigned para pruebas.

## 5. Firmar desde Inno directamente (alternativa)

En Inno Compiler: Tools → Configure Sign Tools → `signtool=signtool sign /f C:\certs\test.pfx /p 1234 /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 $f`,
y descomenta `;SignTool=signtool` en `installer/odoo-printer.iss`.
