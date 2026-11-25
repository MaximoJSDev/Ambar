param(
    [Parameter(Mandatory = $true)]
    [uri]$ApiUrl
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$generatedConfig = Join-Path $root "frontend\src\api_config.py"
$flet = Join-Path $root "backend\venv\Scripts\flet.exe"

if ($ApiUrl.Scheme -ne "https" -or $ApiUrl.Query -or $ApiUrl.Fragment) {
    throw "La URL del servidor debe ser una URL HTTPS sin parámetros ni fragmento."
}
if (Test-Path -LiteralPath $generatedConfig) {
    throw "Ya existe frontend\src\api_config.py; no se sobrescribió."
}
if (-not (Test-Path -LiteralPath $flet)) {
    throw "No se encontró backend\venv\Scripts\flet.exe. Instala las dependencias de frontend primero."
}

$url = $ApiUrl.AbsoluteUri.TrimEnd("/")
$pythonLiteral = $url.Replace("\", "\\").Replace('"', '\"')
$utf8WithoutBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText(
    $generatedConfig,
    "API_URL = `"$pythonLiteral`"$([Environment]::NewLine)from ambar_common.validators import MAX_CLOUDINARY_FREE_PDF_MB as PDF_MAX_MB$([Environment]::NewLine)",
    $utf8WithoutBom
)

Push-Location (Join-Path $root "frontend")
try {
    & $flet build windows . --product Ambar --artifact Ambar `
        --output (Join-Path $root "dist\Ambar") --yes
    if ($LASTEXITCODE -ne 0) {
        throw "Falló la compilación de Ambar para Windows."
    }
} finally {
    Pop-Location
    Remove-Item -LiteralPath $generatedConfig -Force
}
