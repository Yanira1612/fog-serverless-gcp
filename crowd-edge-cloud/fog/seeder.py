import random
from datetime import datetime, timedelta, timezone
from google.cloud import firestore
import os

# Configuración (Asegúrate de tener tus credenciales o estar logueado con gcloud)
db_name = "tu-nombre-de-base-de-datos-de-pulumi" # <--- PON EL NOMBRE DE TU BD AQUÍ (el que vimos en la foto: default-firestore-xxxx)
# Si no sabes el nombre, prueba dejándolo como "(default)" o None si usas la default.
db = firestore.Client(database=db_name)

def generate_fake_data():
    print("🌱 Sembrando datos históricos ficticios...")
    
    batch = db.batch()
    events_ref = db.collection("events")
    
    # Generamos datos de los últimos 7 días
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    
    current_date = start_date
    count = 0

    while current_date < end_date:
        # Lógica de "Horas Pico":
        # Hacemos que a las 8am y 6pm (18h) haya más gente
        hour = current_date.hour
        base_people = random.randint(0, 5)
        
        if 7 <= hour <= 9: # Pico de la mañana
            people = base_people + random.randint(10, 20)
        elif 17 <= hour <= 19: # Pico de la tarde
            people = base_people + random.randint(15, 25)
        else:
            people = base_people # Horas tranquilas

        # Crear evento falso
        event_id = f"hist_{int(current_date.timestamp())}"
        doc_ref = events_ref.document(event_id)
        
        data = {
            "event_id": event_id,
            "camera_id": "CAM-SIMULADA-01",
            "event_type": "CROWD_GATHERING_DETECTED",
            "people_count": people,
            "received_at": current_date.isoformat()
        }
        
        batch.set(doc_ref, data)
        count += 1
        
        # Avanzamos 30 minutos
        current_date += timedelta(minutes=30)

        # Firestore permite max 500 ops por batch
        if count % 400 == 0:
            batch.commit()
            batch = db.batch()
            print(f"   ... {count} eventos insertados.")

    batch.commit()
    print("✅ ¡Datos históricos sembrados! Ahora tu IA tiene algo que aprender.")

if __name__ == "__main__":
    generate_fake_data()