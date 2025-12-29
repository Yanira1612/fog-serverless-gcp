import base64
import json
import logging
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-alerts")


def process_alert(event: Dict[str, Any], context: Any) -> None:
    """Procesa eventos de alertas (CROWD_GATHERING / PROLONGED_CROWD)."""
    try:
        data = base64.b64decode(event["data"]).decode("utf-8")
        payload = json.loads(data)
    except Exception as err:  # noqa: BLE001
        logger.error("Error decodificando alerta: %s", err)
        return

    logger.warning(
        "ALERTA recibida: %s en cámara %s",
        payload.get("event_type"),
        payload.get("camera_id"),
    )
    # Aquí se integraría con un servicio de notificaciones (email/SMS/webhook)
