# Crowd Edge Cloud – Detección de Aglomeraciones (Simulada)

Proyecto académico que demuestra una arquitectura Fog + Serverless en GCP para ingestar y procesar eventos simulados de cámaras de borde. **No** incluye entrenamiento ni visión computacional real; otro integrante desarrollará el modelo y la detección real. Aquí nos enfocamos en la arquitectura, el flujo de eventos y la infraestructura como código.

## Arquitectura
- **Fog/Edge**: script Python (`fog/edge_app.py`) que genera eventos simulados y los envía vía HTTP. Mantiene un buffer local ante fallos de red.
- **Ingesta (Cloud Run)**: servicio FastAPI (`services/ingest/main.py`) que valida payloads y los publica en Pub/Sub.
- **Bus de eventos (Pub/Sub)**: topic `fog-events` para desacoplar ingesta y procesamiento.
- **Procesamiento (Cloud Functions 2nd gen)**: función (`functions/processor/main.py`) activada por Pub/Sub que aplica idempotencia, guarda estado por cámara y persiste eventos en Firestore.
- **BaaS (Firestore)**: almacenamiento nativo para eventos y estado de cámaras.
- **Dashboard/Analítica**: queries de ejemplo (`dashboard/queries.sql`) para explotar datos en BigQuery/Looker Studio.
- **CI/CD**: pipeline en Cloud Build (`ci/cloudbuild.yaml`) que aplica Pulumi, construye la imagen, despliega Cloud Run y la función.

## Flujo de datos en tiempo real
1) El fog simula eventos con `people_count`, tipo de evento y cámara.
2) Envía HTTP `POST /events` al servicio Cloud Run.
3) Cloud Run publica en Pub/Sub (`fog-events`) y registra logs estructurados.
4) Pub/Sub activa la Cloud Function, que asegura idempotencia y persiste en Firestore.
5) Los datos pueden exportarse a BigQuery para dashboards usando las consultas de ejemplo.

## Justificación de diseño (Cloud Architecting)
- **Desac acoplamiento**: Pub/Sub separa ingestión y procesamiento, permitiendo múltiples consumidores futuros (alertas, ML, dashboards).
- **Escalabilidad y HA**: Cloud Run y Cloud Functions escalan automáticamente según carga; Pub/Sub y Firestore son gestionados y regionales.
- **Persistencia y resiliencia**: Firestore almacena estado y eventos; el buffer local en el fog evita pérdida temporal de datos.
- **Rapidez de implementación**: Infraestructura declarada con Pulumi, imágenes ligeras en Python, pipeline de Cloud Build lista.
- **Seguridad básica**: Cuenta de servicio dedicada para Cloud Run con permiso mínimo `roles/datastore.user`; invocación pública controlada.

## Cómo ejecutar la demo
Requisitos: `pulumi`, `gcloud` autenticado contra el proyecto `fog-serverless`, Docker y Python 3.11.

1. **Infraestructura con Pulumi**
   ```bash
   cd crowd-edge-cloud/infra
   pulumi stack init dev  # una sola vez
   pulumi up --yes
   ```
2. **Construir y desplegar ingesta (Cloud Run)**
   ```bash
   cd ..
   docker build -t gcr.io/fog-serverless/fog-ingestion:latest services/ingest
   docker push gcr.io/fog-serverless/fog-ingestion:latest
   gcloud run deploy fog-ingestion \
     --image=gcr.io/fog-serverless/fog-ingestion:latest \
     --region=us-central1 --allow-unauthenticated --project=fog-serverless
   ```
3. **Desplegar función de procesamiento**
   ```bash
   gcloud functions deploy fog-processor \
     --gen2 --region=us-central1 --project=fog-serverless \
     --runtime=python311 --entry-point=process_event \
     --trigger-topic=fog-events --source=functions/processor
   ```
4. **Ejecutar simulador Fog**
   ```bash
   cd fog
   pip install -r ../services/ingest/requirements.txt  # para requests/fastapi deps reutilizadas
   python edge_app.py  # asegurarse de poner la URL real de Cloud Run en config.yaml
   ```
5. **Dashboard**
   - Exporta Firestore a BigQuery o ingesta directa a un dataset `fog_analytics`.
   - Usa las consultas en `dashboard/queries.sql` en BigQuery o Looker Studio.

## Consideraciones
- Eventos actualmente simulados; el modelo de detección real será integrado más adelante.
- No se envía video a la nube ni se realiza reconocimiento facial.
- Código comentado en español y orientado a un despliegue rápido para demos académicas.
