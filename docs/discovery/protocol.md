# Discovery protocol reference

This section describes the wire protocol for anyone building a client implementation. Disco uses two transport channels: UDP broadcast for discovery and time synchronization, and Unix domain sockets for local name queries.

## Transport

| Channel | Address | Purpose |
|---|---|---|
| UDP broadcast | 255.255.255.255:5354 (configurable) | Node announcements, time broadcasts, location broadcasts |
| Unix domain socket | /run/disco.sock (configurable) | Local name queries from NSS module |

All messages are JSON-encoded UTF-8. Each UDP datagram contains exactly one message. Unix socket messages are length-prefixed (4-byte big-endian length, then JSON body).

## Message types

### ANNOUNCE

Sent by every node at a configurable interval (default 30 seconds). Contains the node's identity and services.

```json
{
  "type": "ANNOUNCE",
  "message_id": "web1-1708123456789000000",
  "timestamp": 1708123456,
  "hostname": "web1",
  "ips": ["192.168.1.10", "10.0.0.1"],
  "services": [
    {"name": "www", "port": 80, "addr": "192.168.1.10"},
    {"name": "ssh", "port": 22, "addr": "192.168.1.10"}
  ],
  "ttl": 3600,
  "signature": {
    "signature": "a3f2b8...",
    "signer": "node-abc123",
    "nonce": "c9d4e1...",
    "timestamp": 1708123456
  }
}
```

| Field | Type | Description |
|---|---|---|
| type | string | Always `"ANNOUNCE"` |
| message_id | string | Unique ID: `{hostname}-{unix_nano}`. Used for deduplication. |
| timestamp | int64 | Unix seconds when the message was created |
| hostname | string | Node's hostname |
| ips | string[] | All non-loopback IPv4 addresses on the node |
| services | ServiceInfo[] | Detected services on this node |
| ttl | int64 | How long other nodes should cache this record (seconds). Default: 3600. |
| signature | object or null | HMAC-SHA256 signature (omitted when security is disabled) |

**ServiceInfo:**

| Field | Type | Description |
|---|---|---|
| name | string | Service name (e.g. `"www"`, `"smtp"`, `"ssh"`) |
| port | int | TCP port number |
| addr | string | Local IP address the service is bound to |

### TIME_ANNOUNCE

Sent by GPS broadcaster devices to provide time references for clock synchronization.

```json
{
  "type": "TIME_ANNOUNCE",
  "message_id": "gps-node-1-1708123456789000000",
  "timestamp": 1708123456789000000,
  "source_id": "gps-node-1",
  "clock_info": {
    "stratum": 1,
    "precision": -20,
    "root_delay": 0.0,
    "root_dispersion": 0.0001,
    "reference_id": "GPS",
    "reference_time": 1708123456789000000
  },
  "leap_indicator": 0,
  "signature": {
    "signature": "b7c3d9...",
    "signer": "gps-node-1",
    "nonce": "e1f2a3...",
    "timestamp": 1708123456
  }
}
```

| Field | Type | Description |
|---|---|---|
| type | string | Always `"TIME_ANNOUNCE"` |
| message_id | string | Unique ID for deduplication |
| timestamp | int64 | Nanosecond-precision Unix timestamp from GPS |
| source_id | string | Identifier of the GPS source |
| clock_info | ClockInfo | NTP-like clock quality metrics |
| leap_indicator | int | Leap second indicator (0 = none, 1 = last minute has 61 seconds, 2 = 59 seconds) |
| signature | object or null | HMAC-SHA256 signature |

**ClockInfo:**

| Field | Type | Description |
|---|---|---|
| stratum | int | NTP stratum (1 = GPS, 2 = synced to stratum-1, etc.) |
| precision | int | Log2 of clock precision in seconds (-20 = ~1 microsecond) |
| root_delay | float64 | Round-trip delay to reference clock (seconds) |
| root_dispersion | float64 | Maximum error relative to reference clock (seconds) |
| reference_id | string | Reference clock identifier (e.g. `"GPS"`) |
| reference_time | int64 | Reference timestamp (nanoseconds) |

### LOCATION_ANNOUNCE

Sent by GPS broadcaster devices to share location data with the network. Nodes can use this for timezone detection, country estimation, and geofencing.

```json
{
  "type": "LOCATION_ANNOUNCE",
  "message_id": "gps-node-1-1708123456789000000",
  "source_id": "gps-node-1",
  "location": {
    "latitude": 52.3676,
    "longitude": 4.9041,
    "altitude": 12.5,
    "fix": true,
    "satellites": 8
  },
  "estimated_country": "NL",
  "estimated_timezone": "Europe/Amsterdam",
  "signature": {
    "signature": "d4e5f6...",
    "signer": "gps-node-1",
    "nonce": "a7b8c9...",
    "timestamp": 1708123456
  }
}
```

| Field | Type | Description |
|---|---|---|
| type | string | Always `"LOCATION_ANNOUNCE"` |
| message_id | string | Unique ID for deduplication |
| source_id | string | Identifier of the GPS source |
| location | LocationInfo | GPS position data |
| estimated_country | string | ISO 3166-1 alpha-2 country code (e.g. `"NL"`) |
| estimated_timezone | string | IANA timezone name (e.g. `"Europe/Amsterdam"`) |
| signature | object or null | HMAC-SHA256 signature |

**LocationInfo:**

| Field | Type | Description |
|---|---|---|
| latitude | float64 | Decimal degrees (WGS 84) |
| longitude | float64 | Decimal degrees (WGS 84) |
| altitude | float64 | Meters above sea level |
| fix | bool | Whether the GPS has a valid position fix |
| satellites | int | Number of satellites in use |

## NSS query protocol

The Unix domain socket uses a request-response pattern. Each query is a JSON object with a `type` field. The daemon responds with a JSON object.

### Query by name

```json
{"type": "QUERY_BY_NAME", "name": "web1", "request_id": "query-123456"}
```

Response (success):

```json
{
  "type": "OK",
  "request_id": "query-123456",
  "name": "web1",
  "addrs": ["192.168.1.10"]
}
```

Response (not found):

```json
{"type": "NOTFOUND", "request_id": "query-123456"}
```

### Query by address

```json
{"type": "QUERY_BY_ADDR", "addr": "192.168.1.10", "request_id": "query-789"}
```

Response format is the same as query by name.

### List all hosts

```json
{"type": "LIST_HOSTS", "request_id": "list-1"}
```

Response:

```json
{
  "type": "OK",
  "request_id": "list-1",
  "hosts": [
    {
      "hostname": "web1",
      "addresses": ["192.168.1.10"],
      "status": "healthy",
      "services": {"www": "80"},
      "last_seen": 1708123456,
      "last_seen_ago": "2m",
      "is_static": false
    }
  ]
}
```

### List all services

```json
{"type": "LIST_SERVICES", "request_id": "list-2"}
```

Response:

```json
{
  "type": "OK",
  "request_id": "list-2",
  "services": [
    {"name": "www", "protocol": "tcp", "port": 80, "hosts": ["web1"], "status": "healthy"}
  ]
}
```

### Location status

```json
{"type": "LOCATION_STATUS", "request_id": "loc-1"}
```

Response:

```json
{
  "type": "OK",
  "request_id": "loc-1",
  "sources": [
    {
      "source_id": "gps-node-1",
      "latitude": 52.3676,
      "longitude": 4.9041,
      "altitude": 12.5,
      "fix": true,
      "satellites": 8,
      "estimated_country": "NL",
      "estimated_timezone": "Europe/Amsterdam",
      "last_seen_ago": "30s"
    }
  ],
  "count": 1
}
```

## Message signing

When security is enabled, messages include a `signature` object:

| Field | Type | Description |
|---|---|---|
| signature | string | Hex-encoded HMAC-SHA256 of `nonce + payload` |
| signer | string | Node ID of the signer |
| nonce | string | 32-character hex-encoded random nonce |
| timestamp | int64 | Unix seconds when the signature was created |

**Signing algorithm:**

1. Serialize the message fields (excluding `signature`) as deterministic JSON
2. Generate a random 16-byte nonce, hex-encode it
3. Compute HMAC-SHA256 over `nonce_bytes + message_json` using the shared secret
4. Hex-encode the HMAC digest as the signature

**Verification:**

1. Look up the shared secret for the signer's node ID
2. Reject if timestamp is older than 300 seconds or in the future
3. Recompute HMAC over `nonce_bytes + message_json` using the signer's shared secret
4. Compare using constant-time equality

## Rate limiting

Outgoing broadcasts are rate-limited with a token bucket algorithm: 10 messages per second, burst of 10. Incoming messages pass through a duplicate filter with a 5-minute TTL keyed on `message_id`. Duplicates are silently dropped.

## Host record lifecycle

1. A node receives an ANNOUNCE and creates a record with status `healthy`
2. The record's TTL counts down (default 3600 seconds)
3. If refreshed by a new broadcast, TTL resets
4. After TTL expires, status changes to `stale`
5. After a grace period (default 60 seconds), status changes to `lost`
6. Lost records are eventually removed from the cache

## Building a client

A minimal disco client needs to:

1. **Listen on UDP port 5354** for broadcast messages
2. **Parse JSON** datagrams and check the `type` field
3. **Deduplicate** by `message_id` to avoid processing the same announcement twice
4. **Extract host information** from `hostname`, `ips`, and `services` fields
5. **Cache records** with a TTL from the `ttl` field
6. **Periodically announce** its own identity using the ANNOUNCE format

Pseudo-code for a listener:

```
socket = bind_udp("0.0.0.0:5354")
seen_ids = cache_with_ttl(5 minutes)

loop:
    data = socket.recv()
    msg = json_decode(data)

    if msg.message_id in seen_ids:
        continue
    seen_ids.add(msg.message_id)

    if msg.type == "ANNOUNCE":
        store_record(msg.hostname, msg.ips, msg.services, msg.ttl)
    elif msg.type == "TIME_ANNOUNCE":
        handle_time(msg.timestamp, msg.source_id, msg.clock_info)
    elif msg.type == "LOCATION_ANNOUNCE":
        store_location(msg.source_id, msg.location, msg.estimated_country, msg.estimated_timezone)
```

Pseudo-code for announcing:

```
socket = create_udp_socket()
interval = 30 seconds

loop every interval:
    msg = {
        type: "ANNOUNCE",
        message_id: hostname + "-" + current_time_nanoseconds,
        timestamp: current_time_seconds,
        hostname: my_hostname,
        ips: my_ip_addresses,
        services: my_detected_services,
        ttl: 3600
    }
    data = json_encode(msg)
    socket.send_to(data, "255.255.255.255:5354")
```

For querying the daemon locally:

```
socket = connect_unix("/run/disco.sock")

query = {
    type: "QUERY_BY_NAME",
    name: "web1",
    request_id: random_id()
}

send_length_prefixed(socket, json_encode(query))
response = recv_length_prefixed(socket)
result = json_decode(response)

if result.type == "OK":
    return result.addrs
else:
    return not_found
```
