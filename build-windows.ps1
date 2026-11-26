param(
    [Parameter(Mandatory = $true)]
    [uri]$ApiUrl
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$sourceDir = Join-Path $root "frontend\src"
$generatedConfig = Join-Path $sourceDir "api_config.py"
$icon = Join-Path $sourceDir "assets\icon.ico"
$flet = Join-Path $root "backend\venv\Scripts\flet.exe"
$python = Join-Path $root "backend\venv\Scripts\python.exe"

if ($ApiUrl.Scheme -ne "https" -or $ApiUrl.Query -or $ApiUrl.Fragment) {
    throw "La URL del servidor debe ser una URL HTTPS sin parámetros ni fragmento."
}
if (Test-Path -LiteralPath $generatedConfig) {
    throw "Ya existe frontend\src\api_config.py; no se sobrescribió."
}
if (-not (Test-Path -LiteralPath $flet)) {
    throw "No se encontró backend\venv\Scripts\flet.exe. Instala las dependencias de frontend primero."
}
if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) {
    throw "No se encontró frontend\src\assets\icon.ico."
}

& $python -c "import PyInstaller"
if ($LASTEXITCODE -ne 0) {
    throw "Instala PyInstaller en backend\venv antes de compilar."
}

$outputDir = Join-Path $root "dist"
$outputExe = Join-Path $outputDir "Ambar.exe"
$workDir = Join-Path $root ("build\ambar-pack-" + [guid]::NewGuid().ToString("N"))
[void] (New-Item -ItemType Directory -Path $workDir)

$url = $ApiUrl.AbsoluteUri.TrimEnd("/")
$pythonLiteral = $url.Replace("\", "\\").Replace('"', '\"')
$utf8WithoutBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText(
    $generatedConfig,
    "API_URL = `"$pythonLiteral`"$([Environment]::NewLine)from ambar_common.validators import MAX_CLOUDINARY_FREE_PDF_MB as PDF_MAX_MB$([Environment]::NewLine)",
    $utf8WithoutBom
)

Push-Location -LiteralPath $workDir
try {
    # Flet Pack administra las carpetas build y dist del directorio de trabajo.
    $entryPoint = Join-Path $sourceDir "main.py"
    $assets = Join-Path $sourceDir "assets"
    # PyInstaller debe localizar ambar_common desde su código fuente.
    & $flet pack $entryPoint --name Ambar --product-name Ambar --icon $icon --add-data "${assets}:assets" `
        "--pyinstaller-build-args=--paths=$root" --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la compilación de Ambar para Windows."
    }
    $packedExe = Join-Path $workDir "dist\Ambar.exe"
    if (-not (Test-Path -LiteralPath $packedExe -PathType Leaf)) {
        throw "Flet Pack terminó sin generar Ambar.exe."
    }
    @'
import sys

from PyInstaller.archive.readers import CArchiveReader

app = CArchiveReader(sys.argv[1])
modules = app.open_embedded_archive("PYZ.pyz").toc
required = {
    "api_config",
    "ambar_common.documents",
    "ambar_common.logging_config",
    "ambar_common.validators",
}
missing = sorted(required - modules.keys())
if missing:
    sys.exit("Modulos ausentes: " + ", ".join(missing))
'@ | & $python - $packedExe
    if ($LASTEXITCODE -ne 0) {
        throw "El ejecutable no incluye todos los módulos requeridos."
    }
    [void] (New-Item -ItemType Directory -Path $outputDir -Force)
    if (Test-Path -LiteralPath $outputExe -PathType Container) {
        throw "Ya existe una carpeta con el nombre destinado a Ambar.exe."
    }
    Move-Item -LiteralPath $packedExe -Destination $outputExe -Force
    Write-Output $outputExe
} finally {
    Pop-Location
    Remove-Item -LiteralPath $generatedConfig -Force
    $resolvedWorkDir = (Resolve-Path -LiteralPath $workDir).ProviderPath
    if ($resolvedWorkDir -eq $workDir) {
        Remove-Item -LiteralPath $resolvedWorkDir -Recurse -Force
    }
}
