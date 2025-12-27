import base64
import json
import os
from flask import Flask, request, jsonify
from google.cloud import firestore

app = Flask(__name__)

# Inicializamos Firestore una sola vez (fuera de las funciones)
# Google detecta automáticamente las credenciales en Cloud Run
db = firestore.Client()
COLLECTION_NAME = "eventos_aglomeracion"

@app.route("/events", methods=["POST"])
def receive_event():
    """
    Recibe el evento PUSH de Pub/Sub.
    El mensaje real está dentro de ['message']['data'] codificado en base64.
    """
    envelope = request.json
    if not envelope:
        return "Bad Request: no Pub/Sub message received", 400

    if not isinstance(envelope, dict) or "message" not in envelope:
        return "Bad Request: invalid Pub/Sub message format", 400

    try:
        # 1. Decodificar el mensaje de Pub/Sub
        pubsub_message = envelope["message"]
        
        if isinstance(pubsub_message, dict) and "data" in pubsub_message:
            data_bytes = base64.b64decode(pubsub_message["data"])
            evento_json = json.loads(data_bytes.decode("utf-8"))
            
            print(f"📥 Evento recibido: {evento_json.get('event_type')}")

            # 2. Guardar en Firestore
            # Usamos .add() para que genere un ID automático, o .document().set() si quieres controlar el ID
            db.collection(COLLECTION_NAME).add(evento_json)
            
            print("✅ Guardado en Firestore")
            
        return jsonify({"status": "success"}), 200

    except Exception as e:
        print(f"❌ Error procesando evento: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/", methods=["GET"])
def health():
    return "Cloud Run Fog Ingestion Ready", 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)