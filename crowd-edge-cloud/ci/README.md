# CI/CD con Cloud Build

Pipeline académico para construir/publicar la imagen de ingesta y, opcionalmente, ejecutar Pulumi. El paso de Pulumi está marcado como `allowFailure` para no romper el build si la organización bloquea IAM; puedes desactivarlo con `_RUN_PULUMI=false`.

## Pasos del pipeline (ci/cloudbuild.yaml)
1. **Build**: construye la imagen Docker del servicio de ingesta (`services/ingest`).
2. **Push**: publica la imagen en Artifact Registry `us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest`.
3. **Pulumi (opcional)**: `pulumi up --yes` en `infra/` usando backend local. Si no hay permisos IAM, el build sigue en éxito.
4. **Cloud Function (opcional)**: despliega `fog-processor` (gen2, trigger Pub/Sub) si `_DEPLOY_FUNCTION=true`.

## Ejecutar el pipeline
Desde la raíz del repo:
```bash
gcloud builds submit --config ci/cloudbuild.yaml \
  --substitutions=_INGEST_API_KEY=TU_API_KEY,_STACK=dev,_RUN_PULUMI=true,_DEPLOY_FUNCTION=true
```
- Si quieres omitir Pulumi en Cloud Build: `_RUN_PULUMI=false`.
- Si quieres omitir despliegue de la función: `_DEPLOY_FUNCTION=false`.
- Si tienes permisos IAM adecuados (SA de Cloud Build con roles de despliegue), deja `_RUN_PULUMI=true`.

## Despliegue manual de Pulumi (si omites el paso en Cloud Build)
```bash
cd infra
pulumi login file://$(pwd)/.pulumi-state
pulumi stack select dev || pulumi stack init dev
pulumi config set gcp:project fog-serverless
pulumi config set gcp:region us-central1
pulumi config set ingestApiKey TU_API_KEY
pip install -r requirements.txt
pulumi up --yes
```

O usa el script helper:
```bash
STACK=dev INGEST_API_KEY=TU_API_KEY ./ci/manual-pulumi.sh
```

Requisitos previos:
- Proyecto `fog-serverless` configurado en `gcloud`.
- Artifact Registry y APIs ya habilitadas.
