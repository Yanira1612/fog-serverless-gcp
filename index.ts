import * as pulumi from "@pulumi/pulumi";
import * as gcp from "@pulumi/gcp";

// 1. Obtener configuración del proyecto actual
const config = new pulumi.Config("gcp");
const project = config.require("project");

// 2. Pub/Sub Topic (Ya lo tenías)
const fogEventsTopic = new gcp.pubsub.Topic("fog-events-topic", {
    name: "fog-events",
});

// 3. Crear cuenta de servicio para Cloud Run
// Es buena práctica que el servicio tenga su propia identidad
const cloudRunSa = new gcp.serviceaccount.Account("cloud-run-sa", {
    accountId: "fog-cloud-run-sa",
    displayName: "Service Account for Fog Cloud Run",
});

// 4. Cloud Run Service (Actualizado con la cuenta de servicio)
const fogIngestionService = new gcp.cloudrun.Service("fog-ingestion", {
    location: "us-central1",
    template: {
        spec: {
            serviceAccountName: cloudRunSa.email, // Asignamos la identidad
            containers: [{
                // ASEGÚRATE DE HABER CONSTRUIDO Y SUBIDO ESTA IMAGEN
                // gcloud builds submit --tag us-central1-docker.pkg.dev/...
                image: "us-central1-docker.pkg.dev/fog-serverless/cloud-run-repo/fog-ingestion:latest",
                ports: [{ containerPort: 8080 }],
                envs: [
                    { name: "PYTHONUNBUFFERED", value: "1" } // Para ver los logs print()
                ]
            }],
        },
    },
});

// 5. Permisos: Darle a Cloud Run permiso de escribir en Datastore/Firestore
const saFirestoreBinding = new gcp.projects.IAMMember("sa-firestore-binding", {
    project: project,
    role: "roles/datastore.user", // Permite leer/escribir en Firestore
    member: pulumi.interpolate`serviceAccount:${cloudRunSa.email}`,
});

// 6. Hacer Cloud Run invocable públicamente (necesario para Pub/Sub push si no se configura auth compleja)
// Nota: En producción idealmente se usa una cuenta de servicio dedicada para el trigger, pero esto funciona para demos.
const invoker = new gcp.cloudrun.IamMember("fog-ingestion-public", {
    service: fogIngestionService.name,
    location: fogIngestionService.location,
    role: "roles/run.invoker",
    member: "allUsers",
});

// 7. 🔥 LA CLAVE: Suscripción PUSH
// Esto conecta el Topic con Cloud Run. Cuando llega un mensaje, Pub/Sub llama a la URL.
const fogPushSubscription = new gcp.pubsub.Subscription("fog-push-sub", {
    topic: fogEventsTopic.name,
    pushConfig: {
        pushEndpoint: pulumi.interpolate`${fogIngestionService.statuses[0].url}/events`,
    },
    ackDeadlineSeconds: 60,
});

// 8. Base de Datos Firestore (Modo Nativo)
// Nota: Si ya la creaste manualmente en la consola, Pulumi la importará o dará error si conflicto.
// Si es proyecto nuevo, esto la activa.
const database = new gcp.firestore.Database("serverless-db", {
    locationId: "us-central1",
    type: "FIRESTORE_NATIVE",
});

// Exportaciones
export const cloudRunUrl = fogIngestionService.statuses.apply(s => s[0].url);
export const topicName = fogEventsTopic.name;
export const dbName = database.name;