import time
import json
import random
from datetime import datetime
from google.cloud import pubsub_v1

# --- ⚙️ CONFIGURACIÓN (LLENA ESTO) ⚙️ ---
# Usa tu ID de proyecto real (lo ves con: gcloud config get-value project)
PROJECT_ID = "fog-serverless" 

# El nombre EXACTO del tópico que creó Pulumi (seguramente es "fog-events")
TOPIC_ID = "fog-events" 
# ----------------------------------------

publisher = pubsub_v1.PublisherClient()
topic_path = publisher.topic_path(PROJECT_ID, TOPIC_ID)

def enviar_evento(datos):
    """Empaqueta el JSON y lo envía a Pub/Sub"""
    data_str = json.dumps(datos)
    data_bytes = data_str.encode("utf-8")
    
    try:
        publish_future = publisher.publish(topic_path, data_bytes)
        # Esperamos el resultado para confirmar que llegó al servidor de Pub/Sub
        message_id = publish_future.result()
        print(f"✅ [ENVIADO] ID: {message_id} | Tipo: {datos['event_type']}")
    except Exception as e:
        print(f"❌ [ERROR] No se pudo enviar: {e}")

def simular_camara():
    print(f"🚀 Iniciando simulación FOG en: projects/{PROJECT_ID}/topics/{TOPIC_ID}")
    print("Presiona Ctrl+C para detener.")

    camara_id = "CAM-UNMSM-01"
    
    while True:
        # Generar datos simulados
        personas = random.randint(0, 30)
        timestamp = datetime.now().isoformat()
        
        # Lógica FOG: ¿Enviamos evento?
        # Digamos que enviamos si hay cambio brusco o si hay mucha gente
        
        if personas > 10:
            evento = {
                "event_type": "CROWD_GATHERING_DETECTED",
                "camera_id": camara_id,
                "timestamp": timestamp,
                "people_count": personas,
                "density": round(personas / 20.0, 2), # 20m2 hipotéticos
                "message": "Posible aglomeración detectada"
            }
            enviar_evento(evento)
        
        elif random.random() < 0.3: # 30% de probabilidad de enviar un 'heartbeat' (estado normal)
            evento = {
                "event_type": "STATUS_UPDATE",
                "camera_id": camara_id,
                "timestamp": timestamp,
                "people_count": personas
            }
            enviar_evento(evento)
        else:
            print(f"💤 [FOG] Procesando localmente... (Personas: {personas} - No se envía nada)")

        time.sleep(3) # Espera 3 segundos entre "frames"

if __name__ == "__main__":
    simular_camara()