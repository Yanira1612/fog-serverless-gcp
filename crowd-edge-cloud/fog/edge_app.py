import json
import logging
import os
import random
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Tuple

import requests
import yaml

from buffer import DiskBuffer
from events import build_event

# Configuración de logs para el nodo fog
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fog-node")


def load_config() -> Dict:
    """Carga configuraciones desde YAML."""
    with open(Path(__file__).parent / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def smooth_count(count: int, window: Deque[int], max_len: int = 5) -> int:
    """Suaviza el conteo con promedio móvil simple."""
    window.append(count)
    while len(window) > max_len:
        window.popleft()
    return int(sum(window) / len(window))


def classify_event(count: int, thresholds: Dict[str, int], prev_trend: List[int]) -> Tuple[str, List[int]]:
    """Clasifica el evento según conteo y tendencia."""
    prev_trend.append(count)
    if len(prev_trend) > 3:
        prev_trend.pop(0)
    if count >= thresholds.get("people_high", 50):
        return "CROWD_GATHERING", prev_trend
    if len(prev_trend) >= 3 and prev_trend[-1] - prev_trend[-3] >= thresholds.get("rapid_accumulation", 20):
        return "SUDDEN_SPIKE", prev_trend
    return "PEOPLE_COUNT_UPDATE", prev_trend


def send_event(endpoint: str, event: Dict, api_key: str, attempt: int = 1) -> bool:
    """Envía evento al endpoint protegido con API Key, con backoff simple."""
    headers = {"X-API-KEY": api_key} if api_key else {}
    try:
        resp = requests.post(endpoint, json=event, headers=headers, timeout=8)
        if resp.status_code == 200:
            logger.info("Evento enviado: %s", event["event_id"])
            return True
        logger.warning("HTTP %s al enviar evento %s: %s", resp.status_code, event["event_id"], resp.text)
        return False
    except requests.RequestException as err:
        backoff = min(5 * attempt, 30)
        logger.error("Falla de red al enviar evento %s: %s (reintento en %ss)", event["event_id"], err, backoff)
        time.sleep(backoff)
        return False


def flush_buffer(buffer: DiskBuffer, endpoint: str, api_key: str) -> None:
    """Reintenta eventos pendientes del buffer."""
    resent = buffer.flush(lambda ev: send_event(endpoint, ev, api_key))
    if resent:
        logger.info("Reenviados %s eventos pendientes", resent)


def simulate_once(endpoint: str, cameras: List[str], thresholds: Dict[str, int], buffer: DiskBuffer, api_key: str, state: Dict[str, Deque[int]], trend: Dict[str, List[int]]) -> None:
    """Genera eventos simulados por cámara."""
    flush_buffer(buffer, endpoint, api_key)
    for camera_id in cameras:
        raw_count = random.randint(5, 90)
        smoothed = smooth_count(raw_count, state[camera_id])
        event_type, trend[camera_id] = classify_event(smoothed, thresholds, trend[camera_id])
        event = build_event(event_type, camera_id, smoothed).to_dict()
        if not send_event(endpoint, event, api_key):
            buffer.save_event(event)
            logger.info("Evento guardado para reintento: %s", event["event_id"])


def simulate_forever(config: Dict, buffer: DiskBuffer, api_key: str) -> None:
    """Bucle de simulación pura (sin cámara)."""
    endpoint = config["endpoint"]
    send_interval = int(config.get("send_interval_seconds", 5))
    retry_interval = int(config.get("retry_interval_seconds", send_interval))
    camera_ids = config.get("camera_ids", ["cam-1"])
    thresholds = config.get("thresholds", {})

    state = {cam: deque(maxlen=5) for cam in camera_ids}
    trend = {cam: [] for cam in camera_ids}

    logger.info("Modo simulado activo hacia %s", endpoint)
    while True:
        simulate_once(endpoint, camera_ids, thresholds, buffer, api_key, state, trend)
        time.sleep(send_interval)
        flush_buffer(buffer, endpoint, api_key)
        time.sleep(max(retry_interval - send_interval, 0))


def camera_loop(config: Dict, buffer: DiskBuffer, api_key: str) -> None:
    """Modo cámara real con YOLO si está disponible; si falta, se degrada a simulado."""
    try:
        import cv2  # type: ignore
        from ultralytics import YOLO  # type: ignore
    except Exception as err:  # noqa: BLE001
        logger.error("Dependencias de cámara/YOLO no disponibles: %s. Usando modo simulado.", err)
        simulate_forever(config, buffer, api_key)
        return

    endpoint = config["endpoint"]
    source = config.get("camera_source", 0)
    camera_id = config.get("camera_id", "cam-webcam-1")
    thresholds = config.get("thresholds", {})
    min_interval = int(config.get("min_interval_seconds", 5))

    logger.info("Modo cámara activo. Fuente: %s", source)
    model = YOLO("yolov8n.pt")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        logger.error("No se pudo abrir la cámara/stream. Usando modo simulado.")
        simulate_forever(config, buffer, api_key)
        return

    last_sent = 0.0
    smooth_window = deque(maxlen=5)
    trend = []
    while True:
        ret, frame = cap.read()
        if not ret:
            logger.warning("Frame no disponible, reintento en 2s")
            time.sleep(2)
            continue

        results = model(frame, classes=0, verbose=False)  # Solo personas
        raw_count = len(results[0].boxes)
        smoothed = smooth_count(raw_count, smooth_window)
        event_type, trend = classify_event(smoothed, thresholds, trend)
        now = time.time()

        if now - last_sent >= min_interval:
            event = build_event(event_type, camera_id, smoothed).to_dict()
            if send_event(endpoint, event, api_key):
                last_sent = now
            else:
                buffer.save_event(event)

        flush_buffer(buffer, endpoint, api_key)


def main() -> None:
    """Selecciona modo: camera (YOLO) o simulated."""
    config = load_config()
    endpoint = os.getenv("FOG_ENDPOINT", config.get("endpoint", ""))
    api_key = os.getenv("FOG_API_KEY", config.get("api_key", ""))
    if not api_key:
        logger.warning("API Key no definida; el servicio de ingesta rechazará las peticiones.")
    if not endpoint:
        logger.error("Endpoint no definido; establece FOG_ENDPOINT o config.yaml.")
        return

    buffer_path = config.get("buffer_file", "./fog_buffer/events_pending.jsonl")
    Path(buffer_path).parent.mkdir(parents=True, exist_ok=True)
    buffer = DiskBuffer(buffer_path)

    mode = config.get("mode", "simulated").lower()
    if mode == "camera":
        camera_loop(config, buffer, api_key)
    else:
        simulate_forever({**config, "endpoint": endpoint}, buffer, api_key)


if __name__ == "__main__":
    main()
