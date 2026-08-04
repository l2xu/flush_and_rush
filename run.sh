#!/usr/bin/with-contenv bashio

set -e

bashio::log.info "Starte Klo-Tracker Add-on"
bashio::log.info "Sensor: $(bashio::config 'sensor_entity_id')"
bashio::log.info "Invertiert: $(bashio::config 'sensor_inverted')"

export SENSOR_ENTITY_ID="$(bashio::config 'sensor_entity_id')"
export SENSOR_INVERTED="$(bashio::config 'sensor_inverted')"
export KLO_TRACKER_DB_PATH="/data/klo_tracker.db"

bashio::log.info "DB: ${KLO_TRACKER_DB_PATH}"

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8099