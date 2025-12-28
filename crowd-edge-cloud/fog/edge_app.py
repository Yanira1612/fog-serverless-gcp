import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Dict, List

import requests
import yaml

from buffer import DiskBuffer
from events import build_event

# Configuración de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fog-node")


def load_config() -> Dict:
    """Carga configuraciones desde YAML."""
    with open(Path(__file__).parent / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def pick_event_type(people_count: int, thresholds: Dict[str, int]) -> str:
    """Selecciona tipo de evento según umbrales."""
    if people_count >= thresholds.get("people_high", 50):
        return "CROWD_GATHERING_DETECTED"
    # Usamos rapid_accumulation como el umbral base para detectar algo interesante
    if people_count >= thresholds.get("rapid_accumulation", 3):
        return "RAPID_ACCUMULATION"
    return "PEOPLE_COUNT_UPDATE"


def send_event(endpoint: str, event: Dict, api_key: str) -> bool:
    """Envía evento al endpoint protegido con API Key."""
    headers = {"X-API-KEY": api_key} if api_key else {}
    try:
        resp = requests.post(endpoint, json=event, headers=headers, timeout=8)
        if resp.status_code == 200:
            logger.info("✅ Evento enviado: %s (Personas: %s)", event["event_id"], event.get("people_count"))
            return True
        elif resp.status_code == 401:
             logger.error("⛔ Error API Key (401). Verifica config.yaml")
             return False
        
        logger.warning("⚠️ Servidor rechazó (%s): %s", resp.status_code, resp.text)
        return False
    except requests.RequestException as err:
        logger.error("❌ Falla de red: %s", err)
        return False


def flush_buffer(buffer: DiskBuffer, endpoint: str, api_key: str) -> None:
    """Reintenta eventos pendientes del buffer."""
    resent = buffer.flush(lambda ev: send_event(endpoint, ev, api_key))
    if resent:
        logger.info("🔄 Reenviados %s eventos pendientes", resent)


def simulate_forever(config: Dict, buffer: DiskBuffer, api_key: str) -> None:
    """Modo simulación (Solo se usa si mode='simulated')."""
    endpoint = config["endpoint"]
    logger.warning("⚠️ MODO SIMULACIÓN ACTIVO (Datos Falsos) ⚠️")
    while True:
        # Genera datos falsos
        people = random.randint(5, 20)
        event = build_event("SIMULATED_EVENT", "SIM-CAM-01", people).to_dict()
        if not send_event(endpoint, event, api_key):
             buffer.save_event(event)
        time.sleep(5)


def camera_loop(config: Dict, buffer: DiskBuffer, api_key: str) -> None:
    """Modo cámara real con lógica de filtrado inteligente."""
    try:
        import cv2
        from ultralytics import YOLO
    except ImportError:
        logger.error("❌ ERROR: No tienes 'opencv-python' o 'ultralytics' instalados.")
        return

    endpoint = config["endpoint"]
    source = config.get("camera_source", 0)
    camera_id = config.get("camera_id", "cam-webcam-1")
    
    # Leemos el umbral mínimo para enviar alertas (igual que tu código anterior)
    min_threshold = config.get("thresholds", {}).get("rapid_accumulation", 3)
    min_interval = int(config.get("min_interval_seconds", 5))

    logger.info(f"📡 Conectando a cámara: {source}")
    model = YOLO("yolov8n.pt")
    cap = cv2.VideoCapture(source)

    if not cap.isOpened():
        logger.error(f"❌ ERROR CRÍTICO: No se pudo abrir la cámara: {source}")
        logger.error("   -> Verifica que el celular y la laptop estén en el MISMO WiFi.")
        return

    logger.info("👀 Vigilancia iniciada. Solo se enviarán alertas si personas >= %s", min_threshold)
    
    last_sent = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            logger.warning("⚠️ Frame vacío o error de cámara. Reintentando...")
            time.sleep(1)
            # Intento simple de reconexión si es IP
            if isinstance(source, str) and source.startswith("http"):
                 cap.release()
                 cap = cv2.VideoCapture(source)
            continue

        # Detección
        # Reducimos tamaño para velocidad, igual que tu código
        frame_small = cv2.resize(frame, (640, 480))
        results = model(frame_small, classes=0, verbose=False)
        people_count = len(results[0].boxes)

        # Visualización
        annotated_frame = results[0].plot()
        cv2.imshow(f"Fog Node: {camera_id}", annotated_frame)

        # --- LÓGICA DE NEGOCIO (IGUAL A LA TUYA) ---
        now = time.time()
        
        # Solo enviamos si supera el umbral Y pasó el tiempo
        if people_count >= min_threshold and (now - last_sent >= min_interval):
            
            logger.info(f"🚨 AGLOMERACIÓN DETECTADA: {people_count} personas.")
            
            # Determinamos el tipo de evento (Alerta vs Acumulación)
            event_type = pick_event_type(people_count, config.get("thresholds", {}))
            
            event = build_event(event_type, camera_id, people_count).to_dict()
            
            if send_event(endpoint, event, api_key):
                last_sent = now
            else:
                buffer.save_event(event)
        
        # Procesar buffer en segundo plano (si hubo fallos previos)
        flush_buffer(buffer, endpoint, api_key)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


def main() -> None:
    config = load_config()
    endpoint = os.getenv("FOG_ENDPOINT", config.get("endpoint", ""))
    api_key = os.getenv("FOG_API_KEY", config.get("api_key", ""))
    
    if not endpoint:
        logger.error("❌ Endpoint no definido en config.yaml")
        return

    # Buffer para persistencia local
    buffer_path = config.get("buffer_file", "./fog_buffer/events_pending.jsonl")
    Path(buffer_path).parent.mkdir(parents=True, exist_ok=True)
    buffer = DiskBuffer(buffer_path)

    # Selección de modo
    mode = config.get("mode", "simulated").lower()
    
    if mode == "camera":
        camera_loop(config, buffer, api_key)
    else:
        simulate_forever({**config, "endpoint": endpoint}, buffer, api_key)


if __name__ == "__main__":
    main()