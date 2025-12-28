# Dashboard y visualización

## Esquema de datos en Firestore
- Colección `events` con documentos que incluyen:
  - `camera_id`: identificador de la cámara de borde.
  - `timestamp`: marca de tiempo ISO 8601 del evento.
  - `people_count`: número de personas estimadas/simuladas.
  - `event_type`: tipo de evento (`PEOPLE_COUNT_UPDATE`, `RAPID_ACCUMULATION`, `CROWD_GATHERING_DETECTED`).

## Consultas de ejemplo
- Total de eventos por cámara.
- Eventos por tipo.
- Línea de tiempo de aglomeraciones.

Ejemplos en `dashboard/queries.sql` (puedes usarlos en BigQuery si exportas Firestore o en un conector SQL equivalente).

## Uso en Looker Studio
1. Exporta la colección `events` de Firestore hacia BigQuery (o usa el conector nativo de Firestore).
2. Conecta Looker Studio al dataset (p. ej. `fog_analytics.events`).
3. Crea:
   - Gráfico de barras: `camera_id` vs `COUNT(*)`.
   - Pie chart: `event_type` vs `COUNT(*)`.
   - Serie temporal: `timestamp` truncado a minuto/hora vs `COUNTIF(event_type = 'CROWD_GATHERING_DETECTED')`.

## Flujo recomendado
1. Ejecuta el simulador Fog (`fog/edge_app.py`) para generar eventos.
2. Verifica inserciones en Firestore (colección `events`).
3. Exporta o consulta en BigQuery y construye el dashboard con las queries de ejemplo.
