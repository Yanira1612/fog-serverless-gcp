import pulumi
import pulumi_gcp as gcp

# --- 1. Configuración General ---
project = "fog-serverless"
region = "us-central1"

# Definir las imágenes (Asegúrate de que el tag coincida con lo que subiste)
ingest_image = "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest"
processor_image = "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-processor:latest"

# Base de datos Firestore (Si ya existe, Pulumi la adoptará o la dejará tal cual)
firestore_db = gcp.firestore.Database(
    "default-firestore",
    project=project,
    location_id=region,
    type="FIRESTORE_NATIVE",
    concurrency_mode="OPTIMISTIC",
)

# Tema de Pub/Sub
topic = gcp.pubsub.Topic(
    "fog-events",
    name="fog-events",
    project=project,
)

# --- 2. Servicio de INGESTA (Edge -> Cloud) ---

# Crear cuenta de servicio para que el Ingestor tenga identidad propia
ingest_sa = gcp.serviceaccount.Account("ingest-sa",
    account_id="fog-ingest-sa",
    display_name="Service Account for Fog Ingestion",
)

# Dar permiso explícito para publicar en el tema (Soluciona tu error 500)
ingest_publisher_permission = gcp.pubsub.TopicIAMMember("ingest-publisher-perm",
    topic=topic.name,
    role="roles/pubsub.publisher",
    member=pulumi.Output.concat("serviceAccount:", ingest_sa.email),
)

# Servicio Cloud Run de Ingesta
ingest_service = gcp.cloudrun.Service(
    "fog-ingestion",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            service_account_name=ingest_sa.email, # Usamos la cuenta con permisos
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image=ingest_image,
                    envs=[
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PROJECT_ID", value=project
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="TOPIC_ID", value=topic.name
                        ),
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PYTHONUNBUFFERED", value="1"
                        ),
                    ],
                    ports=[gcp.cloudrun.ServiceTemplateSpecContainerPortArgs(container_port=8080)],
                )
            ],
        )
    ),
    opts=pulumi.ResourceOptions(depends_on=[ingest_publisher_permission])
)

# Permitir que el mundo (tu laptop) envíe datos al Ingestor
ingest_invoker = gcp.cloudrun.IamMember(
    "ingest-public-invoker",
    service=ingest_service.name,
    location=region,
    role="roles/run.invoker",
    member="allUsers",
    project=project,
)

# --- 3. Servicio PROCESADOR (Pub/Sub -> Firestore) ---

# Servicio Cloud Run del Procesador
# Nota: Usamos la cuenta por defecto de Compute Engine que ya tiene acceso a Firestore
processor_service = gcp.cloudrun.Service("fog-processor",
    location=region,
    project=project,
    template=gcp.cloudrun.ServiceTemplateArgs(
        spec=gcp.cloudrun.ServiceTemplateSpecArgs(
            containers=[
                gcp.cloudrun.ServiceTemplateSpecContainerArgs(
                    image=processor_image,
                    envs=[
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="PYTHONUNBUFFERED", value="1"
                        ),
                        # --- AGREGAR ESTO ---
                        gcp.cloudrun.ServiceTemplateSpecContainerEnvArgs(
                            name="DB_NAME", value=firestore_db.name 
                        ),
                        # --------------------
                    ],
                    ports=[gcp.cloudrun.ServiceTemplateSpecContainerPortArgs(container_port=8080)],
                )
            ]
        )
    )
)

# --- 4. Conexión Pub/Sub -> Procesador (Subscription) ---

# Creamos una identidad segura para que Pub/Sub invoque al Procesador
pubsub_invoker_sa = gcp.serviceaccount.Account("pubsub-invoker-sa",
    account_id="processor-invoker",
    display_name="Pub/Sub Invoker Identity"
)

# Le damos permiso a esa identidad para invocar SOLO el servicio Processor
processor_invoker_iam = gcp.cloudrun.IamMember("processor-invoker-perm",
    service=processor_service.name,
    location=region,
    role="roles/run.invoker",
    member=pulumi.Output.concat("serviceAccount:", pubsub_invoker_sa.email),
    project=project
)

# La Suscripción Push
subscription = gcp.pubsub.Subscription(
    "fog-events-sub",
    name="fog-events-sub",
    topic=topic.name,
    project=project,
    push_config=gcp.pubsub.SubscriptionPushConfigArgs(
        # ¡AQUI ESTA LA CLAVE! Apuntamos al Processor, no al Ingest
        push_endpoint=processor_service.statuses.apply(lambda s: s[0]["url"]),
        
        # Autenticación segura (OIDC)
        oidc_token=gcp.pubsub.SubscriptionPushConfigOidcTokenArgs(
            service_account_email=pubsub_invoker_sa.email
        )
    ),
    opts=pulumi.ResourceOptions(depends_on=[processor_invoker_iam, processor_service])
)

# --- 5. Exports ---
pulumi.export("ingest_url", ingest_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("processor_url", processor_service.statuses.apply(lambda s: s[0]["url"]))
pulumi.export("topic_name", topic.name)
pulumi.export("database_name", firestore_db.name)
# Exportes principales para uso en otros componentes o documentación
#pulumi.export("cloudRunUrl", cloud_run_service.statuses.apply(lambda s: s[0]["url"]))
#pulumi.export("topicName", topic.name)