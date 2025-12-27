import json
import logging
import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from google.api_core import exceptions as gcp_exceptions
from google.cloud import pubsub_v1
from pydantic import BaseModel, Field

# Configuración básica de logging estructurado en JSON
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fog-ingest")

# Configuración de Pub/Sub y proyecto
PROJECT_ID = os.getenv("PROJECT_ID", "fog-serverless")
TOPIC_NAME = os.getenv("TOPIC_NAME", "fog-events")

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_NAME)


class EventPayload(BaseModel):
    """Estructura mínima esperada para eventos simulados desde el fog."""

    event_id: str = Field(..., description="Identificador único del evento")
    event_type: str = Field(..., description="Tipo de evento desde el fog")
    camera_id: str = Field(..., description="Identificador de la cámara de borde")
    timestamp: str = Field(..., description="Marca de tiempo ISO8601 del evento")
    people_count: int | None = Field(
        None, description="Cantidad de personas detectadas cuando aplique"
    )


app = FastAPI(title="Fog Ingestion Service", version="1.0.0")


def log_structured(message: str, payload: Dict[str, Any], severity: str = "INFO") -> None:
    """Emite logs en formato JSON para facilitar análisis en Cloud Logging."""
    log_entry = {"severity": severity, "message": message, "payload": payload}
    logger.info(json.dumps(log_entry))


@app.post("/events")
async def receive_event(event: EventPayload):
    """Recibe eventos simulados, valida campos y publica en Pub/Sub."""
    event_dict = event.dict()
    try:
        future = publisher.publish(topic_path, json.dumps(event_dict).encode("utf-8"))
        message_id = future.result()
        log_structured(
            "Evento aceptado y publicado en Pub/Sub",
            {"event_id": event.event_id, "message_id": message_id},
        )
        return {"status": "accepted", "message_id": message_id}
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
