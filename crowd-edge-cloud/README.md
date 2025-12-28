# Crowd Edge Cloud – Detección de Aglomeraciones (Simulada)

Proyecto académico que demuestra una arquitectura Fog + Serverless en GCP para ingestar y procesar eventos simulados de cámaras de borde. No incluye entrenamiento ni visión computacional real; el foco es la arquitectura, el flujo de eventos y la infraestructura como código.

## Arquitectura
- **Fog/Edge**: script Python (`fog/edge_app.py`) que simula eventos y los envía vía HTTP con API Key. Usa buffer local ante fallos de red.
- **Ingesta (Cloud Run v1)**: servicio Flask (`services/ingest/main.py`) que valida API Key y publica en Pub/Sub.
- **Bus de eventos (Pub/Sub)**: topic `fog-events` para desacoplar ingesta y procesamiento.
- **Procesamiento (Cloud Functions 2nd gen)**: función (`functions/processor/main.py`) activada por Pub/Sub que aplica idempotencia, guarda estado por cámara y persiste eventos en Firestore.
- **BaaS (Firestore)**: almacenamiento nativo para eventos y estado de cámaras.
- **Dashboard/Analítica**: consultas de ejemplo (`dashboard/queries.sql`) y guía (`dashboard/README.md`) para Looker Studio/BigQuery.
- **CI/CD**: pipeline en Cloud Build (`ci/cloudbuild.yaml`) que construye la imagen y ejecuta Pulumi (fuente de verdad de la infraestructura).

## Flujo de datos
1) El fog simula eventos con `people_count`, tipo de evento y cámara; envía `POST /events` con header `X-API-KEY`.
2) Cloud Run valida la API Key, publica en Pub/Sub y registra logs estructurados.
3) Pub/Sub activa la Cloud Function, que asegura idempotencia y persiste en Firestore (`events`, `camera_state`).
4) Los datos se pueden exportar a BigQuery para dashboards usando las consultas de ejemplo.

## Seguridad de ingesta (fog → Cloud Run)
- Autenticación simple por API Key en header `X-API-KEY`.
- La API Key se inyecta como variable de entorno `INGEST_API_KEY` en Cloud Run (definirla con `pulumi config set ingestApiKey <valor>`).
- El fog lee `api_key` desde `fog/config.yaml` y la envía en cada petición.

## Cómo ejecutar la demo
Requisitos: `pulumi`, `gcloud` autenticado contra `fog-serverless`, Docker, Python 3.11.

1. **Construir y publicar la imagen de ingesta**
   ```bash
   cd crowd-edge-cloud
   docker build -t us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest services/ingest
   docker push us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest
   ```
2. **Configurar Pulumi (única fuente de verdad)**
   ```bash
   cd infra
   pulumi stack init dev  # solo la primera vez
   pulumi config set ingestApiKey TU_API_KEY
   pulumi up --yes
   ```
   Pulumi crea/actualiza: topic `fog-events`, suscripción push a `/events` de `fog-ingestion`, Firestore nativo y Cloud Run apuntando a la imagen en Artifact Registry (sin modificar IAM de proyecto).
3. **Desplegar la función de procesamiento**
   ```bash
   gcloud functions deploy fog-processor \
     --gen2 --region=us-central1 --project=fog-serverless \
     --runtime=python311 --entry-point=process_event \
     --trigger-topic=fog-events --source=functions/processor
   ```
4. **Ejecutar el simulador Fog**
   ```bash
   cd fog
   pip install -r requirements.txt
   # Edita config.yaml: endpoint de Cloud Run (cloudRunUrl exportado por Pulumi) y api_key usada en Pulumi
   python edge_app.py
   ```
5. **Visualizar**
   - Consulta la colección `events` en Firestore o expórtala a BigQuery.
   - Usa `dashboard/queries.sql` y `dashboard/README.md` para Looker Studio/BigQuery.

## CI/CD con Cloud Build
- Pipeline en `ci/cloudbuild.yaml`: build → push → `pulumi up --yes`. No modifica IAM a nivel proyecto.
- Ejecución manual: `gcloud builds submit --config ci/cloudbuild.yaml .`

## Consideraciones
- Eventos simulados; el modelo real se integrará después.
_- No se envía video a la nube ni se hace reconocimiento facial._
- Código y comentarios en español, orientado a un despliegue académico y rápido.
