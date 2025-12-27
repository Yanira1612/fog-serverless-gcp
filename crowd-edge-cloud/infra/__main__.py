import pulumi
import pulumi_gcp as gcp

# Configuracion fija del proyecto y la region en GCP
project = "fog-serverless"
region = "us-central1"

# Imagen en Artifact Registry (etiqueta fija latest)
container_image = (
    "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest"
)

# Tema de Pub/Sub para los eventos provenientes del fog
topic = gcp.pubsub.Topic(
    "fog-events",
    name="fog-events",
    project=project,
)

# Cuenta de servicio dedicada para el servicio de ingesta en Cloud Run
service_account = gcp.serviceaccount.Account(
    "fog-ingestion-sa",
    account_id="fog-ingestion-sa",
    display_name="Fog ingestion runner",
    project=project,
)

# Servicio Cloud Run (v1) que recibe eventos HTTP del fog
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

# Permiso para invocacion publica del servicio Cloud Run
public_invoker = gcp.cloudrun.IamMember(
    "fog-ingestion-invoker",
    service=cloud_run_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
    project=project,
)

# Rol para que la cuenta de servicio pueda usar Firestore
datastore_binding = gcp.projects.IAMMember(
    "fog-ingestion-firestore-access",
    project=project,
    role="roles/datastore.user",
    member=service_account.email.apply(lambda email: f"serviceAccount:{email}"),
)

# Base de datos Firestore en modo nativo
firestore_db = gcp.firestore.Database(
    "default-firestore",
    project=project,
    location_id=region,
    type="FIRESTORE_NATIVE",
    concurrency_mode="OPTIMISTIC",
)

# Suscripcion push que reenvia mensajes de Pub/Sub al endpoint del servicio Cloud Run
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

# Exportes principales para referencia rapida
pulumi.export("cloudRunUrl", cloud_run_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("topicName", topic.name)