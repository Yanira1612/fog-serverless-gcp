import base64
import json
import logging
from typing import Any, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-ops")


def process_ops(event: Dict[str, Any], context: Any) -> None:
    """Procesa eventos operativos (SUDDEN_SPIKE u otros de soporte)."""
    try:
        data = base64.b64decode(event["data"]).decode("utf-8")
        payload = json.loads(data)
    except Exception as err:  # noqa: BLE001
        logger.error("Error decodificando mensaje ops: %s", err)
        return

    logger.info(
        "Evento OPS recibido: %s en cámara %s",
        payload.get("event_type"),
        payload.get("camera_id"),
    )
    # Aquí se integraría con un sistema de monitoreo/observabilidad
