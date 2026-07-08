import json
import select
import sys
import time

import machine
from machine import Pin, UART

# ---------------------------------------------------------------------------
# VIKELA deployment configuration
#
# Edit these values before uploading this single file to the ESP32.
# Keep private phone numbers, APN credentials, and backend URLs out of git.
# ---------------------------------------------------------------------------

# Cellular APN settings from your SIM/network provider.
CELLULAR_APN = "internet"
CELLULAR_USER = ""
CELLULAR_PASS = ""

# HTTP alert endpoint: the VPS relay, which forwards to Firebase over HTTPS
# (the modem cannot do TLS reliably, so the device posts plain HTTP here).
# Replace YOUR_SERVER_IP with your VPS public IP. Local 192.168.x.x addresses
# are usually not reachable from the SIM7000G cellular network.
BACKEND_ALERT_URL = "http://YOUR_SERVER_IP:8081/hardwareAlert"

# Device/user identity sent in HTTP payloads and SMS fallback messages.
DEVICE_ID = "VIKELA-T-SIM7000G-001"
USER_ID = "user-001"
USER_DISPLAY_NAME = "VIKELA User"

# SMS fallback settings.
# Used only when Firebase is unreachable. Firestore (via the mobile app) is the
# source of truth for emergency contacts; these locals are the offline backup.
SMS_MESSAGE_PREFIX = "VIKELA EMERGENCY ALERT"
EMERGENCY_CONTACTS = [
    "+233504647863"
]
# SMS service centre (SMSC) number for the SIM's network. Leave blank to use
# whatever the SIM provides; set it if SMS sends fail with "CMS ERROR: 500".
SMSC_NUMBER = ""
SEND_BOOT_SMS_ON_START = False
BOOT_SMS_MESSAGE = "VIKELA device powered on"

# LILYGO T-SIM7000G board pins.
MODEM_RX = 26
MODEM_TX = 27
MODEM_PWRKEY = 4
MODEM_POWER_ON = 23
MODEM_RST = 5

# VIKELA panic-device pins.
# Any button held on one of these GPIO pins triggers a panic alert.
# 32 is an external button; 0 is the onboard BOOT button.
# Note: RST/EN is a hardware reset button and cannot be used here.
PANIC_BUTTON_PINS = [32, 0]
STATUS_LED_PIN = 12
STATUS_LED_ACTIVE_LOW = True

# Behavior tuning.
BUTTON_HOLD_MS = 1200
NETWORK_TIMEOUT_MS = 60000
GPS_TIMEOUT_MS = 90000
BOOT_GPS_TIMEOUT_MS = 30000
HTTP_TIMEOUT_MS = 30000
DEV_SERIAL_TRIGGER_ENABLED = True
DEV_SERIAL_TRIGGER_KEY = "p"
SEND_PANIC_ON_BOOT = False
GPS_CACHE_FILE = "last_gps.json"
CONTACTS_CACHE_FILE = "panic_contacts.json"
GPS_REFRESH_INTERVAL_MS = 60000
GPS_REFRESH_TIMEOUT_MS = 15000

# RST multi-press trigger (no external button needed).
# Press the onboard RST button PANIC_RESET_COUNT times in a row to fire a panic.
RESET_TRIGGER_ENABLED = True
PANIC_RESET_COUNT = 3
RESET_MULTIPRESS_WINDOW_MS = 10000    # max gap between presses before the count clears
RESET_TRIGGER_FILE = "reset_trigger.json"
COUNT_RESET_CAUSE = "pwron"           # this board reports the RST button as a power-on reset ("hard" if yours reports HARD_RESET)

# Remote trigger: raise a panic by texting the device from an authorised number.
REMOTE_TRIGGER_ENABLED = True
PANIC_CALLER_NUMBERS = ["+233504647863", "+233555192380"]
PANIC_SMS_KEYWORD = ""                # empty = any SMS from a whitelisted number fires; else require this substring
REMOTE_TRIGGER_POLL_MS = 5000         # how often to poll the modem for new SMS


class Led:
    IDLE = "idle"
    WAITING = "waiting"
    SENDING = "sending"
    SUCCESS = "success"
    ERROR = "error"

    def __init__(self, pin_no, active_low=False):
        self.pin = Pin(pin_no, Pin.OUT)
        self.active_low = active_low
        self.pattern = self.IDLE
        self.state = 0
        self.last_tick = time.ticks_ms()
        self.off()

    def set_pattern(self, pattern):
        self.pattern = pattern
        self.last_tick = time.ticks_ms()
        if pattern == self.IDLE:
            self.off()
        elif pattern == self.SUCCESS:
            self.on()

    def on(self):
        self.state = 1
        self.pin.value(0 if self.active_low else 1)

    def off(self):
        self.state = 0
        self.pin.value(1 if self.active_low else 0)

    def update(self):
        if self.pattern == self.WAITING:
            interval = 900
        elif self.pattern == self.SENDING:
            interval = 180
        elif self.pattern == self.ERROR:
            interval = 120
        else:
            return

        now = time.ticks_ms()
        if time.ticks_diff(now, self.last_tick) >= interval:
            self.last_tick = now
            self.state = 0 if self.state else 1
            if self.state:
                self.on()
            else:
                self.off()

    def blink_for(self, pattern, duration_ms):
        self.set_pattern(pattern)
        start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), start) < duration_ms:
            self.update()
            time.sleep_ms(10)


class Sim7000:
    def __init__(self):
        self.uart = UART(
            1,
            baudrate=115200,
            tx=Pin(MODEM_TX),
            rx=Pin(MODEM_RX),
            timeout=1000,
        )
        self.power_on = Pin(MODEM_POWER_ON, Pin.OUT)
        self.pwrkey = Pin(MODEM_PWRKEY, Pin.OUT)
        self.reset = Pin(MODEM_RST, Pin.OUT)
        self._remote_inbox_cleared = False

    def clear(self):
        while self.uart.any():
            self.uart.read()

    def read_until(self, markers, timeout_ms=1000):
        if isinstance(markers, str):
            markers = [markers]
        started = time.ticks_ms()
        data = b""
        while time.ticks_diff(time.ticks_ms(), started) < timeout_ms:
            if self.uart.any():
                chunk = self.uart.read()
                if chunk:
                    data += chunk
                    text = data.decode("utf-8", "ignore")
                    for marker in markers:
                        if marker in text:
                            return text
            time.sleep_ms(20)
        return data.decode("utf-8", "ignore")

    def at(self, command, timeout_ms=1000, expected="OK"):
        self.clear()
        print("AT>", command)
        self.uart.write((command + "\r\n").encode())
        response = self.read_until([expected, "ERROR"], timeout_ms)
        print("AT<", response.strip())
        return expected in response, response

    def power_cycle(self):
        self.power_on.on()
        self.reset.on()
        time.sleep_ms(100)
        self.pwrkey.on()
        time.sleep_ms(100)
        self.pwrkey.off()
        time.sleep_ms(1000)
        self.pwrkey.on()
        time.sleep_ms(3000)

    def ensure_awake(self):
        ok, _ = self.at("AT", 1000)
        if ok:
            print("Modem already awake.")
            self.configure_basic_modem()
            return True

        print("Powering SIM7000G modem...")
        self.power_cycle()
        started = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), started) < 10000:
            ok, _ = self.at("AT", 1000)
            if ok:
                self.configure_basic_modem()
                return True
            time.sleep_ms(500)
        return False

    def configure_basic_modem(self):
        self.at("ATE0", 1000)
        self.at("AT+CMEE=2", 1000)
        self.at("AT+CPIN?", 3000)
        self.at("AT+CFUN=1", 5000)
        self.at("AT+COPS=0", 10000)
        if REMOTE_TRIGGER_ENABLED:
            self.enable_remote_trigger()

    def enable_remote_trigger(self):
        # Prepare the modem to raise a panic from an incoming SMS (reliable on the
        # SIM7000G) or an incoming call (only if the module exposes voice).
        self.at("AT+CMGF=1", 3000)          # SMS text mode
        self.at("AT+CNMI=2,1,0,0,0", 3000)  # new-SMS indication (+CMTI)
        self.at("AT+CLIP=1", 3000)          # caller ID for RING (harmless without voice)
        if not self._remote_inbox_cleared:
            # Clear any messages already sitting on the SIM so stale texts can't
            # trigger a panic, but only once per power cycle.
            self.at("AT+CMGD=1,4", 5000)
            self._remote_inbox_cleared = True

    def print_registration_diagnostics(self):
        self.at("AT+CPIN?", 1500)
        self.at("AT+CSQ", 1500)
        self.at("AT+COPS?", 1500)

    def wait_for_network(self, led, timeout_ms):
        started = time.ticks_ms()
        last_diagnostic = time.ticks_ms() - 15000
        while time.ticks_diff(time.ticks_ms(), started) < timeout_ms:
            led.update()
            registered = False
            for command in ("AT+CREG?", "AT+CGREG?", "AT+CEREG?"):
                ok, response = self.at(command, 1500)
                if ok and (",1" in response or ",5" in response):
                    registered = True
                    break
            if registered:
                self.print_registration_diagnostics()
                return True
            if time.ticks_diff(time.ticks_ms(), last_diagnostic) >= 15000:
                last_diagnostic = time.ticks_ms()
                self.print_registration_diagnostics()
            time.sleep_ms(1000)
        return False

    def _network_active(self):
        ok, response = self.at("AT+CNACT?", 3000)
        if not ok:
            return False
        for line in response.splitlines():
            line = line.strip()
            if not line.startswith("+CNACT:"):
                continue
            ip = line.split(",")[-1].strip().strip('"')
            if ip and ip != "0.0.0.0":
                return True
        return False

    def activate_network(self):
        # App-layer packet data activation for the SH HTTP(S) stack
        # (SIM7000/7070 series). Replaces the legacy SAPBR bearer, which
        # cannot do TLS on this modem.
        if self._network_active():
            return True
        # The exact argument form varies by modem firmware revision; try the
        # newer 3-argument form first, then the legacy 2-argument form.
        for command in (
            'AT+CNACT=0,1,"{}"'.format(CELLULAR_APN),
            'AT+CNACT=1,"{}"'.format(CELLULAR_APN),
        ):
            self.at(command, 8000)
            started = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), started) < 8000:
                if self._network_active():
                    return True
                time.sleep_ms(1000)
        return False

    def acquire_gps(self, led, timeout_ms):
        self.at("AT+SGPIO=0,4,1,1", 3000)
        self.at("AT+CGNSPWR=1", 3000)
        started = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), started) < timeout_ms:
            led.update()
            ok, response = self.at("AT+CGNSINF", 2000)
            if ok:
                fix = parse_cgnsinf(response)
                if fix:
                    return fix
            time.sleep_ms(2000)
        return None

    def poll_gps_once(self):
        self.at("AT+SGPIO=0,4,1,1", 3000)
        self.at("AT+CGNSPWR=1", 3000)
        ok, response = self.at("AT+CGNSINF", 2000)
        if ok:
            return parse_cgnsinf(response)
        return None

    def http_post_json(self, url, payload, timeout_ms):
        parsed = parse_http_url(url)
        if not parsed:
            print("Only http:// and https:// URLs are supported.")
            return False

        if not self.activate_network():
            print("Data network activation (CNACT) failed.")
            return False

        body = json.dumps(payload)
        base_url = "{}://{}".format("https" if parsed["ssl"] else "http", parsed["host"])
        if parsed["port"]:
            base_url += ":" + parsed["port"]
        path = parsed["path"]

        # Clear any previous SH session before configuring a new one.
        self.at("AT+SHDISC", 2000)

        if parsed["ssl"]:
            # TLS 1.2 on SSL context 1, bound to the SH HTTP stack. authmode 0
            # skips server-certificate verification (no CA cert is loaded on the
            # modem), which is what lets the handshake to Google/Firebase complete.
            self.at('AT+CSSLCFG="sslversion",1,3', 3000)
            self.at('AT+CSSLCFG="authmode",1,0', 3000)
            # Google Cloud Functions requires Server Name Indication (SNI) during
            # the TLS handshake. Without it SHCONN fails against the endpoint.
            # Some older SIM7000G firmware lacks this command; warn but continue
            # so those modems still attempt the handshake.
            ok_sni, _ = self.at('AT+CSSLCFG="sni",1,"{}"'.format(parsed["host"]), 3000)
            if not ok_sni:
                print("WARNING: modem does not support SNI - SHCONN will likely "
                      "fail against Google endpoints.")
            ok, _ = self.at('AT+SHSSL=1,""', 3000)
            if not ok:
                print("TLS setup (SHSSL) failed on modem.")
                return False
        else:
            self.at('AT+SHSSL=0,""', 3000)

        self.at('AT+SHCONF="URL","{}"'.format(base_url), 3000)
        self.at('AT+SHCONF="BODYLEN",1024', 3000)
        self.at('AT+SHCONF="HEADERLEN",350', 3000)

        # SHCONN can intermittently return "operation not allowed" on the
        # SIM7000G (stale SH session or transient bearer state). Retry with a
        # clean disconnect and a short pause between attempts.
        connected = False
        for attempt in range(3):
            ok, conn_response = self.at("AT+SHCONN", timeout_ms)
            if ok:
                ok_state, state = self.at("AT+SHSTATE?", 3000)
                if ok_state and "+SHSTATE: 1" in state:
                    connected = True
                    break
                print("SHCONN ok but SH state not established.")
            else:
                print("SHCONN attempt {} failed: {}".format(
                    attempt + 1, conn_response.strip()))
            self.at("AT+SHDISC", 2000)
            time.sleep_ms(2000)
        if not connected:
            print("SHCONN failed (could not connect to server).")
            self.at("AT+SHDISC", 2000)
            return False

        # Fresh header set with a JSON content type.
        self.at("AT+SHCHEAD", 2000)
        self.at('AT+SHAHEAD="Content-Type","application/json"', 3000)

        # Set the request body. AT+SHBODEXT takes <len>,<timeout> and returns a
        # ">" prompt to write the raw bytes (preferred; handles JSON cleanly).
        # Some SIM7000G firmware only supports the inline AT+SHBOD="<body>",<len>
        # form (which is why AT+SHBOD=<len>,<timeout> returns "operation not
        # allowed"), so fall back to that.
        ok, _ = self.at("AT+SHBODEXT={},10000".format(len(body)), 5000, ">")
        if ok:
            self.uart.write(body.encode())
            self.read_until("OK", 5000)
        else:
            inline = body.replace("\\", "\\\\").replace('"', '\\"')
            ok, _ = self.at('AT+SHBOD="{}",{}'.format(inline, len(body)), 5000)
            if not ok:
                print("Failed to set request body (SHBODEXT and SHBOD both refused).")
                self.at("AT+SHDISC", 2000)
                return False

        self.clear()
        self.uart.write('AT+SHREQ="{}",3\r\n'.format(path).encode())
        response = self.read_until("+SHREQ:", timeout_ms)
        response += self.read_until("OK", 5000)
        print("AT<", response.strip())
        status = shreq_status(response)
        self.at("AT+SHDISC", 2000)
        if status is not None and 200 <= status < 300:
            return True
        print("Server returned HTTP status:", status)
        return False

    def read_battery(self):
        ok, response = self.at("AT+CBC", 3000)
        if not ok:
            return -1
        for line in response.splitlines():
            line = line.strip()
            if not line.startswith("+CBC:"):
                continue
            # +CBC: <bcs>,<bcl>,<voltage_mV> -- bcl is the charge percentage.
            try:
                return int(line.split(":", 1)[1].split(",")[1].strip())
            except (IndexError, ValueError):
                return -1
        return -1

    def ensure_smsc(self):
        # A missing SMSC (service centre) is the usual cause of "CMS ERROR: 500"
        # on send. If one is configured locally, make sure the modem has it.
        if not SMSC_NUMBER:
            return
        ok, response = self.at("AT+CSCA?", 3000)
        if ok and SMSC_NUMBER in response:
            return
        self.at('AT+CSCA="{}"'.format(SMSC_NUMBER), 3000)

    def send_sms(self, number, message):
        self.at("AT+CMGF=1", 3000)
        self.at('AT+CSCS="GSM"', 3000)
        self.at("AT+CSMP=17,167,0,0", 3000)
        self.ensure_smsc()
        print("Sending SMS to {}".format(number))
        self.clear()
        self.uart.write(('AT+CMGS="{}"\r\n'.format(number)).encode())
        prompt = self.read_until(">", 5000)
        print("AT<", prompt.strip())
        if ">" not in prompt:
            print("SMS prompt not received.")
            return False
        body = message.replace("\n", "\r\n")
        print("Writing SMS body, {} characters.".format(len(body)))
        self.uart.write(body.encode())
        self.uart.write(bytes([26]))
        response = self.read_until(["+CMGS:", "ERROR", "+CMS ERROR:"], 120000)
        response += self.read_until("OK", 10000)
        print("AT<", response.strip())
        sent = "+CMGS:" in response and "OK" in response
        print("SMS send {}".format("succeeded" if sent else "failed"))
        return sent

    def check_sms_trigger(self):
        # Poll unread messages; fire if any is from a whitelisted number (and
        # contains PANIC_SMS_KEYWORD, when set). Polling is more robust than
        # relying on +CMTI URCs, which an in-flight AT command can swallow.
        ok, response = self.at('AT+CMGL="REC UNREAD"', 8000)
        if not ok or "+CMGL:" not in response:
            return False
        triggered = False
        for sender, body in parse_cmgl(response):
            if not caller_is_whitelisted(sender):
                continue
            if PANIC_SMS_KEYWORD and PANIC_SMS_KEYWORD.lower() not in body.lower():
                continue
            print("Panic SMS trigger from:", sender)
            triggered = True
        # Clear the inbox either way so a handled or ignored message can't retrigger.
        self.at("AT+CMGD=1,4", 5000)
        return triggered

    def check_incoming_call(self):
        # Bonus path: detect an incoming call (only works if the module has voice).
        if not self.uart.any():
            return False
        text = self.uart.read()
        if not text:
            return False
        text = text.decode("utf-8", "ignore")
        if "RING" not in text and "+CLIP:" not in text:
            return False
        number = parse_clip_number(text)
        self.at("ATH", 3000)  # hang up; we never answer
        if caller_is_whitelisted(number):
            print("Panic call trigger from:", number)
            return True
        if number:
            print("Ignoring call from non-whitelisted number:", number)
        return False


def parse_http_url(url):
    if url.startswith("http://"):
        ssl = False
        rest = url[7:]
    elif url.startswith("https://"):
        ssl = True
        rest = url[8:]
    else:
        return None
    slash = rest.find("/")
    host_port = rest if slash < 0 else rest[:slash]
    path = "/" if slash < 0 else rest[slash:]
    if ":" in host_port:
        host, port = host_port.split(":", 1)
    else:
        host, port = host_port, ""
    return {"host": host, "port": port, "path": path, "ssl": ssl}


def shreq_status(response):
    # Parse the HTTP status from an async +SHREQ: "POST",<status>,<len> line.
    for line in response.splitlines():
        if "+SHREQ:" not in line:
            continue
        try:
            return int(line.split(":", 1)[1].split(",")[1].strip())
        except (IndexError, ValueError):
            return None
    return None


def caller_is_whitelisted(number):
    # Compare on trailing digits so international (+233...), national (0...), and
    # bare forms of the same number all match.
    if not number:
        return False
    digits = "".join(ch for ch in number if ch.isdigit())
    if not digits:
        return False
    for allowed in PANIC_CALLER_NUMBERS:
        adigits = "".join(ch for ch in allowed if ch.isdigit())
        if not adigits:
            continue
        tail = min(len(digits), len(adigits), 9)
        if digits[-tail:] == adigits[-tail:]:
            return True
    return False


def parse_clip_number(text):
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("+CLIP:"):
            continue
        start = line.find('"')
        end = line.find('"', start + 1)
        if start >= 0 and end > start:
            return line[start + 1:end]
    return None


def parse_cmgl(response):
    # Parse AT+CMGL text-mode output into (sender, body) tuples. Each message is a
    # +CMGL: <idx>,"<stat>","<sender>",... header line followed by the body line.
    messages = []
    lines = response.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if not line.startswith("+CMGL:"):
            continue
        fields = line.split(",")
        sender = None
        if len(fields) >= 3:
            sender = fields[2].strip().strip('"')
        body = lines[i + 1].strip() if i + 1 < len(lines) else ""
        messages.append((sender, body))
    return messages


def due(last_ms, interval_ms):
    return time.ticks_diff(time.ticks_ms(), last_ms) >= interval_ms


def valid_phone_number(number):
    return (
        isinstance(number, str)
        and number.startswith("+")
        and len(number) >= 8
        and len(number) <= 20
        and number[1:].isdigit()
    )


def clean_contact_numbers(numbers):
    cleaned = []
    seen = {}
    if not isinstance(numbers, list):
        return cleaned
    for number in numbers:
        if not valid_phone_number(number):
            continue
        if number in seen:
            continue
        seen[number] = True
        cleaned.append(number)
    return cleaned


def load_contact_cache():
    try:
        with open(CONTACTS_CACHE_FILE, "r") as handle:
            data = json.loads(handle.read())
        numbers = clean_contact_numbers(data.get("phone_numbers"))
        if numbers:
            return numbers
    except Exception:
        pass
    return []


def get_panic_contacts():
    # Emergency contacts now live in Firestore (managed by the mobile app).
    # The firmware only needs local numbers for the offline SMS fallback used
    # when Firebase is unreachable: a locally-provisioned cache, else the
    # built-in EMERGENCY_CONTACTS.
    cached = load_contact_cache()
    if cached:
        print("Using saved panic contact cache for SMS fallback.")
        return cached
    print("Using built-in local emergency contacts for SMS fallback.")
    return EMERGENCY_CONTACTS


def parse_cgnsinf(response):
    for line in response.splitlines():
        line = line.strip()
        if not line.startswith("+CGNSINF:"):
            continue
        values = line.split(":", 1)[1].split(",")
        if len(values) < 5:
            return None
        fix_status = values[1].strip()
        lat = values[3].strip()
        lon = values[4].strip()
        if fix_status != "1" or not lat or not lon:
            return None
        try:
            return {
                "latitude": float(lat),
                "longitude": float(lon),
                "source": "sim7000g_gps",
                "saved_ms": time.ticks_ms(),
            }
        except ValueError:
            return None
    return None


def save_last_gps(fix):
    if not fix:
        return
    try:
        with open(GPS_CACHE_FILE, "w") as handle:
            handle.write(json.dumps({
                "latitude": fix["latitude"],
                "longitude": fix["longitude"],
                "source": "last_saved_gps",
                "saved_ms": time.ticks_ms(),
            }))
        print("Saved GPS cache.")
    except Exception as exc:
        print("Could not save GPS cache:", exc)


def load_last_gps():
    try:
        with open(GPS_CACHE_FILE, "r") as handle:
            fix = json.loads(handle.read())
        if "latitude" not in fix or "longitude" not in fix:
            return None
        fix["source"] = "last_saved_gps"
        return fix
    except Exception:
        return None


def fix_age_seconds(fix):
    if not fix or "saved_ms" not in fix:
        return None
    age_ms = time.ticks_diff(time.ticks_ms(), fix["saved_ms"])
    if age_ms < 0:
        return None
    return age_ms // 1000


def load_reset_count():
    try:
        with open(RESET_TRIGGER_FILE, "r") as handle:
            return int(json.loads(handle.read()).get("count", 0))
    except Exception:
        return 0


def save_reset_count(count):
    try:
        with open(RESET_TRIGGER_FILE, "w") as handle:
            handle.write(json.dumps({"count": count}))
    except Exception as exc:
        print("Could not save reset counter:", exc)


def clear_reset_count():
    save_reset_count(0)


def evaluate_reset_trigger():
    # Detect an "RST pressed N times in a row" panic gesture. The RST line is not
    # a readable GPIO, but the chip reports why it booted, so we count qualifying
    # resets in flash. Returns (should_panic, current_count).
    if not RESET_TRIGGER_ENABLED:
        return False, 0

    cause = machine.reset_cause()
    counted_cause = machine.PWRON_RESET if COUNT_RESET_CAUSE == "pwron" else machine.HARD_RESET
    if cause == counted_cause:
        count = load_reset_count() + 1
        print("Counted reset (cause {}). Multi-press count: {}".format(cause, count))
    else:
        # Power-on / brownout / soft reset: start the gesture fresh.
        count = 0
        print("Boot reset cause {}; multi-press counter cleared.".format(cause))

    if count >= PANIC_RESET_COUNT:
        print("RST triple-press registered; panic trigger armed.")
        clear_reset_count()
        return True, 0

    save_reset_count(count)
    return False, count


def build_alert_payload(fix, battery_level):
    # Documented Firebase hardwareAlert contract: the firmware only reports who
    # it is and where it is. Firebase resolves the user from the device ID and
    # builds the emergency message itself.
    return {
        "device_id": DEVICE_ID,
        "latitude": fix["latitude"] if fix else None,
        "longitude": fix["longitude"] if fix else None,
        "battery_level": battery_level,
    }


def build_sms_message(fix):
    lines = [SMS_MESSAGE_PREFIX, "Device: {}".format(DEVICE_ID)]
    if fix:
        lat = "{:.6f}".format(fix["latitude"])
        lon = "{:.6f}".format(fix["longitude"])
        lines.append("GPS: {},{}".format(lat, lon))
        source = fix.get("source", "sim7000g_gps")
        age = fix_age_seconds(fix)
        if age is not None:
            lines.append("Src: {} Age: {}s".format(source, age))
        else:
            lines.append("Src: {}".format(source))
        lines.append("Map: http://maps.google.com/?q={},{}".format(lat, lon))
    else:
        lines.append("Location unavailable")
    return "\n".join(lines)


def append_location_lines(lines, fix):
    if fix:
        lat = "{:.6f}".format(fix["latitude"])
        lon = "{:.6f}".format(fix["longitude"])
        lines.append("GPS: {},{}".format(lat, lon))
        source = fix.get("source", "sim7000g_gps")
        age = fix_age_seconds(fix)
        if age is not None:
            lines.append("Src: {} Age: {}s".format(source, age))
        else:
            lines.append("Src: {}".format(source))
        lines.append("Map: http://maps.google.com/?q={},{}".format(lat, lon))
    else:
        lines.append("Location unavailable")
    return lines


def build_boot_sms_message(fix):
    lines = [
        BOOT_SMS_MESSAGE,
        "User: {}".format(USER_DISPLAY_NAME),
        "User ID: {}".format(USER_ID),
        "Device: {}".format(DEVICE_ID),
    ]
    return "\n".join(append_location_lines(lines, fix))


def pressed_button(buttons):
    for button in buttons:
        if button.value() == 0:
            return button
    return None


def wait_for_button_hold(buttons, led):
    button = pressed_button(buttons)
    if button is None:
        return False

    pressed_at = time.ticks_ms()
    while button.value() == 0:
        led.update()
        if time.ticks_diff(time.ticks_ms(), pressed_at) >= BUTTON_HOLD_MS:
            while button.value() == 0:
                led.update()
                time.sleep_ms(10)
            return True
        time.sleep_ms(10)
    return False


def read_serial_trigger():
    if not DEV_SERIAL_TRIGGER_ENABLED:
        return False
    try:
        poll = select.poll()
        poll.register(sys.stdin, select.POLLIN)
        events = poll.poll(0)
        if not events:
            return False
        data = sys.stdin.read(1)
        return data == DEV_SERIAL_TRIGGER_KEY
    except Exception as exc:
        print("Serial dev trigger unavailable:", exc)
        return False


def choose_alert_location(modem, led, prefer_cached=True, gps_timeout_ms=GPS_TIMEOUT_MS):
    cached = load_last_gps() if prefer_cached else None
    if cached:
        print("Using saved GPS cache for immediate alert.")
        return cached

    fix = modem.acquire_gps(led, gps_timeout_ms)
    if fix:
        save_last_gps(fix)
        return fix

    if not prefer_cached:
        cached = load_last_gps()
        if cached:
            print("Fresh GPS unavailable; using saved GPS cache.")
            return cached
    return None


def refresh_gps_cache(modem, led):
    print("Refreshing saved GPS location.")
    led.set_pattern(Led.WAITING)
    fix = modem.acquire_gps(led, GPS_REFRESH_TIMEOUT_MS)
    if fix:
        save_last_gps(fix)
        print("GPS cache refreshed.")
    else:
        print("GPS cache refresh skipped: no fix.")
    led.set_pattern(Led.IDLE)


def deliver_alert(modem, led, prefer_cached_location=True):
    if not modem.ensure_awake():
        print("Modem did not respond.")
        return False

    led.set_pattern(Led.WAITING)
    if not modem.wait_for_network(led, NETWORK_TIMEOUT_MS):
        print("Network registration timed out.")
        fix = load_last_gps() if prefer_cached_location else None
    else:
        fix = choose_alert_location(
            modem,
            led,
            prefer_cached=prefer_cached_location,
            gps_timeout_ms=GPS_TIMEOUT_MS,
        )
        if not fix:
            print("GPS timed out; continuing without coordinates.")

    led.set_pattern(Led.SENDING)
    battery = modem.read_battery()
    payload = build_alert_payload(fix, battery)
    if modem.http_post_json(BACKEND_ALERT_URL, payload, HTTP_TIMEOUT_MS):
        print("HTTP alert delivered.")
        return True

    print("HTTP failed; sending SMS fallback.")
    sms = build_sms_message(fix)
    delivered = False
    for number in get_panic_contacts():
        led.update()
        if modem.send_sms(number, sms):
            delivered = True
    return delivered


def send_boot_sms(modem, led):
    if not SEND_BOOT_SMS_ON_START:
        return

    print("Sending boot SMS notification.")
    led.set_pattern(Led.WAITING)
    if not modem.ensure_awake():
        print("Boot SMS skipped: modem did not respond.")
        led.blink_for(Led.ERROR, 2500)
        led.set_pattern(Led.IDLE)
        return

    if not modem.wait_for_network(led, NETWORK_TIMEOUT_MS):
        print("Boot SMS skipped: network registration timed out.")
        led.blink_for(Led.ERROR, 2500)
        led.set_pattern(Led.IDLE)
        return

    fix = load_last_gps()
    if fix:
        print("Using saved GPS cache for boot SMS.")
    else:
        fix = modem.acquire_gps(led, BOOT_GPS_TIMEOUT_MS)
        if fix:
            save_last_gps(fix)
    if not fix:
        print("Boot GPS timed out; sending boot SMS without coordinates.")

    led.set_pattern(Led.SENDING)
    message = build_boot_sms_message(fix)
    delivered = False
    for number in get_panic_contacts():
        led.update()
        if modem.send_sms(number, message):
            delivered = True

    if delivered:
        print("Boot SMS sent.")
        led.blink_for(Led.SUCCESS, 2500)
    else:
        print("Boot SMS failed.")
        led.blink_for(Led.ERROR, 2500)
    led.set_pattern(Led.IDLE)


def send_boot_panic_alert(modem, led):
    if not SEND_PANIC_ON_BOOT:
        return

    print("Sending boot/reset panic alert.")
    ok = deliver_alert(modem, led, prefer_cached_location=True)
    if ok:
        led.blink_for(Led.SUCCESS, 2500)
    else:
        led.blink_for(Led.ERROR, 2500)
    led.set_pattern(Led.IDLE)


def main():
    led = Led(STATUS_LED_PIN, STATUS_LED_ACTIVE_LOW)
    buttons = [Pin(pin, Pin.IN, Pin.PULL_UP) for pin in PANIC_BUTTON_PINS]
    modem = Sim7000()

    panic_from_reset, reset_count = evaluate_reset_trigger()
    reset_window_start = time.ticks_ms()

    print("VIKELA MicroPython LILYGO T-SIM7000G panic firmware ready.")
    if RESET_TRIGGER_ENABLED:
        print("Reset trigger: press RST {} times in a row to send a panic alert.".format(
            PANIC_RESET_COUNT
        ))
    if REMOTE_TRIGGER_ENABLED:
        print("Remote trigger: text this device from an authorised number to send a panic alert.")
    if DEV_SERIAL_TRIGGER_ENABLED:
        print("Dev trigger: type '{}' in the serial console to send a panic alert.".format(
            DEV_SERIAL_TRIGGER_KEY
        ))
    led.set_pattern(Led.IDLE)
    send_boot_sms(modem, led)
    send_boot_panic_alert(modem, led)

    if panic_from_reset:
        print("RST multi-press panic trigger accepted.")
        ok = deliver_alert(modem, led, prefer_cached_location=True)
        led.blink_for(Led.SUCCESS if ok else Led.ERROR, 5000)
        led.set_pattern(Led.IDLE)
        reset_count = 0

    last_gps_refresh = time.ticks_ms() - GPS_REFRESH_INTERVAL_MS
    last_remote_poll = time.ticks_ms()

    while True:
        led.update()

        # A lone RST press must be followed by the next one within the window,
        # otherwise the multi-press gesture resets.
        if reset_count > 0 and due(reset_window_start, RESET_MULTIPRESS_WINDOW_MS):
            clear_reset_count()
            reset_count = 0
            print("Reset multi-press window expired; counter cleared.")

        triggered = wait_for_button_hold(buttons, led) or read_serial_trigger()
        if not triggered and REMOTE_TRIGGER_ENABLED and due(last_remote_poll, REMOTE_TRIGGER_POLL_MS):
            last_remote_poll = time.ticks_ms()
            triggered = modem.check_incoming_call() or modem.check_sms_trigger()

        if triggered:
            print("Panic trigger accepted.")
            ok = deliver_alert(modem, led, prefer_cached_location=True)
            if ok:
                led.blink_for(Led.SUCCESS, 5000)
            else:
                led.blink_for(Led.ERROR, 5000)
            led.set_pattern(Led.IDLE)
        elif due(last_gps_refresh, GPS_REFRESH_INTERVAL_MS):
            last_gps_refresh = time.ticks_ms()
            if modem.ensure_awake() and modem.wait_for_network(led, NETWORK_TIMEOUT_MS):
                refresh_gps_cache(modem, led)
        time.sleep_ms(20)


main()
