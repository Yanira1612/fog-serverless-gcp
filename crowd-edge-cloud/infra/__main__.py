import pulumi
import pulumi_gcp as gcp

# Configuración fija del proyecto y la región en GCP
project = "fog-serverless"
region = "us-central1"

# Imágenes en Artifact Registry
ingest_image = "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest"
processor_image = "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-processor:latest"
analyst_image = "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-analyst:latest"

# API key para la ingesta segura
config = pulumi.Config()
ingest_api_key = config.get("ingestApiKey") or "fog-secret-123"

# --- 1. BASE DE DATOS FIRESTORE ---
firestore_db = gcp.firestore.Database(
    "default-firestore",
    project=project,
    location_id=region,
    type="FIRESTORE_NATIVE",
    concurrency_mode="OPTIMISTIC",
)

# --- 2. PUB/SUB ---
topic = gcp.pubsub.Topic("fog-events", name="fog-events", project=project)

# --- 3. SERVICIO INGESTA (ENTRADA) ---
ingest_sa = gcp.serviceaccount.Account("fog-ingestion-sa", account_id="fog-ingestion-sa", project=project)

gcp.pubsub.TopicIAMMember("fog-ingestion-topic-publisher",
    topic=topic.name,
    role="roles/pubsub.publisher",
    member=ingest_sa.email.apply(lambda email: f"serviceAccount:{email}"),
)

cloud_run_service = gcp.cloudrun.Service("fog-ingestion",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            service_account_name=ingest_sa.email,
            containers=[gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                image=ingest_image,
                envs=[
                    {"name": "PROJECT_ID", "value": project},
                    {"name": "TOPIC_NAME", "value": topic.name},
                    {"name": "INGEST_API_KEY", "value": ingest_api_key},
                ],
                ports=[{"containerPort": 8080}],
            )],
        )
    ),
)

gcp.cloudrun.IamMember("fog-ingestion-invoker",
    service=cloud_run_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
)

# --- 4. SERVICIO PROCESSOR (EL QUE GUARDA EN DB) ---
# Aquí es donde corregimos el error que tenías
processor_service = gcp.cloudrun.Service("fog-processor",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            containers=[gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                image=processor_image,
                envs=[
                    {"name": "DB_NAME", "value": firestore_db.name}, # <-- VITAL
                    {"name": "PYTHONUNBUFFERED", "value": "1"},
                ],
                ports=[{"containerPort": 8080}],
            )],
        )
    ),
)

gcp.cloudrun.IamMember("processor-invoker",
    service=processor_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
)

# --- 5. SERVICIO ANALYST (PREDICCIÓN MARKOV) ---
analyst_service = gcp.cloudrun.Service("fog-analyst",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            containers=[gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                image=analyst_image,
                envs=[
                    {"name": "DB_NAME", "value": firestore_db.name}, # <-- VITAL
                    {"name": "PYTHONUNBUFFERED", "value": "1"},
                ],
                ports=[{"containerPort": 8080}],
            )],
        )
    ),
)

gcp.cloudrun.IamMember("analyst-invoker",
    service=analyst_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
)

# --- 6. SUSCRIPCIÓN PUB/SUB (CONEXIÓN INGESTA -> PROCESSOR) ---
# Esto hace que cuando llegue algo a la ingesta, se mande al procesador
subscription = gcp.pubsub.Subscription("fog-events-subscription",
    project=project,
    topic=topic.name,
    push_config=gcp.pubsub.SubscriptionPushConfigArgs(
        push_endpoint=processor_service.statuses.apply(lambda s: s[0]["url"])
    ),
)

# --- EXPORTES ---
pulumi.export("ingest_url", cloud_run_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("analyst_url", analyst_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("database_name", firestore_db.name)