import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, List

import requests
import yaml

from buffer import DiskBuffer
from events import build_event

# Configuración de logging simple para la simulación
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fog-simulator")


def load_config() -> Dict:
    """Carga la configuración YAML para la simulación."""
    with open(Path(__file__).parent / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pick_event_type(people_count: int, thresholds: Dict[str, int]) -> str:
    """Selecciona el tipo de evento según umbrales y aleatoriedad."""
    if people_count >= thresholds.get("people_high", 50):
        return "CROWD_GATHERING_DETECTED"
    if people_count >= thresholds.get("rapid_accumulation", 20):
        return "RAPID_ACCUMULATION"
    return "PEOPLE_COUNT_UPDATE"


def send_event(endpoint: str, event: Dict) -> bool:
    """Envía un evento al endpoint HTTP; retorna True si fue exitoso."""
    try:
        response = requests.post(endpoint, json=event, timeout=5)
        if response.status_code == 200:
            logger.info("Evento enviado: %s", event["event_id"])
            return True
        logger.error("Falla HTTP %s para evento %s", response.status_code, event["event_id"])
        return False
    except requests.RequestException as err:
        logger.error("Error de red al enviar evento %s: %s", event["event_id"], err)
        return False


def simulate_once(endpoint: str, cameras: List[str], thresholds: Dict[str, int], buffer: DiskBuffer) -> None:
    """Genera eventos para cada cámara y los envía, con buffer de respaldo."""
    # Reintentar primero los pendientes en disco
    resent = buffer.flush(lambda ev: send_event(endpoint, ev))
    if resent:
        logger.info("Reenviados %s eventos pendientes", resent)

    for camera_id in cameras:
        people_count = random.randint(5, 80)
        event_type = pick_event_type(people_count, thresholds)
        event = build_event(event_type, camera_id, people_count).to_dict()

        if not send_event(endpoint, event):
            buffer.save_event(event)
            logger.info("Evento guardado en buffer para reintento: %s", event["event_id"])


def main() -> None:
    """Ciclo principal de simulación periódica."""
    config = load_config()
    endpoint = config["endpoint"]
    send_interval = int(config.get("send_interval_seconds", 5))
    retry_interval = int(config.get("retry_interval_seconds", send_interval))
    camera_ids = config.get("camera_ids", ["cam-1"])
    thresholds = config.get("thresholds", {})

    buffer_path = config.get("buffer_file", "./fog_buffer/events_pending.jsonl")
    Path(buffer_path).parent.mkdir(parents=True, exist_ok=True)
    buffer = DiskBuffer(buffer_path)

    logger.info("Iniciando simulador Fog hacia %s", endpoint)
    while True:
        simulate_once(endpoint, camera_ids, thresholds, buffer)
        time.sleep(send_interval)
        # Espaciado para reintentos fuera del ciclo si no hay nuevos eventos
        buffer.flush(lambda ev: send_event(endpoint, ev))
        time.sleep(max(retry_interval - send_interval, 0))


if __name__ == "__main__":
    main()
