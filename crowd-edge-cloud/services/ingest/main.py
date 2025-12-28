import json
import logging
import os

from flask import Flask, jsonify, request
from google.cloud import pubsub_v1

# Configuración de logging en texto plano (Cloud Logging lo estructurará)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fog-ingest")

# Configuración de entorno (inyectadas por Pulumi en Cloud Run)
PROJECT_ID = os.getenv("PROJECT_ID", "fog-serverless")
TOPIC_NAME = os.getenv("TOPIC_NAME", "fog-events")
INGEST_API_KEY = os.getenv("INGEST_API_KEY", "")

app = Flask(__name__)

# Inicialización del cliente Pub/Sub
try:
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)
except Exception as err:  # noqa: BLE001
    logger.error("Error inicializando Pub/Sub: %s", err)
    publisher = None
    topic_path = None


def log_structured(message: str, payload: dict, severity: str = "INFO") -> None:
    """Emite logs en formato JSON simple para Cloud Logging."""
    log_entry = {"severity": severity, "message": message, "payload": payload}
    print(json.dumps(log_entry))


@app.route("/events", methods=["POST"])
def receive_event():
    """Recibe eventos, valida API Key y publica en Pub/Sub."""
    if not publisher or not topic_path:
        return jsonify({"error": "Pub/Sub no inicializado"}), 500

    # Validación de API Key simple para simular seguridad en el borde
    api_key = request.headers.get("X-API-KEY", "")
    if not INGEST_API_KEY or api_key != INGEST_API_KEY:
        log_structured(
            "API Key inválida en ingesta",
            {"client_ip": request.remote_addr},
            severity="WARNING",
        )
        return jsonify({"error": "No autorizado"}), 401

    try:
        payload = request.get_json(force=True, silent=False)
    except Exception:  # noqa: BLE001
        return jsonify({"error": "JSON inválido"}), 400

    if not payload:
        return jsonify({"error": "Payload vacío"}), 400

    # Validación básica de campos mínimos
    required = ("event_id", "event_type", "camera_id", "timestamp")
    missing = [f for f in required if f not in payload]
    if missing:
        return jsonify({"error": f"Faltan campos: {', '.join(missing)}"}), 400

    try:
        data_str = json.dumps(payload)
        future = publisher.publish(topic_path, data_str.encode("utf-8"))
        message_id = future.result(timeout=5)

        log_structured(
            "Evento aceptado y publicado",
            {
                "event_id": payload.get("event_id"),
                "event_type": payload.get("event_type"),
                "camera_id": payload.get("camera_id"),
                "message_id": message_id,
                "topic": TOPIC_NAME,
            },
        )
        return jsonify({"status": "accepted", "message_id": message_id, "topic": TOPIC_NAME}), 200
    except Exception as err:  # noqa: BLE001
        log_structured(
            "Error procesando evento",
            {"error": str(err)},
            severity="ERROR",
        )
        return jsonify({"detail": "Error interno"}), 500


@app.route("/health", methods=["GET"])
def health():
    """Endpoint simple de salud."""
    return jsonify({"status": "ok", "service": "fog-ingestion"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
