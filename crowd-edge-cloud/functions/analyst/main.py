import os
import logging
from flask import Flask, request, jsonify
from google.cloud import firestore
import pandas as pd
from collections import Counter

# Configuración
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-analyst")

app = Flask(__name__)


import os
import logging
import smtplib
from email.mime.text import MIMEText
from collections import Counter
from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import firestore

# Configuración de Logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-analyst")

app = Flask(__name__)
CORS(app)
# Conexión a Firestore

# Conexión a BD
#db_name = os.environ.get("DB_NAME", "(default)")

db_name = "default-firestore-9c92172"
logger.info(f"🧪 PRUEBA MANUAL: Conectando a {db_name}")
db = firestore.Client(database=db_name)

# Conexión a la BD
try:
    db = firestore.Client(database=db_name)
    logger.info(f"✅ Conectado manualmente a: {db_name}")
except Exception as e:
    logger.error(f"❌ Error conectando a Firestore: {e}")

# --- CONFIGURACIÓN DE CORREO (Opcional) ---
# Para que funcione, necesitas generar una "Contraseña de Aplicación" en Gmail
GMAIL_USER = os.environ.get("GMAIL_USER", "ysuniq@unsa.edu.pe")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "teamomamaforecerr") 

def send_email_alert(prediction, probability):
    """Envía un correo si la predicción es crítica."""
    if "CROWD" not in prediction: # Solo alertar si es aglomeración
        return

    msg = MIMEText(f"⚠️ Alerta de Sistema Fog\n\nSe ha predicho un evento de: {prediction}\nCon una probabilidad del: {probability}%")
    msg['Subject'] = '🚨 ALERTA: Probable Aglomeración Detectada'
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        logger.info("📧 Correo de alerta enviado.")
    except Exception as e:
        logger.error(f"❌ Error enviando correo: {e}")

def train_markov_model():
    docs = db.collection("events").order_by("received_at").stream()
    events = [d.get("event_type") for doc in docs if (d := doc.to_dict()).get("event_type")]
    
    if len(events) < 2: return None

    transitions = {}
    for i in range(len(events) - 1):
        curr, nxt = events[i], events[i+1]
        transitions.setdefault(curr, []).append(nxt)
    return transitions


@app.route("/metrics", methods=["GET"])
def get_metrics():
    """Endpoint para el Dashboard: Estadísticas en tiempo real."""
    try:
        docs = db.collection("events").stream()
        total, type_counts, cam_counts = 0, {}, {}
        
        for doc in docs:
            d = doc.to_dict()
            total += 1
            t, c = d.get("event_type", "N/A"), d.get("camera_id", "N/A")
            type_counts[t] = type_counts.get(t, 0) + 1
            cam_counts[c] = cam_counts.get(c, 0) + 1

        return jsonify({
            "total_events": total,
            "distribution": type_counts,
            "cameras": cam_counts
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/predict_next", methods=["GET"])
def predict_next_event():
    current_event = request.args.get('current_event')
    if not current_event: return jsonify({"error": "Missing current_event"}), 400

    transitions = train_markov_model()
    if not transitions or current_event not in transitions:
        return jsonify({"prediction": "UNKNOWN", "probability": 0.0})

    possible = transitions[current_event]
    most_common = Counter(possible).most_common(1)[0]
    next_evt, prob = most_common[0], (most_common[1] / len(possible)) * 100

    # DISPARAR ALERTA SI ES CRÍTICO
    if prob > 70 and "CROWD" in next_evt:
        send_email_alert(next_evt, round(prob, 2))

    return jsonify({
        "current_state": current_event,
        "prediction": next_evt,
        "probability": round(prob, 2),
        "total_samples": len(possible)
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))