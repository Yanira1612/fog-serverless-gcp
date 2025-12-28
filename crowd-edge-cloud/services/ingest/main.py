import logging
import os
import json
from flask import Flask, request, jsonify
from google.cloud import pubsub_v1

# 1. Configuración de Logs
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fog-ingest")

app = Flask(__name__)

# 2. Configuración de Pub/Sub y Proyecto
# Usamos las variables que definiste en Pulumi
PROJECT_ID = os.getenv("PROJECT_ID", "fog-serverless")
TOPIC_ID = os.getenv("TOPIC_ID", "fog-events")

# Inicializar cliente Pub/Sub
publisher = None
topic_path = None

try:
    publisher = pubsub_v1.PublisherClient()
    topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)
except Exception as e:
    logger.error(f"Error inicializando Pub/Sub: {e}")

def log_structured(message: str, payload: dict, severity: str = "INFO"):
    """Emite logs en formato JSON para Cloud Logging."""
    log_entry = {"severity": severity, "message": message, "payload": payload}
    print(json.dumps(log_entry))

@app.route("/events", methods=["POST"])
def receive_event():
    """Recibe eventos, valida campos básicos y publica en Pub/Sub."""
    if not publisher:
         return jsonify({"error": "Pub/Sub no inicializado"}), 500

    try:
        # Flask a veces necesita force=True si el header no es application/json exacto
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "Payload vacío"}), 400

        # Publicar a Pub/Sub
        data_str = json.dumps(data)
        future = publisher.publish(topic_path, data_str.encode("utf-8"))
        
        # Esperamos confirmación (timeout corto)
        message_id = future.result(timeout=5)

        log_structured(
            "Evento aceptado y publicado",
            {"event_id": data.get("event_id"), "message_id": message_id}
        )
        
        return jsonify({"status": "accepted", "message_id": message_id}), 200

    except Exception as e:
        log_structured("Error procesando evento", {"error": str(e)}, severity="ERROR")
        return jsonify({"detail": str(e)}), 500

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "fog-ingestion-flask"}), 200

if __name__ == "__main__":
    # Esto ayuda a probar localmente si es necesario
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)