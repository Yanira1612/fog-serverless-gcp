import logging
import os
import smtplib
from collections import Counter
from email.mime.text import MIMEText
from typing import Dict, Optional

from flask import Flask, jsonify, request, make_response
from flask_cors import CORS
from google.cloud import firestore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-analyst")

app = Flask(__name__)
CORS(app)

API_TOKEN = os.getenv("ANALYST_API_TOKEN")
DB_NAME = os.getenv("DB_NAME")
GMAIL_USER = os.environ.get("GMAIL_USER", "ysuniq@unsa.edu.pe")
GMAIL_PASS = os.environ.get("GMAIL_PASS", "ewtm cyks jepw pmsv")

try:
    db: Optional[firestore.Client] = firestore.Client(database=DB_NAME) if DB_NAME else firestore.Client()
    logger.info("Firestore inicializado para base: %s", DB_NAME or "(default)")
except Exception as err:  # noqa: BLE001
    logger.error("No se pudo inicializar Firestore: %s", err)
    db = None


def _auth_ok() -> bool:
    """Valida token simple (API key o Bearer)."""
    if not API_TOKEN:
        return True  # demo sin token configurado

    header = request.headers.get("Authorization", "")
    bearer = header.replace("Bearer", "").strip()
    token = request.headers.get("X-API-KEY") or bearer
    return token == API_TOKEN


def _safe_int(value: object) -> int:
    try:
        return int(value)
    except Exception:  # noqa: BLE001
        return 0


def _send_email_alert(prediction: str, probability: float) -> None:
    """Envia un correo simple cuando se detecta evento de crowd con alta probabilidad."""
    if not GMAIL_USER or not GMAIL_PASS:
        logger.debug("Correo no enviado: GMAIL_USER/GMAIL_PASS no configurados")
        return
    if "CROWD" not in prediction:
        return

    msg = MIMEText(
        f"Alerta de Sistema Fog\n\nPredicción: {prediction}\nProbabilidad: {probability}%"
    )
    msg["Subject"] = "ALERTA: Probable Aglomeración"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_PASS)
            server.sendmail(GMAIL_USER, [GMAIL_USER], msg.as_string())
        logger.info("Correo de alerta enviado")
    except Exception as err:  # noqa: BLE001
        logger.error("Error enviando correo de alerta: %s", err)


def _train_markov() -> Optional[Dict[str, list]]:
    """Modelo simple de transiciones por tipo de evento."""
    if not db:
        return None
    docs = db.collection("events").order_by("received_at").stream()
    events = [doc.to_dict().get("event_type") for doc in docs]
    events = [e for e in events if e]
    if len(events) < 2:
        return None

    transitions: Dict[str, list] = {}
    for i in range(len(events) - 1):
        curr, nxt = events[i], events[i + 1]
        transitions.setdefault(curr, []).append(nxt)
    return transitions


@app.before_request
def enforce_auth() -> Optional[tuple]:
    if request.method == "OPTIONS":
        resp = make_response()
        resp.status_code = 200  # permitir preflight sin auth
        return resp
    if request.path in ("/health", "/"):
        return None
    if not _auth_ok():
        return jsonify({"error": "No autorizado"}), 401
    return None


@app.route("/metrics", methods=["GET"])
def get_metrics():
    if not db:
        return jsonify({"error": "Firestore no disponible"}), 500

    docs = db.collection("events").stream()
    total, type_counts, cam_counts = 0, {}, {}
    hourly_data: Dict[str, Dict[str, int]] = {}

    for doc in docs:
        d = doc.to_dict()
        total += 1

        people_count = _safe_int(
            d.get("people_count") or d.get("peopleCount") or 0
        )
        event_type = d.get("event_type", "N/A")
        camera_id = d.get("camera_id", "N/A")

        type_counts[event_type] = type_counts.get(event_type, 0) + 1
        cam_counts[camera_id] = cam_counts.get(camera_id, 0) + 1

        ts = d.get("received_at")
        if not ts:
            continue
        ts_str = str(ts)
        if " " in ts_str:
            hour = ts_str.split(" ")[1][:2]
        elif "T" in ts_str:
            hour = ts_str.split("T")[1][:2]
        else:
            hour = ts_str[:2]

        hour_label = f"{hour}:00"
        hourly_data.setdefault(hour_label, {"events": 0, "people": 0})
        hourly_data[hour_label]["events"] += 1
        hourly_data[hour_label]["people"] += people_count

    peak_hour, peak_avg = "N/A", 0
    if hourly_data:
        peak_hour = max(hourly_data, key=lambda k: hourly_data[k]["people"])
        data_peak = hourly_data[peak_hour]
        if data_peak["events"] > 0:
            peak_avg = round(data_peak["people"] / data_peak["events"], 1)

    latest_event = "UNKNOWN"
    last_doc = (
        db.collection("events")
        .order_by("received_at", direction=firestore.Query.DESCENDING)
        .limit(1)
        .get()
    )
    if last_doc:
        latest_event = last_doc[0].to_dict().get("event_type", "UNKNOWN")

    return jsonify(
        {
            "total_events": total,
            "distribution": type_counts,
            "cameras": cam_counts,
            "peak_hour": peak_hour,
            "peak_avg_people": peak_avg,
            "hourly_counts": {h: v["events"] for h, v in sorted(hourly_data.items())},
            "latest_event": latest_event,
        }
    ), 200


@app.route("/predict_next", methods=["GET"])
def predict_next_event():
    if not db:
        return jsonify({"error": "Firestore no disponible"}), 500

    current_event = request.args.get("current_event")
    if not current_event:
        return jsonify({"error": "Missing event"}), 400

    transitions = _train_markov()
    if not transitions or current_event not in transitions:
        return jsonify({"prediction": "UNKNOWN", "probability": 0.0})

    possible = transitions[current_event]
    most_common = Counter(possible).most_common(1)[0]
    next_evt, prob = most_common[0], (most_common[1] / len(possible)) * 100

    # Alerta opcional por correo si hay alto riesgo de aglomeración
    if prob >= 70 and "CROWD" in next_evt:
        _send_email_alert(next_evt, round(prob, 2))

    return jsonify(
        {
            "current_state": current_event,
            "prediction": next_evt,
            "probability": round(prob, 2),
            "total_samples": len(possible),
        }
    )


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "fog-analyst"}), 200


@app.route("/", methods=["GET"])
def root():
    return jsonify({"service": "fog-analyst"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
