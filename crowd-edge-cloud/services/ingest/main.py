import json
import logging
import os
from collections import deque
from typing import Dict, Set

from fastapi import FastAPI, HTTPException, Request
from google.api_core import exceptions as gcp_exceptions
from google.cloud import pubsub_v1
from pydantic import BaseModel, Field

# Configuración de logging en texto plano (Cloud Logging lo estructurará)
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fog-ingest")

# Configuración de entorno (inyectadas por Pulumi en Cloud Run)
PROJECT_ID = os.getenv("PROJECT_ID", "fog-serverless")
TOPIC_NAME = os.getenv("TOPIC_NAME", "fog-events.raw")
INGEST_API_KEY = os.getenv("INGEST_API_KEY", "")

# Idempotencia simple en memoria (cola acotada)
_seen_ids: Set[str] = set()
_recent_ids = deque(maxlen=1024)

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)


class EventPayload(BaseModel):
    """Estructura esperada para eventos simulados desde el fog."""

    event_id: str = Field(..., description="Identificador único del evento")
    event_type: str = Field(..., description="Tipo de evento")
    camera_id: str = Field(..., description="Identificador de la cámara de borde")
    timestamp: str = Field(..., description="Marca de tiempo ISO8601 del evento")
    people_count: int | None = Field(
        None, description="Cantidad de personas cuando aplique"
    )
    extra: Dict | None = Field(None, description="Datos adicionales opcionales")


app = FastAPI(title="Fog Ingestion Service", version="1.1.0")


def log_structured(message: str, payload: Dict, severity: str = "INFO") -> None:
    """Emite logs en formato JSON para Cloud Logging."""
    log_entry = {"severity": severity, "message": message, "payload": payload}
    print(json.dumps(log_entry))


def _check_idempotency(event_id: str) -> bool:
    """Retorna True si es nuevo, False si ya se vio recientemente."""
    if event_id in _seen_ids:
        return False
    _seen_ids.add(event_id)
    _recent_ids.append(event_id)
    if len(_recent_ids) == _recent_ids.maxlen:
        # Limpieza simple para evitar crecer sin límite
        while len(_seen_ids) > _recent_ids.maxlen:
            old = _recent_ids.popleft()
            _seen_ids.discard(old)
    return True


@app.post("/events")
async def receive_event(request: Request, event: EventPayload):
    """Recibe eventos, valida API Key e idempotencia, publica en Pub/Sub."""
    # Validación de API Key
    api_key = request.headers.get("X-API-KEY", "")
    if not INGEST_API_KEY or api_key != INGEST_API_KEY:
        log_structured("API Key inválida en ingesta", {"client_ip": request.client.host}, severity="WARNING")
        raise HTTPException(status_code=401, detail="No autorizado")

    if not _check_idempotency(event.event_id):
        log_structured("Evento duplicado recibido", {"event_id": event.event_id}, severity="INFO")
        return {"status": "duplicate"}

    event_dict = event.dict()
    try:
        future = publisher.publish(topic_path, json.dumps(event_dict).encode("utf-8"))
        message_id = future.result()
        log_structured(
            "Evento aceptado y publicado",
            {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "camera_id": event.camera_id,
                "message_id": message_id,
                "topic": TOPIC_NAME,
            },
        )
        return {"status": "accepted", "message_id": message_id, "topic": TOPIC_NAME}
    except (gcp_exceptions.GoogleAPICallError, gcp_exceptions.RetryError) as err:
        log_structured(
            "Falla al publicar en Pub/Sub",
            {"event_id": event.event_id, "error": str(err)},
            severity="ERROR",
        )
        raise HTTPException(status_code=500, detail="Error al publicar evento") from err
    except Exception as err:  # noqa: BLE001
        log_structured(
            "Error inesperado en ingesta",
            {"event_id": event.event_id, "error": str(err)},
            severity="ERROR",
        )
        raise HTTPException(status_code=500, detail="Error inesperado") from err


@app.get("/health")
async def health():
    """Endpoint simple para verificar salud del servicio en Cloud Run."""
    return {"status": "ok"}
