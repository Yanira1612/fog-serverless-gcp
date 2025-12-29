import base64
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

from google.cloud import firestore
from google.cloud import pubsub_v1

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-processor")

# Cliente global de Firestore
db = firestore.Client()

# Pub/Sub publisher para enrutar a otros tópicos
publisher = pubsub_v1.PublisherClient()

# Variables de entorno para tópicos de salida
TOPIC_ALERTS = os.getenv("TOPIC_ALERTS", "fog-events.alerts")
TOPIC_OPS = os.getenv("TOPIC_OPS", "fog-events.ops")
TOPIC_TICKETS = os.getenv("TOPIC_TICKETS", "fog-events.tickets")
TOPIC_DLQ = os.getenv("TOPIC_DLQ", "fog-events.dlq")
PROJECT_ID = os.getenv("PROJECT_ID", "fog-serverless")


def _decode_event(event: Dict[str, Any]) -> Dict[str, Any]:
    """Deserializa el mensaje Pub/Sub codificado en base64."""
    if "data" not in event:
        raise ValueError("Mensaje sin atributo data")
    decoded_bytes = base64.b64decode(event["data"])
    return json.loads(decoded_bytes.decode("utf-8"))


def _publish(topic_name: str, payload: Dict[str, Any]) -> None:
    """Publica un payload en el tópico indicado."""
    topic_path = publisher.topic_path(PROJECT_ID, topic_name)
    publisher.publish(topic_path, json.dumps(payload).encode("utf-8"))


def _store_event(transaction: firestore.Transaction, payload: Dict[str, Any]) -> bool:
    """Guarda evento e idempotencia; True si se insertó, False si ya existía."""
    event_id = payload["event_id"]
    camera_id = payload.get("camera_id", "unknown")

    events_ref = db.collection("events").document(event_id)
    camera_state_ref = db.collection("camera_state").document(camera_id)

    event_snapshot = events_ref.get(transaction=transaction)
    if event_snapshot.exists:
        return False

    now_iso = datetime.now(timezone.utc).isoformat()

    transaction.set(events_ref, {**payload, "received_at": now_iso})
    transaction.set(
        camera_state_ref,
        {
            "last_event_id": event_id,
            "last_event_type": payload.get("event_type"),
            "people_count": payload.get("people_count"),
            "updated_at": now_iso,
        },
        merge=True,
    )
    return True


def _route_event(payload: Dict[str, Any]) -> str:
    """Determina el tópico destino según el tipo de evento."""
    event_type = payload.get("event_type", "")
    if event_type in {"CROWD_GATHERING", "PROLONGED_CROWD"}:
        return TOPIC_ALERTS
    if event_type == "SUDDEN_SPIKE":
        return TOPIC_OPS
    if event_type == "CAMERA_OFFLINE":
        return TOPIC_TICKETS
    return TOPIC_DLQ


def process_event(event: Dict[str, Any], context: Any) -> None:
    """Función Cloud Function (gen2) activada por Pub/Sub raw."""
    try:
        payload = _decode_event(event)
    except Exception as err:  # noqa: BLE001
        logger.error("No se pudo decodificar el mensaje: %s", err)
        return

    required = ("event_id", "camera_id", "event_type", "timestamp")
    missing = [f for f in required if f not in payload]
    if missing:
        logger.error("Evento inválido, faltan campos: %s", ", ".join(missing))
        return

    transaction = db.transaction()
    try:
        inserted = transaction.call(_store_event, payload)
    except Exception as err:  # noqa: BLE001
        logger.error("Error al persistir evento %s: %s", payload.get("event_id"), err)
        _publish(TOPIC_DLQ, {"error": str(err), "payload": payload})
        return

    if not inserted:
        logger.info("Evento duplicado ignorado: %s", payload.get("event_id"))
    else:
        logger.info(
            "Evento procesado y guardado en Firestore",
            extra={
                "event_id": payload.get("event_id"),
                "event_type": payload.get("event_type"),
                "camera_id": payload.get("camera_id"),
            },
        )

    # Enrutamiento a tópico correspondiente
    try:
        target_topic = _route_event(payload)
        _publish(target_topic, payload)
        logger.info("Evento reenrutado a tópico %s", target_topic)
    except Exception as err:  # noqa: BLE001
        logger.error("Error al reenrutar evento %s: %s", payload.get("event_id"), err)
        _publish(TOPIC_DLQ, {"error": str(err), "payload": payload})

    # Alertar en logs si hay aglomeración
    if payload.get("event_type") in {"CROWD_GATHERING", "PROLONGED_CROWD"}:
        logger.warning(
            "ALERTA de aglomeración detectada en cámara %s (evento %s)",
            payload.get("camera_id"),
            payload.get("event_id"),
        )
