# Flush & Rush

Flush & Rush turns your toilet into a race against yourself.

It is a Home Assistant add-on that measures how long you sit on the toilet, using nothing more than a cheap door/window contact sensor attached to the toilet lid. A screen on the wall (for example an old phone or tablet) shows a live timer that races against your own times from today, much like the ghost racer in Mario Kart. Home Assistant also gets a statistics dashboard for everyone who likes data.

Is this over-engineered? Absolutely. Does it work? Surprisingly well.

## Why

The average person who takes their phone to the toilet spends about three days a year sitting there. Each individual visit feels short, so you never notice it. A number you can look up afterwards rarely changes anything, though. What makes the difference is:

1. **An incentive.** Nobody optimizes a statistic for fun, but everybody wants to beat their own best time.
2. **Feedback at the right moment.** The timer is right in front of you while you are sitting there, not hidden in an app.

## How it works

### The sensor

A standard smart home contact sensor (two parts, one magnet) is attached to the toilet lid and the cistern or seat.

- **Lid up:** the sensor opens, a session starts.
- **Lid down:** the sensor closes, the session ends.

No camera, no app, no button to press. The add-on reads the sensor state from Home Assistant once per second. State changes that happen within 1.5 seconds of the previous change are ignored, so a bouncing lid does not create bogus sessions.

### The race

For every day, Flush & Rush calculates three reference values from all sessions of that day:

| Value | Meaning |
| --- | --- |
| Fastest | Your shortest session today |
| Median | The median of all sessions today. The median is used instead of the average because it is far less affected by outliers. |
| Longest | Your longest session today |

As soon as the lid goes up, the race starts and the wall display shows a live timer and a progress bar with markers for these three values. The timer changes color while you sit:

| Color | Condition |
| --- | --- |
| Green | You are still faster than your fastest session today. The first session of a day always stays green. |
| Yellow | You are somewhere between your fastest and your longest session today. Time to wrap up. |
| Red | You have now been sitting longer than in any other session today. You lost. |

When the lid closes, the display shows the final time together with a short verdict (new daily record, slower or faster than the median by N seconds, or new longest session). Unless it was a new longest session, you also get confetti. After that, the display shows today's fastest, median and longest times.

At midnight everything resets. New day, new race, new chance for a personal best. Sessions are assigned to the day on which they started, using the time zone configured in Home Assistant.

### The dashboard

Inside Home Assistant, the add-on adds a "Flush & Rush" entry to the sidebar. It opens a statistics dashboard with:

- Key figures such as total sessions, total time spent, fastest, median and longest session
- Sessions by hour of the day and by weekday
- Duration distribution
- Sessions per day and duration trend over 7 days, 30 days, 90 days or all time
- A daily overview with every single session

Individual sessions can be deleted from the daily overview. This is useful when the lid stayed open for half an hour while cleaning the bathroom. The daily values are recalculated immediately.

### Architecture

```
Contact sensor --> Home Assistant --> Flush & Rush add-on --> Wall display (browser)
                   (binary_sensor)    - polls the sensor via     - live timer over WebSocket
                                        the Supervisor API
                                      - stores sessions in       Home Assistant sidebar
                                        SQLite (/data)           - statistics dashboard
                                      - serves both web pages      (via Ingress)
```

The add-on is a small Python application (FastAPI and Uvicorn) running in its own container. All data stays local in a SQLite database inside the add-on's data directory, so it is included in Home Assistant backups.

## Requirements

- Home Assistant OS or Home Assistant Supervised (add-ons are required, so Home Assistant Container or Core will not work)
- A 64-bit system (`aarch64` or `amd64`, for example a Raspberry Pi 4/5, Home Assistant Green/Yellow or an x86 machine)
- A contact sensor that is integrated in Home Assistant as a `binary_sensor` (Zigbee, Z-Wave, Matter, Wi-Fi, it does not matter)
- Optional: any device with a screen and a browser for the live display, such as an old Android phone or tablet

## Installation

### 1. Set up the sensor

1. Attach the contact sensor so that the two parts are close together when the lid is **down** and separate when the lid is **up**. The magnet part usually goes on the lid, the sensor part on the cistern or the seat hinge area.
2. Pair the sensor with Home Assistant as you would with any other contact sensor.
3. Note its entity ID, for example `binary_sensor.toilet_lid`. You can find it under **Settings > Devices & services > Entities**.
4. Check the state: with the lid up, the sensor should report `on` (open). If it reports `off` instead, enable the `sensor_inverted` option later on.

### 2. Add the repository and install the add-on

In recent Home Assistant versions add-ons are called "Apps". The menu names below use the new wording, with the old wording in parentheses.

1. In Home Assistant, go to **Settings > Apps (Add-ons) > App Store (Add-on Store)**.
2. Open the three-dot menu in the top right corner and select **Repositories**.
3. Add this URL and confirm:
   ```
   https://github.com/l2xu/flush_and_rush
   ```
4. Close the dialog and reload the store. "Flush & Rush" now appears in the list.
5. Open it and click **Install**. The container is built locally on your system, so the first installation can take a few minutes.

Alternatively, you can use this link to open the repository dialog directly in your Home Assistant instance:
[Add repository to my Home Assistant](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fl2xu%2Fflush_and_rush)

### 3. Configure the add-on

Open the **Configuration** tab of the add-on and set at least your sensor entity:

```yaml
sensor_entity_id: binary_sensor.toilet_lid
sensor_inverted: false
fade_duration_ms: 600
sidebar_view: auto
```

| Option | Default | Description |
| --- | --- | --- |
| `sensor_entity_id` | `binary_sensor.klodeckel` | Entity ID of the contact sensor on the toilet lid. |
| `sensor_inverted` | `false` | Set to `true` if your sensor reports `off` when the lid is up. |
| `fade_duration_ms` | `600` | Duration of the fade transition on the result screen, in milliseconds (100 to 5000). |
| `sidebar_view` | `auto` | Which page the sidebar entry opens. `auto` shows the dashboard inside Home Assistant and the live display on the direct port. `admin` or `guest` force one of the two pages everywhere. |

In the **Network** section of the same tab you can change the port of the live display. The default is `8080`.

### 4. Start the add-on

1. Go to the **Info** tab, enable **Show in sidebar** and click **Start**.
2. Check the **Log** tab. It should show the configured sensor and no errors.
3. Lift the toilet lid and close it again. A first session should appear in the dashboard.

## Setting up the wall display

The live display is a plain web page served by the add-on on your local network. There is no app, no store and no account. Every device with a screen and a browser works.

1. Open the following address on the device, replacing the IP with the address of your Home Assistant host (and the port if you changed it):
   ```
   http://<home-assistant-ip>:8080/
   ```
   The page is also always available at `http://<home-assistant-ip>:8080/guest`.
2. To keep the page open permanently, use a kiosk browser app, for example Fully Kiosk Browser on Android. Configure it to:
   - load the address above as its start page
   - keep the screen on and disable standby
   - hide the status bar and navigation, and block notifications and other apps
3. Keep the device plugged in. A wall mount with an opening for the charging cable looks much better than a car phone holder on a bathroom wall.

The display reconnects automatically if Home Assistant or the add-on restarts.

If you do not want a screen in your bathroom, you can skip this step entirely and only use the statistics dashboard in the sidebar.

### Showing the display on a Home Assistant dashboard

You can also embed the live display on a regular Home Assistant dashboard using a **Webpage** card with the URL `http://<home-assistant-ip>:8080/guest`. Note that browsers block this if you access Home Assistant via `https` while the add-on page uses `http`.

## Multiple people

The sensor only knows that somebody is sitting there, not who. All sessions therefore end up in one shared pool. In a shared flat, a family or a couple, you are not racing against yourself but against the whole household.

Entering your name before every visit would add exactly the kind of friction that makes people stop using something after three days, so this is intentionally not implemented. If you have an elegant idea for telling people apart automatically, please open an issue.

## Security note

The port of the live display (default `8080`) is not protected by Home Assistant's login. Besides the display, it also serves the dashboard and its API, including the endpoint for deleting sessions. Only expose it on your local network and never forward it to the internet. If you do not need the wall display, you can disable the port in the add-on's **Network** settings. The sidebar entry keeps working because it goes through Home Assistant Ingress.

## Troubleshooting

| Problem | Solution |
| --- | --- |
| No sessions are recorded | Check the entity ID in the configuration and look at the add-on log for errors such as `HTTP Fehler von Supervisor API: 404`. |
| Sessions start when the lid closes | Toggle `sensor_inverted`. |
| A session is way too long | The lid was left open. Delete the session in the daily overview of the dashboard. |
| The wall display stays at `00:00` | Make sure the device can reach `http://<home-assistant-ip>:8080/` and that the port is enabled in the Network settings. |

The endpoint `http://<home-assistant-ip>:8080/health` returns the current sensor state, the open session and the last error as JSON, which is handy for debugging.

## Limitations

- The user interface is currently in German.
- Only one sensor (and therefore one toilet) per installation is supported.
- The sensor is polled once per second instead of subscribing to state changes, so start and end times are accurate to about one second.

## API

The add-on exposes a small JSON API that the pages use. You can use it for your own automations as well.

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/health` | Status of the add-on and the sensor service |
| `GET` | `/api/admin/stats?days=30` | Aggregated statistics (totals, today, daily, by hour, by weekday, histogram) |
| `GET` | `/api/admin/days` | Fastest, median and longest session per day |
| `GET` | `/api/admin/days/{YYYY-MM-DD}/sessions` | All sessions of one day |
| `DELETE` | `/api/admin/sessions/{id}` | Delete a single session |
| `GET` | `/api/guest/config` | Configuration of the live display |
| `WS` | `/ws/guest` | Live state (phase, elapsed time, today's stats, last result) once per second |

## Project structure

```
.
├── config.yaml                  Add-on manifest (options, ports, Ingress)
├── repository.yaml              Makes this repo installable as an add-on repository
├── Dockerfile                   Container build
├── run.sh                       Start script (reads options, starts Uvicorn)
├── requirements.txt             Python dependencies
└── app/
    ├── main.py                  FastAPI app, routes, WebSocket
    ├── settings.py              Reads the add-on options
    ├── supervisor_client.py     Reads the sensor state via the Supervisor API
    ├── db.py                    SQLite storage and statistics
    ├── ws_manager.py            Broadcasts live updates to all displays
    ├── pages.py                 Serves the HTML pages
    ├── services/
    │   └── sensor_service.py    Sensor polling and session logic
    └── static/
        ├── guest.html           Live display for the wall
        └── admin.html           Statistics dashboard
```

## License

Flush & Rush is released under the [MIT License](LICENSE).
