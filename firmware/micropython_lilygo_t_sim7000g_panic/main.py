import json
import select
import sys
import time

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

# HTTP alert endpoint.
# For cellular testing, use a public URL. Local 192.168.x.x addresses are
# usually not reachable from the SIM7000G cellular network.
# Example: "https://example.com/api/alerts/hardware"
BACKEND_ALERT_URL = "http://yourusername.pythonanywhere.com/api/alerts/hardware"

# Device/user identity sent in HTTP payloads and SMS fallback messages.
DEVICE_ID = "VIKELA-T-SIM7000G-001"
USER_ID = "user-001"
USER_DISPLAY_NAME = "VIKELA User"

# SMS fallback settings.
SMS_MESSAGE_PREFIX = "VIKELA EMERGENCY ALERT"
EMERGENCY_CONTACTS = [
    "+233000000000"
]
FETCH_CONTACTS_FROM_BACKEND = True
BACKEND_CONTACT_NUMBERS_URL = ""
SEND_BOOT_SMS_ON_START = False
BOOT_SMS_MESSAGE = "VIKELA device powered on"

# LILYGO T-SIM7000G board pins.
MODEM_RX = 26
MODEM_TX = 27
MODEM_PWRKEY = 4
MODEM_POWER_ON = 23
MODEM_RST = 5

# VIKELA panic-device pins.
PANIC_BUTTON_PIN = 32
STATUS_LED_PIN = 12
STATUS_LED_ACTIVE_LOW = True

# Behavior tuning.
BUTTON_HOLD_MS = 1200
NETWORK_TIMEOUT_MS = 60000
GPS_TIMEOUT_MS = 90000
BOOT_GPS_TIMEOUT_MS = 30000
HTTP_TIMEOUT_MS = 30000
CONTACTS_HTTP_TIMEOUT_MS = 20000
DEV_SERIAL_TRIGGER_ENABLED = True
DEV_SERIAL_TRIGGER_KEY = "p"
SEND_PANIC_ON_BOOT = True
GPS_CACHE_FILE = "last_gps.json"
CONTACTS_CACHE_FILE = "panic_contacts.json"
GPS_REFRESH_INTERVAL_MS = 60000
GPS_REFRESH_TIMEOUT_MS = 15000


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

    def configure_pdp(self):
        apn = CELLULAR_APN
        self.at('AT+SAPBR=3,1,"Contype","GPRS"', 3000)
        self.at('AT+SAPBR=3,1,"APN","{}"'.format(apn), 3000)
        if CELLULAR_USER:
            self.at('AT+SAPBR=3,1,"USER","{}"'.format(CELLULAR_USER), 3000)
        if CELLULAR_PASS:
            self.at('AT+SAPBR=3,1,"PWD","{}"'.format(CELLULAR_PASS), 3000)
        self.at("AT+SAPBR=0,1", 5000)
        ok, _ = self.at("AT+SAPBR=1,1", 20000)
        if not ok:
            return False
        ok, _ = self.at("AT+SAPBR=2,1", 5000)
        return ok

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

        if not self.configure_pdp():
            print("PDP context setup failed.")
            return False

        body = json.dumps(payload)
        self.at("AT+HTTPTERM", 2000)
        ok, _ = self.at("AT+HTTPINIT", 5000)
        if not ok:
            return False
        self.at("AT+HTTPPARA=\"CID\",1", 3000)
        if parsed["ssl"]:
            ok, _ = self.at("AT+HTTPSSL=1", 3000)
            if not ok:
                print("HTTPS setup failed on modem.")
                self.at("AT+HTTPTERM", 2000)
                return False
        else:
            self.at("AT+HTTPSSL=0", 3000)
        self.at("AT+HTTPPARA=\"URL\",\"{}\"".format(url), 3000)
        self.at("AT+HTTPPARA=\"CONTENT\",\"application/json\"", 3000)

        ok, response = self.at("AT+HTTPDATA={},10000".format(len(body)), 5000, "DOWNLOAD")
        if not ok:
            self.at("AT+HTTPTERM", 2000)
            return False
        self.uart.write(body.encode())
        response = self.read_until("OK", 12000)
        print("AT<", response.strip())
        if "OK" not in response:
            self.at("AT+HTTPTERM", 2000)
            return False

        self.clear()
        self.uart.write(b"AT+HTTPACTION=1\r\n")
        response = self.read_until("+HTTPACTION:", timeout_ms)
        response += self.read_until("OK", 5000)
        print("AT<", response.strip())
        self.at("AT+HTTPTERM", 2000)
        return http_action_success(response)

    def http_get_json(self, url, timeout_ms):
        parsed = parse_http_url(url)
        if not parsed:
            print("Only http:// and https:// URLs are supported.")
            return None

        if not self.configure_pdp():
            print("PDP context setup failed.")
            return None

        self.at("AT+HTTPTERM", 2000)
        ok, _ = self.at("AT+HTTPINIT", 5000)
        if not ok:
            return None
        self.at("AT+HTTPPARA=\"CID\",1", 3000)
        if parsed["ssl"]:
            ok, _ = self.at("AT+HTTPSSL=1", 3000)
            if not ok:
                print("HTTPS setup failed on modem.")
                self.at("AT+HTTPTERM", 2000)
                return None
        else:
            self.at("AT+HTTPSSL=0", 3000)
        self.at("AT+HTTPPARA=\"URL\",\"{}\"".format(url), 3000)

        self.clear()
        self.uart.write(b"AT+HTTPACTION=0\r\n")
        response = self.read_until("+HTTPACTION:", timeout_ms)
        response += self.read_until("OK", 5000)
        print("AT<", response.strip())
        if not http_action_success(response):
            self.at("AT+HTTPTERM", 2000)
            return None

        ok, read_response = self.at("AT+HTTPREAD", 10000)
        self.at("AT+HTTPTERM", 2000)
        if not ok:
            return None
        return parse_httpread_json(read_response)

    def send_sms(self, number, message):
        self.at("AT+CMGF=1", 3000)
        self.at('AT+CSCS="GSM"', 3000)
        self.at("AT+CSMP=17,167,0,0", 3000)
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
    host = host_port.split(":", 1)[0]
    return {"host": host, "path": path, "ssl": ssl}


def backend_contact_numbers_url():
    if BACKEND_CONTACT_NUMBERS_URL:
        return BACKEND_CONTACT_NUMBERS_URL

    marker = "/api/alerts/hardware"
    index = BACKEND_ALERT_URL.find(marker)
    if index >= 0:
        return BACKEND_ALERT_URL[:index] + "/api/panic-contacts/numbers"

    parsed = parse_http_url(BACKEND_ALERT_URL)
    if not parsed:
        return ""

    scheme = "https://" if parsed["ssl"] else "http://"
    rest = BACKEND_ALERT_URL[len(scheme):]
    slash = rest.find("/")
    base = scheme + (rest if slash < 0 else rest[:slash])
    return base + "/api/panic-contacts/numbers"


def http_action_success(response):
    for line in response.splitlines():
        if "+HTTPACTION:" not in line:
            continue
        try:
            parts = line.split(":", 1)[1].split(",")
            status = int(parts[1].strip())
            return 200 <= status < 300
        except (IndexError, ValueError):
            return False
    return False


def parse_httpread_json(response):
    start = response.find("{")
    end = response.rfind("}")
    if start < 0 or end < start:
        print("HTTP response did not contain JSON.")
        return None
    try:
        return json.loads(response[start:end + 1])
    except ValueError as exc:
        print("Could not parse HTTP JSON:", exc)
        return None


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


def save_contact_cache(numbers):
    numbers = clean_contact_numbers(numbers)
    if not numbers:
        return
    try:
        with open(CONTACTS_CACHE_FILE, "w") as handle:
            handle.write(json.dumps({
                "phone_numbers": numbers,
                "saved_ms": time.ticks_ms(),
            }))
        print("Saved panic contact cache.")
    except Exception as exc:
        print("Could not save panic contact cache:", exc)


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


def fallback_panic_contacts(reason):
    cached = load_contact_cache()
    if cached:
        print("{}; using saved panic contact cache.".format(reason))
        return cached
    print("{}; using built-in local contacts.".format(reason))
    return EMERGENCY_CONTACTS


def get_panic_contacts(modem):
    if not FETCH_CONTACTS_FROM_BACKEND:
        return fallback_panic_contacts("Backend contact fetch disabled")

    url = backend_contact_numbers_url()
    if not url:
        return fallback_panic_contacts("Backend contact URL unavailable")

    print("Fetching panic contacts from backend.")
    data = modem.http_get_json(url, CONTACTS_HTTP_TIMEOUT_MS)
    if not data:
        return fallback_panic_contacts("Backend contacts unavailable")

    numbers = clean_contact_numbers(data.get("phone_numbers"))
    if not numbers:
        return fallback_panic_contacts("Backend returned no enabled contacts")

    save_contact_cache(numbers)
    print("Using {} backend panic contact(s).".format(len(numbers)))
    return numbers


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


def build_alert_payload(fix):
    return {
        "device_id": DEVICE_ID,
        "user_id": USER_ID,
        "trigger_type": "hardware",
        "latitude": fix["latitude"] if fix else None,
        "longitude": fix["longitude"] if fix else None,
        "location_source": fix.get("source", "sim7000g_gps") if fix else "unavailable",
        "delivery_attempt": "cellular_http",
        "battery_level": -1,
        "timestamp": "unavailable",
        "message": SMS_MESSAGE_PREFIX,
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


def wait_for_button_hold(button, led):
    if button.value() == 1:
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
    payload = build_alert_payload(fix)
    if modem.http_post_json(BACKEND_ALERT_URL, payload, HTTP_TIMEOUT_MS):
        print("HTTP alert delivered.")
        return True

    print("HTTP failed; sending SMS fallback.")
    sms = build_sms_message(fix)
    delivered = False
    for number in get_panic_contacts(modem):
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
    for number in get_panic_contacts(modem):
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
    button = Pin(PANIC_BUTTON_PIN, Pin.IN, Pin.PULL_UP)
    modem = Sim7000()

    print("VIKELA MicroPython LILYGO T-SIM7000G panic firmware ready.")
    if DEV_SERIAL_TRIGGER_ENABLED:
        print("Dev trigger: type '{}' in the serial console to send a panic alert.".format(
            DEV_SERIAL_TRIGGER_KEY
        ))
    led.set_pattern(Led.IDLE)
    send_boot_sms(modem, led)
    send_boot_panic_alert(modem, led)
    last_gps_refresh = time.ticks_ms() - GPS_REFRESH_INTERVAL_MS

    while True:
        led.update()
        if wait_for_button_hold(button, led) or read_serial_trigger():
            print("Panic trigger accepted.")
            ok = deliver_alert(modem, led, prefer_cached_location=True)
            if ok:
                led.blink_for(Led.SUCCESS, 5000)
            else:
                led.blink_for(Led.ERROR, 5000)
            led.set_pattern(Led.IDLE)
        elif time.ticks_diff(time.ticks_ms(), last_gps_refresh) >= GPS_REFRESH_INTERVAL_MS:
            last_gps_refresh = time.ticks_ms()
            if modem.ensure_awake() and modem.wait_for_network(led, NETWORK_TIMEOUT_MS):
                refresh_gps_cache(modem, led)
        time.sleep_ms(20)


main()
