FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# AGREGA ESTA LÍNEA PARA FORZAR RECONSTRUCCIÓN:
ENV FORCE_REBUILD=1

# Comando vital para que Cloud Run no falle:
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 main:app