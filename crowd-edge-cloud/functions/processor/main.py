import os
import base64
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict
from flask import Flask, request
from google.cloud import firestore

# Configuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-processor")

app = Flask(__name__)

# --- CORRECCIÓN CRÍTICA AQUÍ ---
# Leemos el nombre de la base de datos que Pulumi inyectó en la variable de entorno DB_NAME.
# Si no la encuentra, intenta usar "(default)", pero ahora usará la correcta (ej: default-firestore-69...)
db_name = os.environ.get("DB_NAME", "(default)")
logger.info(f"🔌 Conectando a Firestore DB: {db_name}")
db = firestore.Client(database=db_name)
# -------------------------------

# 1. DECORADOR TRANSACCIONAL
@firestore.transactional
def run_transactional_store(transaction, payload: Dict[str, Any]) -> bool:
    """Lógica de guardado atómico."""
    event_id = payload["event_id"]
    camera_id = payload.get("camera_id", "unknown")

    events_ref = db.collection("events").document(event_id)
    camera_state_ref = db.collection("camera_state").document(camera_id)

    # Lectura (Debe ser lo primero)
    event_snapshot = events_ref.get(transaction=transaction)
    
    if event_snapshot.exists:
        return False

    now_iso = datetime.now(timezone.utc).isoformat()

    # Escritura
    transaction.set(events_ref, {**payload, "received_at": now_iso})
    transaction.set(camera_state_ref, {
        "last_event_id": event_id,
        "last_event_type": payload.get("event_type"),
        "people_count": payload.get("people_count"),
        "updated_at": now_iso,
    }, merge=True)
    
    return True

@app.route("/", methods=["POST"])
def receive_pubsub_push():
    """Endpoint que recibe el POST de Pub/Sub."""
    envelope = request.get_json(silent=True)
    if not envelope:
        return "No JSON received", 400

    if "message" not in envelope:
        return "Invalid Pub/Sub message format", 400

    pubsub_message = envelope["message"]

    try:
        # Decodificar
        if isinstance(pubsub_message, dict) and "data" in pubsub_message:
            data_str = base64.b64decode(pubsub_message["data"]).decode("utf-8")
            payload = json.loads(data_str)
        else:
            return "Invalid message payload", 400
    except Exception as e:
        logger.error(f"Error decoding: {e}")
        return "Decoding error", 400

    # 2. EJECUCIÓN DE LA TRANSACCIÓN
    transaction = db.transaction()
    try:
        inserted = run_transactional_store(transaction, payload)
        
        if inserted:
            logger.info(f"✅ Evento guardado en Firestore: {payload.get('event_id')}")
        else:
            logger.info(f"⏭️ Evento duplicado ignorado: {payload.get('event_id')}")
            
    except Exception as e:
        # Si la DB no es correcta, aquí salta el error "Transaction has no ID"
        logger.error(f"Error saving to Firestore: {e}")
        return "Database error", 500

    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)