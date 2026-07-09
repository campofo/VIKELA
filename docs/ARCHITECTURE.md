# VIKELA — System Architecture & Team Guide

A shared reference for how the VIKELA panic system works end to end: the hardware
device, the VPS relay, Firebase, and the SMS paths. Diagrams are Mermaid and
render automatically on GitHub.

> **This document describes the relay architecture** (branch
> `claude/vps-relay-firebase`): the device talks plain HTTP to a VPS relay, which
> forwards to Firebase over HTTPS. A separate branch
> (`claude/dev-branch-error-fix-38ew5o`) implements an alternative "native
> backend" that replaces Firebase entirely — see [Appendix B](#appendix-b--alternative-native-backend).

---

## 1. What VIKELA is

VIKELA is a community-safety system built around a **standalone hardware panic
button**. When a person triggers the device, it reports **who it is** and **where
it is**, and the backend alerts that person's **emergency contacts** by SMS.

The system has three parts:

| Part | Tech | Responsibility |
| --- | --- | --- |
| **Hardware device** | LILYGO T-SIM7000G (ESP32 + SIM7000G modem), MicroPython | Detect a panic, get GPS + battery, send the alert, SMS fallback |
| **VPS relay** | FastAPI + Docker on a VPS | Accept plain HTTP from the device, forward to Firebase over HTTPS |
| **Firebase** | Cloud Functions + Firestore | Resolve device → user, store the alert, send SMS via Agoo |
| **Mobile app** | (separate repo) | Manage users, contacts, device pairing, alert history |

### Why the relay exists

The SIM7000G modem **cannot reliably complete a TLS/HTTPS handshake**. Firebase
requires HTTPS. The relay bridges the gap: the device speaks plain **HTTP** to
the relay, and the relay speaks **HTTPS** to Firebase.

```
Hardware --HTTP--> VPS relay --HTTPS--> Firebase Cloud Function
```

---

## 2. System topology

```mermaid
flowchart LR
    subgraph Field["Field"]
      HW["LILYGO T-SIM7000G<br/>panic device<br/>MicroPython firmware"]
    end

    subgraph Cellular["Cellular network"]
      NET["LTE / GPRS<br/>APN data + SMS"]
    end

    subgraph VPS["VPS  (e.g. Hostinger)"]
      RELAY["VIKELA relay<br/>FastAPI, Docker<br/>plain HTTP :8081"]
    end

    subgraph Firebase["Firebase"]
      FN["hardwareAlert<br/>Cloud Function"]
      FS[("Firestore")]
      TRG["onAlertCreated<br/>Cloud Function"]
    end

    AGOO["Agoo SMS gateway"]
    CONTACTS["Emergency contacts<br/>(phones)"]
    APP["Mobile app"]

    HW -- "1. HTTP POST /hardwareAlert" --> NET
    NET --> RELAY
    RELAY -- "2. HTTPS forward" --> FN
    FN -- "3. write alert" --> FS
    FS -- "4. trigger" --> TRG
    TRG -- "5. send SMS" --> AGOO
    AGOO --> CONTACTS

    HW -. "Fallback: SMS straight from the SIM" .-> CONTACTS
    APP -- "manage users / contacts / history" --> FS
```

**Two independent SMS paths:**
1. **Primary** — Firebase (`onAlertCreated`) sends SMS to the resolved contacts via Agoo.
2. **Fallback** — if the device can't reach the relay/Firebase, the firmware sends SMS **directly from its own SIM** to locally cached / built-in numbers.

---

## 3. End-to-end panic flow

```mermaid
sequenceDiagram
    autonumber
    participant U as Person
    participant D as Device (firmware)
    participant R as VPS Relay
    participant F as Firebase Fn
    participant S as Firestore
    participant A as Agoo SMS
    participant C as Contacts

    U->>D: Trigger panic (button / RST x3 / SMS / serial)
    D->>D: Wake modem, register on network
    D->>D: Get GPS fix (or use cached), read battery
    D->>R: HTTP POST /hardwareAlert {device_id, lat, lon, battery}
    R->>F: HTTPS POST (forward body verbatim)
    F->>S: Create alert doc, resolve device -> user
    S-->>F: (on create)
    F->>A: onAlertCreated builds message
    A->>C: SMS to emergency contacts
    F-->>R: HTTP 2xx
    R-->>D: 2xx (Firebase response)
    D-->>U: LED success

    Note over D,R: If the relay/Firebase is unreachable OR returns non-2xx
    D->>C: SMS fallback directly from the SIM
    D-->>U: LED success/error
```

---

## 4. The hardware device (firmware)

**File:** `firmware/micropython_lilygo_t_sim7000g_panic/main.py`
(MicroPython, single file, configured at the top before flashing.)

### 4.1 Panic triggers

The device needs no attached button to work. Any of these raise a panic:

```mermaid
flowchart TD
    A["Idle loop"] --> B{"Trigger?"}
    B -- "RST button pressed<br/>PANIC_RESET_COUNT times" --> P["Panic"]
    B -- "SMS from an authorised number<br/>PANIC_CALLER_NUMBERS" --> P
    B -- "Held button on GPIO 32 / BOOT" --> P
    B -- "Serial 'p' key (dev)" --> P
    B -- "none" --> A
    P --> DELIVER["deliver_alert()"]
```

| Trigger | Config | Notes |
| --- | --- | --- |
| RST multi-press | `PANIC_RESET_COUNT` (3), `RESET_MULTIPRESS_WINDOW_MS` | Counts qualifying resets via `machine.reset_cause()` + a flash counter |
| Remote SMS | `PANIC_CALLER_NUMBERS`, `PANIC_SMS_KEYWORD`, `REMOTE_TRIGGER_POLL_MS` | Polls the SIM inbox; whitelisted sender fires |
| Physical button | `PANIC_BUTTON_PINS` (`[32, 0]`), `BUTTON_HOLD_MS` | Hold to fire; debounced |
| Serial dev key | `DEV_SERIAL_TRIGGER_KEY` (`p`) | For bench testing without hardware |

### 4.2 Alert delivery logic

```mermaid
flowchart TD
    START["deliver_alert()"] --> WAKE{"Modem awake?"}
    WAKE -- no --> FAILW["Log + return"]
    WAKE -- yes --> NET{"Network registered?"}
    NET -- no --> USECACHE["Use cached GPS"]
    NET -- yes --> GPS["Acquire GPS (or cache)"]
    USECACHE --> BATT
    GPS --> BATT["Read battery (AT+CBC)"]
    BATT --> POST["HTTP POST alert to relay"]
    POST --> OK{"HTTP 2xx?"}
    OK -- yes --> DONE["Success (Firebase handles SMS)"]
    OK -- no --> SMS["SMS fallback from SIM<br/>to cached / built-in contacts"]
    SMS --> DONE2["Done (delivered if any SMS sent)"]
```

Key config at the top of `main.py`:

- `BACKEND_ALERT_URL = "http://YOUR_SERVER_IP:8081/hardwareAlert"` — the relay
- `CELLULAR_APN`, `DEVICE_ID`, `EMERGENCY_CONTACTS`, `SMSC_NUMBER`
- GPS/HTTP/network timeouts, trigger settings

### 4.3 How the modem sends HTTP (SIM7000G `AT+SH*` stack)

The firmware drives the modem with AT commands over UART. For a plain-HTTP POST:

```mermaid
sequenceDiagram
    autonumber
    participant FW as Firmware
    participant M as SIM7000G modem
    FW->>M: AT+CNACT=... (activate data / PDP context)
    FW->>M: AT+SHCONF="URL","http://IP:8081"
    FW->>M: AT+SHCONF="BODYLEN"/"HEADERLEN"
    loop up to 3 attempts
        FW->>M: AT+SHCONN
        M-->>FW: OK or "operation not allowed"
        FW->>M: AT+SHSTATE?  (expect +SHSTATE: 1)
    end
    FW->>M: AT+SHCHEAD / AT+SHAHEAD Content-Type
    FW->>M: AT+SHBODEXT=<len>,<t>  (then write body)
    Note right of FW: Fallback: AT+SHBOD="<body>",<len>
    FW->>M: AT+SHREQ="/hardwareAlert",3  (3 = POST)
    M-->>FW: +SHREQ: "POST",<status>,<len>
    FW->>M: AT+SHDISC
```

**Modem quirks handled in firmware:**
- `AT+SHCONN` intermittently returns `operation not allowed` → **retried up to 3×** with a clean `AT+SHDISC` and a pause between attempts.
- The request body uses **`AT+SHBODEXT`** (length + `>` prompt, then raw bytes); some firmware only accepts the inline `AT+SHBOD="<body>",<len>` form, so that's a **fallback**.
- `AT+SHSSL`/`AT+SHDISC` `operation not allowed` before a session exists is harmless.

### 4.4 Data the device sends (contract)

`POST /hardwareAlert`, `Content-Type: application/json`:

```json
{
  "device_id": "VIKELA-T-SIM7000G-001",
  "latitude": 5.6037,
  "longitude": -0.187,
  "battery_level": 78
}
```

- `latitude`/`longitude` are `null` when GPS times out.
- `battery_level` is a percentage from `AT+CBC`, or `-1` if unavailable.
- The device only sends **who it is and where it is** — Firebase resolves the
  user and builds the emergency message.

---

## 5. The VPS relay

**Directory:** `relay/` &nbsp;•&nbsp; **File:** `relay/relay.py` (FastAPI)

Stateless HTTP→HTTPS forwarder. It does not store anything.

```mermaid
flowchart TD
    IN["POST /hardwareAlert"] --> PARSE{"Body type == 'heartbeat'?"}
    PARSE -- yes --> HB["Return {accepted:true, type:heartbeat}<br/>(not forwarded)"]
    PARSE -- no --> FWD["HTTPS POST to FIREBASE_FUNCTION_URL"]
    FWD --> RESP{"Firebase reachable?"}
    RESP -- yes --> PASS["Return Firebase status + body verbatim"]
    RESP -- no --> ERR["Return 502 {accepted:false}"]
```

| Endpoint | Purpose |
| --- | --- |
| `GET /health` | Liveness check → `{"status":"ok"}` |
| `POST /hardwareAlert` | Forward alert to Firebase; heartbeats acked locally |

**Configuration (env):**

| Var | Default | Meaning |
| --- | --- | --- |
| `FIREBASE_FUNCTION_URL` | VIKELA `hardwareAlert` URL | HTTPS forward target |
| `RELAY_BIND` | `0.0.0.0:8081` | Public HTTP bind (port 80 fallback if a carrier blocks 8081) |
| `RELAY_FORWARD_TIMEOUT` | `30` | Seconds to wait for Firebase before returning 502 |

The relay returns **Firebase's real status and body** to the device, so the
device sees a true 2xx/non-2xx and can decide whether to fall back to SMS.

---

## 6. Firebase (backend of record)

Managed **outside this repo**. Responsibilities:

1. **`hardwareAlert` (HTTP Cloud Function)** — validates the payload, resolves
   `device_id` → user (via `devices/{deviceId}`), writes an alert document to
   Firestore.
2. **Firestore** — stores users, devices, emergency contacts, alert history;
   the mobile app reads/writes here.
3. **`onAlertCreated` (Firestore trigger)** — reads the user's emergency
   contacts, builds the message, and sends SMS via **Agoo**.

```mermaid
flowchart LR
    IN["hardwareAlert()"] --> RES["Resolve device -> user"]
    RES --> DOC["Write alert doc"] --> FS[("Firestore")]
    FS --> T["onAlertCreated()"]
    T --> MSG["Build message from<br/>user's emergency contacts"]
    MSG --> AGOO["Agoo SMS"] --> C["Contacts"]
```

---

## 7. Deployment

```mermaid
flowchart TD
    subgraph VPS["VPS host"]
      direction TB
      DC["docker compose"] --> CT["relay container<br/>uvicorn :8081"]
      FW["Firewall: allow TCP 8081"]
    end
    DEV["Device firmware<br/>BACKEND_ALERT_URL = http://VPS_IP:8081/hardwareAlert"]
    DEV -- "public internet, HTTP" --> FW --> CT
    CT -- "HTTPS" --> FB["Firebase hardwareAlert"]
```

**Steps (full runbook in `relay/README.md`):**

```bash
cd VIKELA/relay
cp .env.example .env            # set FIREBASE_FUNCTION_URL if different
docker compose up -d --build
curl http://127.0.0.1:8081/health     # {"status":"ok"}
# Open TCP 8081 in the VPS firewall (hPanel + ufw allow 8081/tcp)
```

Then set `BACKEND_ALERT_URL` in the firmware to
`http://<VPS_IP>:8081/hardwareAlert` and reflash the device.

> If a mobile carrier blocks port 8081, switch the relay to port 80
> (`RELAY_BIND=0.0.0.0:80`) — still plain HTTP, no TLS/Traefik.

---

## 8. Failure handling & resilience

| Failure | Behaviour |
| --- | --- |
| No GPS fix | Sends `latitude/longitude = null`; SMS says location unavailable; uses cached GPS when available |
| Network not registered | Uses cached GPS; attempts alert; falls back to SMS |
| `AT+SHCONN` "operation not allowed" | Retries up to 3× with disconnect + pause |
| Relay/Firebase unreachable or non-2xx | Device sends **SMS fallback** from its own SIM to cached / built-in contacts |
| Relay can't reach Firebase | Relay returns **502**; device falls back to SMS |
| SMS send fails (`CMS ERROR: 500`) | Set `SMSC_NUMBER` (SIM's service-centre number) |

---

## 9. Security notes (read before production)

- The device → relay path is **plain HTTP** and **unauthenticated**. Alert
  payloads (device ID + GPS) travel in the clear; anyone who knows the
  `IP:8081` can post to it. This is a deliberate trade-off for modem
  reliability. Mitigations to consider: a shared-secret header (device + relay),
  IP allow-listing, or moving the relay behind an authenticated gateway.
- Keep real phone numbers, APN credentials, and server IPs **out of git** — the
  firmware config constants use placeholders (`YOUR_SERVER_IP`); fill them in
  locally before flashing.

---

## 10. Repository map

```text
firmware/
  micropython_lilygo_t_sim7000g_panic/   # PRIMARY firmware (MicroPython)
    main.py                              #   single-file firmware
    README.md
  lilygo_t_sim7000g_panic/               # Arduino/TinyGSM alternative
relay/
  relay.py                               # FastAPI HTTP -> HTTPS forwarder
  Dockerfile, docker-compose.yml
  README.md                              # deploy runbook
  tests/                                 # respx-based tests
docs/
  ARCHITECTURE.md                        # this document
scripts/
  upload_micropython.sh                  # flash helper
```

---

## Appendix A — Glossary

| Term | Meaning |
| --- | --- |
| SIM7000G | The LTE/GPRS/GPS cellular modem on the board |
| `AT+SH*` | The SIM7000 modem's built-in HTTP client command set |
| CNACT | Modem command to activate the packet-data (PDP) context |
| Relay | The VPS service that forwards HTTP → HTTPS |
| Agoo | The SMS gateway Firebase uses to send messages (Ghana) |
| Heartbeat | An optional liveness ping (`{"type":"heartbeat"}`) acked by the relay |

## Appendix B — Alternative: native backend

Branch `claude/dev-branch-error-fix-38ew5o` replaces Firebase with a
**self-hosted FastAPI + SQLite backend** (`backend/`). In that design there is
**no relay and no Firebase**: the device posts directly to the backend, the
backend returns the emergency contacts, the **SIM sends the SMS**, and the device
**streams live GPS every 5 seconds** during an active panic (stoppable via a
resolve endpoint). Use that branch if you want to own the whole stack instead of
depending on Firebase. The two branches are mutually exclusive — pick one per
deployment.
