import pandas as pd
from google.cloud import firestore
from sklearn.ensemble import RandomForestRegressor
from datetime import datetime
import numpy as np

# Configuración
db_name = "tu-nombre-de-base-de-datos-de-pulumi" # <--- EL MISMO NOMBRE AQUÍ
db = firestore.Client(database=db_name)

def train_and_predict(target_hour, target_minute):
    print("📥 Descargando datos históricos de Firestore...")
    
    # Bajamos los eventos
    docs = db.collection("events").stream()
    data = []
    for doc in docs:
        d = doc.to_dict()
        if "received_at" in d and "people_count" in d:
            data.append(d)
    
    if not data:
        print("❌ No hay datos para entrenar. ¿Corriste el seeder.py?")
        return

    # Convertimos a DataFrame (Tabla)
    df = pd.DataFrame(data)
    df['dt'] = pd.to_datetime(df['received_at'])
    
    # --- INGENIERÍA DE CARACTERÍSTICAS (FEATURE ENGINEERING) ---
    # La IA no entiende fechas, entiende números.
    # Convertimos la fecha en: Hora del día (0-23) y Minuto (0-59)
    df['hour'] = df['dt'].dt.hour
    df['minute'] = df['dt'].dt.minute
    # df['day_of_week'] = df['dt'].dt.dayofweek # Podríamos añadir esto también

    # X = Datos de entrada (Hora, Minuto)
    X = df[['hour', 'minute']]
    # y = Lo que queremos predecir (Cantidad de personas)
    y = df['people_count']

    print(f"🧠 Entrenando modelo con {len(df)} registros...")
    
    # Usamos Random Forest (es excelente para capturar patrones no lineales)
    model = RandomForestRegressor(n_estimators=100, random_state=42)
    model.fit(X, y)
    
    # --- PREDICCIÓN ---
    print(f"🔮 Consultando al oráculo para las {target_hour}:{target_minute}...")
    prediction_input = np.array([[target_hour, target_minute]])
    predicted_count = model.predict(prediction_input)[0]
    
    print("-" * 40)
    print(f"📊 REPORTE DE PREDICCIÓN")
    print(f"🕒 Hora consultada: {target_hour:02d}:{target_minute:02d}")
    print(f"👥 Aglomeración estimada: {int(predicted_count)} personas")
    
    if predicted_count > 10:
        print("⚠️ ALERTA: Probabilidad alta de aglomeración.")
    else:
        print("✅ Estado: Tráfico normal.")
    print("-" * 40)

if __name__ == "__main__":
    # ¡Prueba cambiándole la hora aquí!
    train_and_predict(8, 10) # ¿Qué pasará a las 8:10 AM?