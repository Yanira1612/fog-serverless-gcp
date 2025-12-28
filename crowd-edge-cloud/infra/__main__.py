import pulumi
import pulumi_gcp as gcp

# Configuración fija del proyecto y la región en GCP
project = "fog-serverless"
region = "us-central1"

# Imagen en Artifact Registry para el servicio de ingesta
container_image = (
    "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest"
)

# API key para la ingesta segura (defínela vía `pulumi config set ingestApiKey <valor>`)
config = pulumi.Config()
ingest_api_key = config.get("ingestApiKey") or "DEFINIR-API-KEY"

# Tema de Pub/Sub para los eventos provenientes del fog
topic = gcp.pubsub.Topic(
    "fog-events",
    name="fog-events",
    project=project,
)

# Cuenta de servicio dedicada para Cloud Run (principio de mínimo privilegio)
ingest_sa = gcp.serviceaccount.Account(
    "fog-ingestion-sa",
    account_id="fog-ingestion-sa",
    display_name="Fog ingestion service account",
    project=project,
)

# Permiso para publicar en el tópico, sin tocar IAM de todo el proyecto
topic_publisher = gcp.pubsub.TopicIAMMember(
    "fog-ingestion-topic-publisher",
    topic=topic.name,
    role="roles/pubsub.publisher",
    member=ingest_sa.email.apply(lambda email: f"serviceAccount:{email}"),
)

# Servicio Cloud Run (v1) que recibe eventos HTTP simulados y los publica en Pub/Sub.
cloud_run_service = gcp.cloudrun.Service(
    "fog-ingestion",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            service_account_name=ingest_sa.email,
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image=container_image,
                    envs=[
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PROJECT_ID", value=project
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="TOPIC_NAME", value=topic.name
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
    opts=pulumi.ResourceOptions(depends_on=[topic_publisher]),
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

# Suscripción push que reenvía mensajes de Pub/Sub al endpoint /events de Cloud Run
subscription = gcp.pubsub.Subscription(
    "fog-events-subscription",
    name="fog-events-subscription",
    project=project,
    topic=topic.name,
    push_config=gcp.pubsub.SubscriptionPushConfigArgs(
        push_endpoint=cloud_run_service.statuses.apply(
            lambda statuses: f"{statuses[0]['url']}/events" if statuses else None
        ),
    ),
    opts=pulumi.ResourceOptions(depends_on=[cloud_run_service]),
)

# Exportes principales para uso en otros componentes o documentación
pulumi.export("cloudRunUrl", cloud_run_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("topicName", topic.name)
