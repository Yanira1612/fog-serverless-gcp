-- Consulta: eventos por hora
SELECT
  TIMESTAMP_TRUNC(received_at, HOUR) AS hora,
  COUNT(1) AS total_eventos
FROM
  `fog_analytics.events`
GROUP BY
  hora
ORDER BY
  hora;

-- Consulta: cámaras con más aglomeraciones detectadas
SELECT
  camera_id,
  COUNTIF(event_type = 'CROWD_GATHERING_DETECTED') AS aglomeraciones,
  COUNT(1) AS total_eventos
FROM
  `fog_analytics.events`
GROUP BY
  camera_id
ORDER BY
  aglomeraciones DESC
LIMIT 10;

-- Consulta: horas pico donde ocurren más eventos críticos
SELECT
  EXTRACT(HOUR FROM received_at) AS hora_dia,
  COUNTIF(event_type = 'RAPID_ACCUMULATION') AS acumulaciones_rapidas,
  COUNTIF(event_type = 'CROWD_GATHERING_DETECTED') AS aglomeraciones
FROM
  `fog_analytics.events`
GROUP BY
  hora_dia
ORDER BY
  (acumulaciones_rapidas + aglomeraciones) DESC;
