# Umsetzungsplan: Home Assistant Add-on "Klo-Tracker"

## Ausgangslage
Im Ordner `addons/flush_and_rush` existieren bereits folgende Basisdateien:
- `config.yaml`
- `Dockerfile`
- `run.sh`

Ziel ist ein Docker-basiertes Home Assistant Add-on mit:
- Sensor-Auslesung ueber Supervisor API
- SQLite in `/data`
- oeffentlicher Gaeste-Ansicht (mit Token)
- geschuetzter Admin-Ansicht via Ingress

---

## 1. Zielstruktur (Ordner + Dateien)

```text
addons/flush_and_rush/
├─ config.yaml                 # Add-on Manifest (HA Store Konfiguration)
├─ Dockerfile                  # Container Build
├─ run.sh                      # Container Startscript (S6/Bashio)
├─ requirements.txt            # Python-Abhaengigkeiten
├─ app/
│  ├─ main.py                  # FastAPI/Flask App + Routing
│  ├─ settings.py              # Laden/Validieren der Add-on Optionen
│  ├─ supervisor_client.py     # Zugriff auf HA/Supervisor API
│  ├─ db.py                    # SQLite Init + Connection-Handling
│  ├─ models.py                # Datenmodelle (Session, Claim, User)
│  ├─ services/
│  │  ├─ sensor_service.py     # Sensor polling + Sitzungslogik
│  │  └─ leaderboard_service.py# Ranking/Statistiken
│  ├─ routes/
│  │  ├─ admin.py              # Ingress-geschuetzte Admin-Endpunkte
│  │  ├─ guest.py              # Oeffentliche Gaeste-Endpunkte ohne Token
│  │  └─ api.py                # JSON API fuer Frontend
│  ├─ templates/
│  │  ├─ admin.html
│  │  └─ guest.html
│  └─ static/
│     ├─ css/
│     │  └─ styles.css
│     └─ js/
│        ├─ admin.js
│        └─ guest.js
└─ README.md                   # Setup, QR-Link, Betrieb
```

Hinweise:
1. SQLite-Datei liegt zwingend unter `/data`, z. B. `/data/klo_tracker.db`.
2. Trennung von `routes`, `services` und `db` erleichtert spaetere Erweiterungen.
3. Admin- und Gaeste-Ansicht nutzen dasselbe Backend mit getrennter Auth-Logik.

---

## 2. Erste Basis-Entwuerfe

### 2.1 Entwurf `config.yaml`

```yaml
name: "Klo-Tracker"
description: "Gamification fuer das Gaeste-WC: Sitzungen tracken, claimen und als Leaderboard anzeigen."
version: "0.1.0"
slug: "flush_and_rush"
url: "https://example.com/klo-tracker-docs"
init: false
startup: services
boot: auto

arch:
  - aarch64
  - amd64

# Admin-Ansicht via Home Assistant Ingress
ingress: true
ingress_port: 8099
panel_title: "Klo-Tracker"
panel_icon: "mdi:toilet"

# Zugriff auf Home Assistant API ueber Supervisor-Proxy
homeassistant_api: true

# Oeffentliche Gaeste-Ansicht auf Host-Port 8080
ports:
  8080/tcp: 8080

options:
  sensor_entity_id: "binary_sensor.klodeckel"

schema:
  sensor_entity_id: str
```

Warum diese Werte:
1. `ingress: true` fuer die interne, geschuetzte Admin-Seite.
2. `ports` fuer oeffentliche Gaeste-Erreichbarkeit.
3. `homeassistant_api: true` fuer Sensorstatus via `SUPERVISOR_TOKEN`.
4. Gaeste-Endpunkte laufen ohne Token, Zugriff nur im lokalen WLAN.

---

### 2.2 Entwurf `Dockerfile`

```dockerfile
ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:3.20
FROM ${BUILD_FROM}

# Basispakete
RUN apk add --no-cache \
    python3 \
    py3-pip \
    bash \
    jq \
    curl

WORKDIR /app

# Dependencies
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Application
COPY app /app/app
COPY run.sh /run.sh
RUN chmod +x /run.sh

# App intern auf 8099 (Ingress) und extern auf 8080 (Guest)
EXPOSE 8099 8080

CMD ["/run.sh"]
```

Empfohlene spaetere `requirements.txt`:
- Bei FastAPI: `fastapi`, `uvicorn[standard]`, `jinja2`, `httpx`
- Bei Flask: `flask`, `gunicorn`, `jinja2`, `httpx`

---

## 3. Logische Entwicklungsreihenfolge (Python)

### Schritt A: Konfigurations- und Laufzeitbasis
1. `settings.py`: Lade `sensor_entity_id` und DB-Pfad (`/data/klo_tracker.db`).
2. `run.sh`: App-Startprozess sauber und mit nachvollziehbaren Logs.
3. Health-Endpoint `/health` fuer schnellen Betriebscheck.

### Schritt B: Datenbank stabilisieren
1. `db.py` mit SQLite-Initialisierung beim Start.
2. Tabellen anlegen:
   - `sessions` (id, started_at, ended_at, duration_sec, status)
   - `claims` (id, session_id, name, claimed_at)
   - optional `events` (Sensor-Transitions fuer Debug)
3. Regeln absichern:
   - Pro Session nur ein Claim.
   - Nur abgeschlossene Sessions sind claimbar.
4. Basisabfragen fuer Leaderboard und Statistiken vorbereiten.

### Schritt C: Sensor-Auslesung via Supervisor API
1. `supervisor_client.py`: API-Aufrufe mit `SUPERVISOR_TOKEN`.
2. `sensor_service.py`: Polling-Intervall (z. B. 1 Sekunde).
3. Zustandsautomat:
   - `off -> on`: Session starten.
   - `on -> off`: Session beenden und Dauer berechnen.
4. Debounce + Robustheit:
   - sehr kurze Flanken ignorieren.
   - API-Fehler loggen und retryen.

### Schritt D: API- und Routing-Schicht
1. `routes/api.py`:
   - `GET /api/current-session`
   - `POST /api/claim`
   - `GET /api/leaderboard`
2. Gaeste-Endpunkte:
   - Zugriff direkt im lokalen WLAN ohne Token.
3. Admin-Endpunkte (Ingress):
   - `GET /admin/stats`
   - `GET /admin/sessions`
   - `DELETE /admin/session/{id}`

### Schritt E: Frontends
1. Gaeste-Seite:
   - grosser Timer
   - Namenseingabe
   - kompaktes Leaderboard, sortiert nach kurzer Dauer
2. Admin-Seite:
   - Dashboard in Home Assistant Sidebar via Ingress
   - Statistiken und Session-Historie
3. Vanilla JS:
   - einfache Fetch-Aufrufe
   - klare Fehlermeldungen bei API-Fehlern

### Schritt F: Qualitaet, Betrieb, Sicherheit
3. Testfaelle:
   - Session-Lifecycle
   - Claim nur einmal
   - Gastzugriff ohne Token
2. Logging:
   - Sensorwechsel
   - Claim-Events
   - API-Fehler
3. README:
   - Konfiguration
   - Gast-URL: `http://<HA-IP>:8080/guest`

---

## 4. Umsetzung in Meilensteinen
1. Add-on Basis lauffaehig (Manifest, Docker, Run, Healthcheck)
2. SQLite + Datenmodell
3. Sensor-Polling + Session-Erzeugung
4. Gaeste-Ansicht + Claim-Flow
5. Admin-Ansicht + Statistiken + Delete
6. Feinschliff (Validierung, Logging, Tests)

---

## Frage fuer den naechsten Schritt
Moechtest du, dass wir jetzt mit **Schritt 1** starten und die Basisdateien direkt konkret im Add-on umsetzen?