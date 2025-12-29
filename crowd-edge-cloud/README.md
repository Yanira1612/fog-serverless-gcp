# Crowd Edge Cloud – Demo Fog + Serverless en GCP

Proyecto academico que muestra una arquitectura Fog + Serverless para ingestar eventos simulados desde el borde, procesarlos en GCP y exponer metricas basicas para un dashboard.

## Arquitectura (simplificada y coherente)
- **Fog/Edge**: `fog/edge_app.py` simula eventos (o usa camara local), aplica filtrado basico y buffer local ante fallos de red. No se envian videos ni datos pesados.
- **Ingesta (Cloud Run)**: `services/ingest` expone `/events` con API key y publica en Pub/Sub (`fog-events`).
- **Procesamiento (Cloud Functions Gen2 + Pub/Sub)**: `functions/processor` se activa por Pub/Sub, garantiza idempotencia y persiste en Firestore.
- **BaaS (Firestore)**: colecciones `events` y `camera_state`.
- **Analyst/Dashboard (Cloud Run protegido)**: `functions/analyst` expone `/metrics` y `/predict_next` con token simple. `dashboard/index.html` consume esas APIs con el token.
- **Infra como codigo (Pulumi)**: crea Firestore, Pub/Sub y Cloud Run de ingesta/analyst parametrizados por stack.
- **CI/CD (Cloud Build)**: build/push de imagen de ingesta, deploy a Cloud Run (ingesta) y deploy de Cloud Function (procesador). Pulumi se ejecuta fuera del pipeline.

## Despliegue rapido
Requisitos: `gcloud` autenticado, `pulumi`, Docker, Python 3.11.

1. **Configurar Pulumi (infra base)**
   ```bash
   cd infra
   pulumi stack init dev   # solo primera vez
   pulumi config set gcp:project <tu-proyecto>
   pulumi config set gcp:region us-central1
   pulumi config set --secret ingestApiKey <api-key-para-ingesta>
   pulumi config set ingestImage <region>-docker.pkg.dev/<proyecto>/cloud-run-repo/fog-ingestion:latest
   pulumi config set analystImage <region>-docker.pkg.dev/<proyecto>/cloud-run-repo/fog-analyst:latest
   pulumi up --yes
   ```

2. **Desplegar servicios de aplicacion**
   ```bash
   cd ..
   gcloud builds submit --config ci/cloudbuild.yaml \
     --substitutions _PROJECT=<tu-proyecto>,_REGION=us-central1,_TAG=latest,_INGEST_API_KEY=<api-key-para-ingesta>
   ```
   - Cloud Run `fog-ingestion` queda publico (solo endpoint HTTP).
   - Cloud Function `fog-processor` queda suscrita al topic `fog-events`.
   - Cloud Run `fog-analyst` queda privado (usa token simple).

3. **Ejecutar el simulador Fog**
   ```bash
   cd fog
   pip install -r requirements.txt
   export FOG_ENDPOINT="https://<cloud-run-url>/events"
   export FOG_API_KEY="<api-key-para-ingesta>"
   python edge_app.py
   ```

4. **Dashboard**
   - Servir `dashboard/index.html` (p.ej. con un `python -m http.server`).
   - Configurar variables JS en runtime: `window.DASHBOARD_API_BASE="<url-analyst>"` y `window.DASHBOARD_API_TOKEN="<token-analyst>"`.

## Seguridad (demo)
- API key en ingesta (simple). Para prod: Identity Platform/IAP y/o Cloud Armor.
- `ANALYST_API_TOKEN` protege `/metrics` y `/predict_next`.
- Secretos via variables de entorno o Secret Manager (recomendado). No se versionan API keys ni URL productivas.
- Solo la ingesta es publica; analyst/dash deben ir tras token/IAP.

## CI/CD (Cloud Build)
- **Incluye**: build/push imagen ingesta, deploy Cloud Run ingesta, deploy Cloud Function procesador.
- **No incluye**: ejecucion de Pulumi (se corre manualmente cuando hay cambios de infra).
- Pasos fallan en caso de error (sin `allowFailure`).

## Six Pillars (resumen)
- **Operational Excellence**: IaC con Pulumi, servicios desacoplados (ingesta/processor/analyst), logs estructurados.
- **Security**: secretos fuera del codigo, API key en ingesta, token en analyst, posibilidad de IAP/Identity Platform y Cloud Armor.
- **Reliability**: Pub/Sub desacopla, idempotencia en processor, buffer local en Fog, Firestore gestionado.
- **Performance Efficiency**: serverless auto-escalable, carga minima en fog (solo eventos).
- **Cost Optimization**: pago por uso (Cloud Run/Functions), topicos compartidos, sin VMs ni GPUs en la nube.
- **Sustainability**: evita envio de video, procesamiento ligero en el borde, recursos serverless que escalan a cero.
