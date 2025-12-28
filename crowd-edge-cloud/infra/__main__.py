import pulumi
import pulumi_gcp as gcp

# Configuración fija del proyecto y la región en GCP
project = "fog-serverless"
region = "us-central1"

# Imagen en Artifact Registry para el servicio de ingesta
container_image = (
    "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest"
)

# Tema de Pub/Sub para los eventos provenientes del fog
topic = gcp.pubsub.Topic(
    "fog-events",
    name="fog-events",
    project=project,
)

# Cuenta de servicio dedicada para Cloud Run (ingesta)
service_account = gcp.serviceaccount.Account(
    "fog-ingestion-sa",
    account_id="fog-ingestion-sa",
    display_name="Fog ingestion runner",
    project=project,
)

# Permisos mínimos para que la cuenta de servicio publique en Pub/Sub y use Firestore
pubsub_publisher = gcp.projects.IAMMember(
    "fog-ingestion-pubsub-publisher",
    project=project,
    role="roles/pubsub.publisher",
    member=service_account.email.apply(lambda email: f"serviceAccount:{email}"),
)

datastore_user = gcp.projects.IAMMember(
    "fog-ingestion-datastore-user",
    project=project,
    role="roles/datastore.user",
    member=service_account.email.apply(lambda email: f"serviceAccount:{email}"),
)

# Servicio Cloud Run (v1) que recibe eventos HTTP simulados y los publica en Pub/Sub
cloud_run_service = gcp.cloudrun.Service(
    "fog-ingestion",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            service_account_name=service_account.email,
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
)

# Permitir invocación pública del servicio Cloud Run
public_invoker = gcp.cloudrun.IamMember(
    "fog-ingestion-invoker",
    service=cloud_run_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
    project=project,
)

# Base de datos Firestore en modo nativo
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
)

# Exportes principales para uso en otros componentes o documentación
pulumi.export("cloudRunUrl", cloud_run_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("topicName", topic.name)
