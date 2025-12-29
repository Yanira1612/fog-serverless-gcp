import pulumi
import pulumi_gcp as gcp

# Configuración parametrizada (evita valores fijos en código)
gcp_project = gcp.config.project or pulumi.Config("gcp").require("project")
gcp_region = gcp.config.region or pulumi.Config("gcp").require("region")

config = pulumi.Config()
ingest_image = config.get("ingestImage") or f"{gcp_region}-docker.pkg.dev/{gcp_project}/cloud-run-repo/fog-ingestion:latest"
analyst_image = config.get("analystImage") or f"{gcp_region}-docker.pkg.dev/{gcp_project}/cloud-run-repo/fog-analyst:latest"
ingest_api_key = config.require_secret("ingestApiKey")

# --- 1. BASE DE DATOS FIRESTORE ---
firestore_db = gcp.firestore.Database(
    "default-firestore",
    project=gcp_project,
    location_id=gcp_region,
    type="FIRESTORE_NATIVE",
    concurrency_mode="OPTIMISTIC",
)

# --- 2. PUB/SUB ---
topic = gcp.pubsub.Topic("fog-events", name="fog-events", project=gcp_project)

# --- 3. SERVICIO INGESTA (Cloud Run HTTP) ---
ingest_sa = gcp.serviceaccount.Account(
    "fog-ingestion-sa",
    account_id="fog-ingestion-sa",
    project=gcp_project,
)

gcp.pubsub.TopicIAMMember(
    "fog-ingestion-topic-publisher",
    topic=topic.name,
    role="roles/pubsub.publisher",
    member=ingest_sa.email.apply(lambda email: f"serviceAccount:{email}"),
)

cloud_run_service = gcp.cloudrun.Service(
    "fog-ingestion",
    location=gcp_region,
    project=gcp_project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            service_account_name=ingest_sa.email,
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image=ingest_image,
                    envs=[
                        {"name": "PROJECT_ID", "value": gcp_project},
                        {"name": "TOPIC_NAME", "value": topic.name},
                        {"name": "INGEST_API_KEY", "value": ingest_api_key},
                    ],
                    ports=[{"containerPort": 8080}],
                )
            ],
        )
    ),
)

# Ingesta pública (demo). Analyst no se expone públicamente.
gcp.cloudrun.IamMember(
    "fog-ingestion-invoker",
    service=cloud_run_service.name,
    location=gcp_region,
    role="roles/run.invoker",
    member="allUsers",
)

# --- 4. SERVICIO ANALYST (Cloud Run protegido con token/IAP) ---
analyst_service = gcp.cloudrun.Service(
    "fog-analyst",
    location=gcp_region,
    project=gcp_project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image=analyst_image,
                    envs=[
                        {"name": "DB_NAME", "value": firestore_db.name},
                        {"name": "PYTHONUNBUFFERED", "value": "1"},
                    ],
                    ports=[{"containerPort": 8080}],
                )
            ],
        )
    ),
)

# --- EXPORTES ---
pulumi.export("ingest_url", cloud_run_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("analyst_url", analyst_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("database_name", firestore_db.name)
