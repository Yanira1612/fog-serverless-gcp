import logging
import os
from datetime import datetime, timedelta
from typing import List

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from google.cloud import firestore

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("fog-dashboard")

PROJECT_ID = os.getenv("PROJECT_ID", "fog-serverless")
DASHBOARD_API_TOKEN = os.getenv("DASHBOARD_API_TOKEN", "")

db = firestore.Client(project=PROJECT_ID)
app = FastAPI(title="Fog Dashboard API", version="1.0.0")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def index():
    """Entrega el frontend sencillo del dashboard."""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


def auth(req: Request):
    """Autenticación simple por bearer token (placeholder de Identity Platform)."""
    auth_header = req.headers.get("Authorization", "")
    parts = auth_header.split()
    token = parts[1] if len(parts) == 2 and parts[0].lower() == "bearer" else ""
    if not token or token != DASHBOARD_API_TOKEN:
        raise HTTPException(status_code=401, detail="No autorizado")
    return True


@app.get("/metrics")
def metrics(_: bool = Depends(auth)):
    """Eventos por cámara en las últimas 24h."""
    since = datetime.utcnow() - timedelta(hours=24)
    query = db.collection("events").where("timestamp", ">=", since.isoformat())
    counts = {}
    for doc in query.stream():
        data = doc.to_dict()
        cam = data.get("camera_id", "unknown")
        counts[cam] = counts.get(cam, 0) + 1
    return {"window_hours": 24, "events_per_camera": counts}


@app.get("/alerts")
def alerts(_: bool = Depends(auth)):
    """Últimas alertas de aglomeración."""
    query = (
        db.collection("events")
        .where("event_type", "in", ["CROWD_GATHERING", "PROLONGED_CROWD"])
        .order_by("timestamp", direction=firestore.Query.DESCENDING)
        .limit(20)
    )
    alerts: List[dict] = []
    for doc in query.stream():
        alerts.append(doc.to_dict())
    return {"alerts": alerts}


@app.get("/predictions")
def predictions(_: bool = Depends(auth)):
    """Predicciones simuladas (placeholder) para siguiente evento probable."""
    # Aquí se conectaría BigQuery/Vertex AI; devolvemos stub estático
    return {
        "model": "placeholder-markov",
        "next_event_probabilities": {
            "CROWD_GATHERING": 0.4,
            "SUDDEN_SPIKE": 0.3,
            "PROLONGED_CROWD": 0.2,
            "CAMERA_OFFLINE": 0.1,
        },
        "explanation": "Probabilidades estimadas basadas en frecuencias recientes.",
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "fog-dashboard"}
