# Crowd Edge Cloud – Detección de Aglomeraciones (Simulada)

Proyecto académico que demuestra una arquitectura Fog + Serverless en GCP para ingestar y procesar eventos **simulados** de cámaras de borde. **No** incluye entrenamiento ni visión computacional real; otro integrante desarrollará esa parte. El foco aquí es la arquitectura, el flujo de eventos y la infraestructura como código.

## Arquitectura
- **Fog/Edge**: script Python (`fog/edge_app.py`) que genera eventos simulados y los envía vía HTTP, con buffer local ante fallos de red.
- **Ingesta (Cloud Run)**: servicio FastAPI (`services/ingest/main.py`) que valida payloads y los publica en Pub/Sub.
- **Bus de eventos (Pub/Sub)**: topic `fog-events` para desacoplar ingesta y procesamiento.
- **Procesamiento (Cloud Functions 2nd gen)**: función (`functions/processor/main.py`) activada por Pub/Sub que aplica idempotencia, guarda estado por cámara y persiste eventos en Firestore.
- **BaaS (Firestore)**: almacenamiento nativo para eventos y estado de cámaras.
- **Dashboard/Analítica**: queries de ejemplo (`dashboard/queries.sql`) para explotar datos en BigQuery/Looker Studio.
- **CI/CD**: pipeline en Cloud Build (`ci/cloudbuild.yaml`) que **solo** construye la imagen en Artifact Registry y ejecuta Pulumi (fuente de verdad de la infraestructura).

## Flujo de datos en tiempo real
1) El fog simula eventos con `people_count`, tipo de evento y cámara.
2) Envía HTTP `POST /events` al servicio Cloud Run.
3) Cloud Run publica en Pub/Sub (`fog-events`) y registra logs estructurados.
4) Pub/Sub activa la Cloud Function, que asegura idempotencia y persiste en Firestore.
5) Los datos pueden exportarse a BigQuery para dashboards usando las consultas de ejemplo.

## Justificación de diseño (Cloud Architecting)
- **Desacoplamiento**: Pub/Sub separa ingestión y procesamiento, permitiendo múltiples consumidores futuros (alertas, ML, dashboards).
- **Escalabilidad y HA**: Cloud Run y Cloud Functions escalan automáticamente según carga; Pub/Sub y Firestore son gestionados y regionales.
- **Persistencia y resiliencia**: Firestore almacena estado y eventos; el buffer local en el fog evita pérdida temporal de datos.
- **Rapidez de implementación**: Infraestructura declarada con Pulumi, imágenes ligeras en Python, pipeline de Cloud Build lista.
- **Seguridad básica**: Cuenta de servicio dedicada para Cloud Run con permiso mínimo `roles/datastore.user`; invocación pública controlada.

## Cómo ejecutar la demo
Requisitos: `pulumi`, `gcloud` autenticado contra el proyecto `fog-serverless`, Docker y Python 3.11.

1. **Construir y publicar la imagen en Artifact Registry**
   ```bash
   cd crowd-edge-cloud
   docker build -t us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest services/ingest
   docker push us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest
   ```
2. **Configurar Pulumi (única fuente de verdad de Cloud Run/Pub/Sub/Firestore)**
   ```bash
   cd infra
   pulumi stack init dev  # solo si es la primera vez
   pulumi config set imageTag latest  # o usa una etiqueta de build específica
   pulumi up --yes
   ```
   Pulumi crea/actualiza: topic `fog-events`, suscripción push hacia `/events` del servicio `fog-ingestion`, cuenta de servicio, Firestore nativo y Cloud Run apuntando a la imagen en Artifact Registry.
3. **Desplegar la función de procesamiento (gcloud)**
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
   # Edita config.yaml y coloca la URL real de Cloud Run exportada por Pulumi (cloud_run_url)
   python edge_app.py
   ```
5. **Dashboard**
   - Exporta Firestore a BigQuery o ingesta directa a un dataset `fog_analytics`.
   - Usa las consultas en `dashboard/queries.sql` en BigQuery o Looker Studio.

## CI/CD con Cloud Build (opcional)
- El pipeline (`ci/cloudbuild.yaml`) construye la imagen en Artifact Registry (tags `latest` y `${BUILD_ID}`), actualiza `imageTag` en Pulumi y ejecuta `pulumi up`. No re-deploya infraestructura fuera de Pulumi.

## Consideraciones
- Eventos actualmente simulados; el modelo de detección real se integrará después.
- No se envía video a la nube ni se realiza reconocimiento facial.
- Código comentado en español y orientado a un despliegue rápido para demos académicas.
