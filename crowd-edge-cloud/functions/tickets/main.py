import base64
import json
import logging
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-tickets")


def process_ticket(event: Dict[str, Any], context: Any) -> None:
    """Procesa eventos de ticket (ej. CAMERA_OFFLINE)."""
    try:
        data = base64.b64decode(event["data"]).decode("utf-8")
        payload = json.loads(data)
    except Exception as err:  # noqa: BLE001
        logger.error("Error decodificando ticket: %s", err)
        return

    logger.info(
        "Ticket generado para evento %s en cámara %s",
        payload.get("event_type"),
        payload.get("camera_id"),
    )
    # Aquí se integraría con un sistema de incidentes (Jira, ServiceNow, etc.)
