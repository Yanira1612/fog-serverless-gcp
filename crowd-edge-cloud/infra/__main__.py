import pulumi
import pulumi_gcp as gcp

# Configuración fija del proyecto y la región en GCP
project = "fog-serverless"
region = "us-central1"

# Imágenes en Artifact Registry
container_image_ingest = (
    "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest"
)
container_image_dashboard = (
    "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-dashboard:latest"
)

# API keys para ingesta y dashboard (definir via pulumi config)
config = pulumi.Config()
ingest_api_key = config.get("ingestApiKey") or "DEFINIR-API-KEY"
dashboard_api_token = config.get("dashboardApiToken") or "DEFINIR-DASHBOARD-TOKEN"

# Tópicos de Pub/Sub para enrutar eventos
topic_raw = gcp.pubsub.Topic("fog-events-raw", name="fog-events.raw", project=project)
topic_alerts = gcp.pubsub.Topic("fog-events-alerts", name="fog-events.alerts", project=project)
topic_ops = gcp.pubsub.Topic("fog-events-ops", name="fog-events.ops", project=project)
topic_tickets = gcp.pubsub.Topic("fog-events-tickets", name="fog-events.tickets", project=project)
topic_dlq = gcp.pubsub.Topic("fog-events-dlq", name="fog-events.dlq", project=project)

# Cuenta de servicio dedicada para Cloud Run (principio de mínimo privilegio)
ingest_sa = gcp.serviceaccount.Account(
    "fog-ingestion-sa",
    account_id="fog-ingestion-sa",
    display_name="Fog ingestion service account",
    project=project,
)

# Permisos mínimos para publicar en los tópicos definidos
topic_publishers = []
for t in [topic_raw, topic_alerts, topic_ops, topic_tickets, topic_dlq]:
    topic_publishers.append(
        gcp.pubsub.TopicIAMMember(
            f"fog-ingestion-topic-publisher-{t._name}",
            topic=t.name,
            role="roles/pubsub.publisher",
            member=ingest_sa.email.apply(lambda email: f"serviceAccount:{email}"),
        )
    )

# Servicio Cloud Run (v1) que recibe eventos HTTP y los publica en Pub/Sub (raw)
cloud_run_service = gcp.cloudrun.Service(
    "fog-ingestion",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            service_account_name=ingest_sa.email,
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image=container_image_ingest,
                    envs=[
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PROJECT_ID", value=project
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="TOPIC_NAME", value=topic_raw.name
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="TOPIC_ALERTS", value=topic_alerts.name
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="TOPIC_OPS", value=topic_ops.name
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="TOPIC_TICKETS", value=topic_tickets.name
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="TOPIC_DLQ", value=topic_dlq.name
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PYTHONUNBUFFERED", value="1"
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="INGEST_API_KEY", value=ingest_api_key
                        ),
                    ],
                    ports=[
                        gcp.cloudrun.ServiceTemplateSpecContainerPortArgs(
                            container_port=8080
                        )
                    ],
                )
            ],
        )
    ),
    opts=pulumi.ResourceOptions(depends_on=topic_publishers),
)

# Permitir invocación pública del servicio Cloud Run (recibe eventos desde el fog)
public_invoker = gcp.cloudrun.IamMember(
    "fog-ingestion-invoker",
    service=cloud_run_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
    project=project,
)

# Base de datos Firestore en modo nativo (BaaS)
firestore_db = gcp.firestore.Database(
    "default-firestore",
    project=project,
    location_id=region,
    type="FIRESTORE_NATIVE",
    concurrency_mode="OPTIMISTIC",
)

# Suscripciones pull para consumidores futuros (dashboard/notificaciones)
sub_alerts = gcp.pubsub.Subscription(
    "fog-alerts-sub",
    project=project,
    topic=topic_alerts.name,
)
sub_ops = gcp.pubsub.Subscription(
    "fog-ops-sub",
    project=project,
    topic=topic_ops.name,
)
sub_tickets = gcp.pubsub.Subscription(
    "fog-tickets-sub",
    project=project,
    topic=topic_tickets.name,
)
sub_dlq = gcp.pubsub.Subscription(
    "fog-dlq-sub",
    project=project,
    topic=topic_dlq.name,
)

# Servicio Cloud Run para dashboard protegido por token simple (placeholder de Identity Platform)
dashboard_sa = gcp.serviceaccount.Account(
    "fog-dashboard-sa",
    account_id="fog-dashboard-sa",
    display_name="Fog dashboard service account",
    project=project,
)

dashboard_service = gcp.cloudrun.Service(
    "fog-dashboard",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            service_account_name=dashboard_sa.email,
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image=container_image_dashboard,
                    envs=[
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PROJECT_ID", value=project
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="DASHBOARD_API_TOKEN", value=dashboard_api_token
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PYTHONUNBUFFERED", value="1"
                        ),
                    ],
                )
            ],
        )
    ),
)

dashboard_invoker = gcp.cloudrun.IamMember(
    "fog-dashboard-invoker",
    service=dashboard_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
    project=project,
)

# Exportes principales para uso en otros componentes o documentación
pulumi.export("cloudRunUrl", cloud_run_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("topicRaw", topic_raw.name)
pulumi.export("topicAlerts", topic_alerts.name)
pulumi.export("topicOps", topic_ops.name)
pulumi.export("topicTickets", topic_tickets.name)
pulumi.export("topicDlq", topic_dlq.name)
pulumi.export("dashboardUrl", dashboard_service.statuses.apply(lambda s: s[0]["url"]))
