# GPS Broadcaster

GPS broadcasters send UDP messages on port 5354 — the same port disco uses for host discovery. Two message types are produced:

| Type | Purpose |
|------|---------|
| `TIME_ANNOUNCE` | Stratum-1 time reference; consumed by `time_sync` |
| `LOCATION_ANNOUNCE` | GPS fix data (lat/lon/alt/satellites); stored in the location index |

Three implementations send `TIME_ANNOUNCE`: the Go binary (built as part of this project), an Arduino sketch, and an ESPHome component. The Heltec Wireless Tracker (`esp32-timesyncd`) sends **both** message types.

## Go binary (Raspberry Pi, Linux)

### Build

```bash
make                                              # builds disco-gps-broadcaster for the current platform
```

Cross-compile for Raspberry Pi Zero 2W (arm64):

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=arm64 go build \
  -o build/bin/disco-gps-broadcaster cmd/gps-broadcaster/main.go
```

### Run

```bash
disco-gps-broadcaster -device /dev/ttyACM0
```

With options:

```bash
disco-gps-broadcaster \
  -device /dev/ttyACM0 \
  -broadcast 255.255.255.255:5354 \
  -id gps-pi-01 \
  -interval 16s \
  -interfaces eth0,wlan0 \
  -v
```

| Flag | Description |
|------|-------------|
| `-device` | Serial device path (e.g. `/dev/ttyACM0`) |
| `-broadcast` | Broadcast address (default `255.255.255.255:5354`) |
| `-id` | Source ID included in messages |
| `-interval` | Broadcast interval (default `16s`) |
| `-interfaces` | Comma-separated list of interfaces to broadcast on |
| `-v` | Verbose output |

### systemd service

Create `/etc/systemd/system/disco-gps-broadcaster.service`:

```ini
[Unit]
Description=Disco GPS time broadcaster
After=network.target

[Service]
ExecStart=/usr/local/bin/disco-gps-broadcaster -device /dev/ttyACM0 -id gps-pi-01
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now disco-gps-broadcaster
```

## Arduino

The Arduino sketch is in `gps-broadcaster/arduino/`. It reads NMEA data from a GPS module over a serial connection and broadcasts TIME_ANNOUNCE messages via UDP.

### Hardware

Connect a GPS module to the Arduino's hardware serial pins. The sketch reads from `Serial1` by default.

### Flash

Open `gps-broadcaster/arduino/gps_time_broadcaster.ino` in the Arduino IDE (or use PlatformIO with `gps-broadcaster/arduino/platformio.ini`). Configure your network settings in the sketch before uploading:

```cpp
// Broadcast interval (milliseconds)
const unsigned long BROADCAST_INTERVAL = 16000;
```

## ESPHome (ESP32 / ESP8266)

The ESPHome component is in `gps-broadcaster/esphome/`. Copy both files to your ESPHome configuration directory.

### Hardware (ESP32)

| GPS Module | ESP32 |
|------------|-------|
| VCC | 3.3V |
| GND | GND |
| TX | GPIO16 (RX2) |
| RX | GPIO17 (TX2) |

### Configure and flash

Edit `gps-broadcaster.yaml` to set your Wi-Fi credentials and source ID, then flash:

```bash
esphome run gps-broadcaster.yaml
```

Tune the broadcaster in `gps-broadcaster.yaml`:

```yaml
custom_component:
  - lambda: |-
      auto broadcaster = new GPSBroadcasterComponent();
      broadcaster->set_source_id("gps-esphome-01");
      broadcaster->set_interval(16000);    # ms between broadcasts
      broadcaster->set_port(5354);
      App.register_component(broadcaster);
      return {broadcaster};
```

## Heltec Wireless Tracker (esp32-timesyncd)

The `esp32-timesyncd` firmware runs on a Heltec Wireless Tracker and sends both message types:

- **`TIME_ANNOUNCE`** — every 16 seconds when a GPS fix is held
- **`LOCATION_ANNOUNCE`** — every 60 seconds when a GPS fix is held

The location broadcast payload:

```json
{
  "type": "LOCATION_ANNOUNCE",
  "message_id": "gps-timeserver-<millis>",
  "timestamp": 1718000000,
  "source_id": "gps-timeserver",
  "location": {
    "latitude": 52.370216,
    "longitude": 4.895168,
    "altitude": 3.5,
    "fix": true,
    "satellites": 8
  }
}
```

The daemon stores the latest fix per `source_id`. Query it with:

```bash
disco location
disco location show gps-timeserver
disco location --json
```

## Verify

On any node running disco-daemon with `time_sync.enabled: true`, listen for broadcasts:

```bash
sudo tcpdump -i any udp port 5354 -A
```

Check time sync:

```bash
disco time
```

`Sources: 1` (or more) confirms the daemon received a `TIME_ANNOUNCE` message.

Check location data:

```bash
disco location
```

A row in the output confirms the daemon received a `LOCATION_ANNOUNCE` message.
