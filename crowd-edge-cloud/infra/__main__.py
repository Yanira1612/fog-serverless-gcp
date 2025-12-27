import pulumi
import pulumi_gcp as gcp

# Configuración fija del proyecto y región en GCP
project = "fog-serverless"
region = "us-central1"

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

# Servicio Cloud Run que recibirá eventos HTTP del fog y los publicará en Pub/Sub
cloud_run_service = gcp.cloudrunv2.Service(
    "fog-ingestion",
    name="fog-ingestion",
    location=region,
    project=project,
    template=gcp.cloudrunv2.ServiceTemplateArgs(
        service_account=service_account.email,
        containers=[
            gcp.cloudrunv2.ServiceTemplateContainerArgs(
                image="gcr.io/fog-serverless/fog-ingestion:latest",
                ports=[
                    gcp.cloudrunv2.ServiceTemplateContainerPortArgs(
                        container_port=8080,
                    )
                ],
            )
        ],
    ),
)

# Permiso para invocación pública del servicio Cloud Run
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

# Suscripción push que reenvía mensajes de Pub/Sub al endpoint del servicio Cloud Run
subscription = gcp.pubsub.Subscription(
    "fog-events-subscription",
    name="fog-events-subscription",
    project=project,
    topic=topic.name,
    push_config=gcp.pubsub.SubscriptionPushConfigArgs(
        push_endpoint=cloud_run_service.uri.apply(lambda uri: f"{uri}/events"),
    ),
)

# Exportes principales para referencia rápida
pulumi.export("cloud_run_url", cloud_run_service.uri)
pulumi.export("topic_name", topic.name)
pulumi.export("firestore_db", firestore_db.name)
