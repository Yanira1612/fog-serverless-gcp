#!/usr/bin/env pwsh

# Script de despliegue manual con Pulumi para evitar restricciones IAM en Cloud Build.
# Requisitos:
# - Tener gcloud autenticado en el proyecto fog-serverless
# - Python y pip disponibles
# - Pulumi instalado (o se instalará vía pip en el entorno actual)


# Script de despliegue manual con Pulumi (PowerShell)

$STACK = $env:STACK
if (-not $STACK) { $STACK = "dev" }

$API_KEY = $env:INGEST_API_KEY
if (-not $API_KEY) { $API_KEY = "demo-api-key" }

Set-Location "$PSScriptRoot/../infra"

# Backend local
pulumi login "file://$PWD/.pulumi-state"

# Seleccionar o crear stack
pulumi stack select $STACK -ErrorAction SilentlyContinue
if ($LASTEXITCODE -ne 0) {
    pulumi stack init $STACK
}

# Configuración
pulumi config set gcp:project fog-serverless
pulumi config set gcp:region us-central1
pulumi config set ingestApiKey $API_KEY --secret

# Dependencias
python -m pip install -r requirements.txt

# Aplicar cambios
pulumi up --yes

Write-Host "Pulumi finalizado en stack $STACK"
