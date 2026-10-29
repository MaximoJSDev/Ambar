$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $root

function ConvertTo-DotEnvValue([string]$value) {
    return '"' + $value.Replace('\', '\\').Replace('"', '\"') + '"'
}

function Read-RequiredValue([string]$prompt) {
    while ($true) {
        $value = Read-Host $prompt
        if (-not [string]::IsNullOrWhiteSpace($value)) {
            return $value.Trim()
        }
        Write-Host "Este dato es obligatorio." -ForegroundColor Yellow
    }
}

Write-Host "=== Ambar: inicio y configuración ===" -ForegroundColor Cyan

$pythonLauncher = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pythonLauncher) {
    & $pythonLauncher.Source -3 -c "import sys; print(sys.version)"
    if ($LASTEXITCODE -ne 0) {
        throw "No se encontró Python 3. Instálalo desde https://www.python.org/downloads/ y vuelve a ejecutar este archivo."
    }
    $pythonCommand = $pythonLauncher.Source
    $pythonArguments = @("-3")
} else {
    $pythonCommand = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (-not $pythonCommand) {
        throw "No se encontró Python. Instálalo desde https://www.python.org/downloads/ y vuelve a ejecutar este archivo."
    }
    & $pythonCommand --version
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo ejecutar Python."
    }
    $pythonArguments = @()
}

$venvPython = Join-Path $root "backend\venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "Creando el entorno privado del proyecto..."
    & $pythonCommand @pythonArguments -m venv (Join-Path $root "backend\venv")
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el entorno virtual de backend."
    }
}

Write-Host "Instalando o comprobando dependencias..."
Push-Location (Join-Path $root "backend")
try {
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la instalación de dependencias del backend."
    }
} finally {
    Pop-Location
}
Push-Location (Join-Path $root "frontend")
try {
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la instalación de dependencias del frontend."
    }
} finally {
    Pop-Location
}

$envFile = Join-Path $root "backend\.env"
$createdEnv = -not (Test-Path -LiteralPath $envFile)
if ($createdEnv) {
    Write-Host "`nConfiguración de MySQL (el servidor MySQL debe estar instalado y en ejecución)." -ForegroundColor Yellow
    $dbHost = Read-Host "Servidor MySQL [127.0.0.1]"
    if ([string]::IsNullOrWhiteSpace($dbHost)) { $dbHost = "127.0.0.1" }
    $dbPort = Read-Host "Puerto MySQL [3306]"
    if ([string]::IsNullOrWhiteSpace($dbPort)) { $dbPort = "3306" }
    if ($dbPort -notmatch '^\d+$' -or [int]$dbPort -lt 1 -or [int]$dbPort -gt 65535) {
        throw "El puerto debe ser un número entre 1 y 65535."
    }
    $dbUser = Read-RequiredValue "Usuario MySQL"
    $securePassword = Read-Host "Contraseña MySQL" -AsSecureString
    $passwordPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
    try {
        $dbPassword = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($passwordPointer)
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($passwordPointer)
    }

    $secretBytes = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    try {
        $random.GetBytes($secretBytes)
    } finally {
        $random.Dispose()
    }
    $jwtSecret = ([BitConverter]::ToString($secretBytes)).Replace("-", "").ToLowerInvariant()

    $envLines = @(
        "DB_HOST=$(ConvertTo-DotEnvValue $dbHost)"
        "DB_PORT=$dbPort"
        "DB_USER=$(ConvertTo-DotEnvValue $dbUser)"
        "DB_PASSWORD=$(ConvertTo-DotEnvValue $dbPassword)"
        "DB_NAME=ambar_escolar"
        "JWT_SECRET=$jwtSecret"
    )
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText(
        $envFile,
        ($envLines -join [Environment]::NewLine) + [Environment]::NewLine,
        $utf8WithoutBom
    )
    $dbPassword = $null
    $securePassword = $null
}

Write-Host "`nComprobando e inicializando la base de datos si aún no existe..."
$env:AMBAR_PROJECT_ROOT = $root
$env:AMBAR_ENV_FILE = $envFile
$databaseSetup = @'
import os
from pathlib import Path

from dotenv import dotenv_values
import pymysql

root = Path(os.environ["AMBAR_PROJECT_ROOT"])
config = dotenv_values(os.environ["AMBAR_ENV_FILE"])
connection = pymysql.connect(
    host=config["DB_HOST"],
    port=int(config.get("DB_PORT", "3306")),
    user=config["DB_USER"],
    password=config["DB_PASSWORD"],
    charset="utf8mb4",
    autocommit=True,
)
try:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM information_schema.schemata WHERE schema_name = %s",
            ("ambar_escolar",),
        )
        exists = cursor.fetchone()[0] > 0
        if exists:
            print("La base ambar_escolar ya existe; no se modificó.")
        else:
            script = (root / "ambar-db.sql").read_text(encoding="utf-8")
            statements = (
                "\n".join(line for line in part.splitlines()
                          if not line.lstrip().startswith("--")).strip()
                for part in script.split(";")
            )
            for statement in statements:
                if statement:
                    cursor.execute(statement)
            print("Base de datos y tablas creadas desde ambar-db.sql.")
            print("AMBAR_DATABASE_CREATED=1")
        cursor.execute(
            "SELECT COUNT(*) FROM ambar_escolar.catalogo_codigos_postales"
        )
        if cursor.fetchone()[0] == 0:
            print("AMBAR_POSTAL_CATALOG_EMPTY=1")
finally:
    connection.close()
'@
$databaseOutput = $databaseSetup | & $venvPython -
if ($LASTEXITCODE -ne 0) {
    throw "No se pudo preparar MySQL. Comprueba que el servidor esté encendido y que el usuario pueda crear la base ambar_escolar."
}
$databaseOutput | ForEach-Object { Write-Host $_ }
$newDatabase = $databaseOutput -contains "AMBAR_DATABASE_CREATED=1"
$postalCatalogEmpty = $databaseOutput -contains "AMBAR_POSTAL_CATALOG_EMPTY=1"

if ($postalCatalogEmpty) {
    $postalCatalogFile = Join-Path $root "SERVICIO_POSTAL_MEXICANO.txt"
    if (-not (Test-Path -LiteralPath $postalCatalogFile -PathType Leaf)) {
        throw "La tabla de códigos postales está vacía y no se encontró SERVICIO_POSTAL_MEXICANO.txt en la raíz del proyecto."
    }

    Write-Host "`nPrimera inicialización del catálogo postal local..."
    & $venvPython -m backend.importar_catalogo_cp $postalCatalogFile
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo importar el catálogo postal. Revisa la conexión a MySQL y el archivo SERVICIO_POSTAL_MEXICANO.txt."
    }
}

if ($newDatabase) {
    Write-Host "`nCrea el usuario de Secretaría para iniciar sesión." -ForegroundColor Yellow
    $email = Read-RequiredValue "Correo de prueba"
    $firstName = Read-RequiredValue "Nombre(s)"
    $lastName = Read-RequiredValue "Apellidos"
    & $venvPython -m backend.seed --correo $email --nombres $firstName --apellidos $lastName
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo crear el usuario inicial de Secretaría."
    }
}

$backendProcess = Start-Process -FilePath "powershell.exe" `
    -WorkingDirectory $root `
    -ArgumentList @(
        "-NoExit",
        "-NoProfile",
        "-Command",
        "& '$venvPython' -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload"
    ) `
    -PassThru

$healthy = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/salud" -TimeoutSec 2
        if ($health.estado -eq "ok") {
            $healthy = $true
            break
        }
    } catch {
        if ($backendProcess.HasExited) {
            break
        }
    }
}
if (-not $healthy) {
    throw "El backend no inició correctamente. Revisa la ventana del backend y backend.log."
}

Write-Host "`nBackend listo en http://127.0.0.1:8000" -ForegroundColor Green
Write-Host "Documentación de la API: http://127.0.0.1:8000/docs"
Write-Host "Iniciando la aplicación de escritorio; cierra esta ventana para salir del frontend."
Push-Location (Join-Path $root "frontend")
try {
    & (Join-Path $root "backend\venv\Scripts\flet.exe") run -d
    if ($LASTEXITCODE -ne 0) {
        throw "El frontend terminó con un error. Revisa frontend.log."
    }
} finally {
    Pop-Location
}
