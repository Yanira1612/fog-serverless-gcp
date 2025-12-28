import logging
import time
import cv2
from ultralytics import YOLO
from pathlib import Path
from typing import Dict
import requests
import yaml
from datetime import datetime

# Importamos las clases de tu compañera (Buffer y Eventos)
from buffer import DiskBuffer
from events import build_event

# Configuración de logs
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("fog-node-ipcam")

def load_config() -> Dict:
    """Carga configuración desde config.yaml."""
    with open(Path(__file__).parent / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def send_event(endpoint: str, event: Dict) -> bool:
    """Envía el evento a Cloud Run."""
    try:
        response = requests.post(endpoint, json=event, timeout=12)
        if response.status_code == 200:
            logger.info("✅ Evento enviado a Cloud Run: %s", event["event_type"])
            return True
        else:
            logger.warning("⚠️ Servidor rechazó (%s): %s", response.status_code, response.text)
            return False
    except requests.RequestException as err:
        logger.error("❌ Error de Red (Guardando en Buffer): %s", err)
        return False

def run_ip_camera_fog():
    # 1. Cargar Configuración
    config = load_config()
    endpoint = config["endpoint"]
    camera_id = config.get("camera_ids", ["CAM-IP-GENERICA"])[0]
    threshold = config.get("thresholds", {}).get("rapid_accumulation", 3)
    
    # 2. Obtener la fuente de video del YAML
    # Si es '0' (número), OpenCV usará la webcam. Si es 'http...', usará el IP.
    source_config = config.get("camera_source", 0)
    logger.info(f"📡 Conectando a cámara: {source_config}")

    # 3. Inicializar Buffer y Modelo IA
    buffer_path = config.get("buffer_file", "./fog_buffer/events_pending.jsonl")
    buffer = DiskBuffer(buffer_path)
    
    logger.info("🧠 Cargando modelo YOLOv8...")
    model = YOLO('yolov8n.pt')

    # 4. Abrir la cámara IP
    cap = cv2.VideoCapture(source_config)
    
    # Verificación de conexión
    if not cap.isOpened():
        logger.error("❌ ERROR CRÍTICO: No se puede conectar a la cámara IP.")
        logger.error("   -> Verifica que el celular y la laptop estén en el MISMO WiFi.")
        logger.error(f"   -> Verifica la URL: {source_config}")
        return

    logger.info("👀 Vigilancia iniciada. Presiona 'q' en la ventana de video para salir.")
    
    last_sent_time = 0
    min_interval = 5.0 # Segundos mínimos entre alertas para no hacer spam

    while True:
        # A. Reintentar envíos fallidos (Buffer Flush)
        resent = buffer.flush(lambda ev: send_event(endpoint, ev))
        if resent:
            logger.info(f"🔄 Buffer recuperado: {resent} eventos enviados.")

        # B. Leer Frame
        ret, frame = cap.read()
        if not ret:
            logger.error("❌ Error leyendo frame de la IP Cam (¿Se desconectó?)")
            # Intentamos reconectar o esperar
            time.sleep(2)
            cap = cv2.VideoCapture(source_config) # Reintento simple
            continue

        # C. Procesamiento IA (YOLO)
        # Reducimos tamaño para agilizar transmisión por WiFi
        frame_small = cv2.resize(frame, (640, 480))
        results = model(frame_small, classes=0, verbose=False) # Solo personas
        people_count = len(results[0].boxes)

        # D. Visualización
        annotated_frame = results[0].plot()
        cv2.imshow(f"Fog Node: {camera_id}", annotated_frame)

        # E. Lógica de Negocio
        current_time = time.time()
        
        # Disparar evento si supera umbral Y pasó el tiempo de espera
        if people_count >= threshold and (current_time - last_sent_time) > min_interval:
            
            logger.info(f"🚨 AGLOMERACIÓN DETECTADA: {people_count} personas.")
            
            # Construir evento estándar
            event_obj = build_event("CROWD_GATHERING_DETECTED", camera_id, people_count)
            event_dict = event_obj.to_dict()
            
            # Enviar (o guardar en buffer si falla)
            if send_event(endpoint, event_dict):
                last_sent_time = current_time
            else:
                buffer.save_event(event_dict)

        # Salir con 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_ip_camera_fog()