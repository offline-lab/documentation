# Resource Tracking

appctl checks available resources before installing an app. If the device cannot
comfortably run the app, the install warns or errors rather than silently degrading
the system.

---

## App resource estimates

Each package declares expected resource usage at three load levels in `package.yaml`:

```yaml
resources:
  low:
    cpu_percent: 2
    memory_mb: 24
    storage_mb: 45
  moderate:
    cpu_percent: 15
    memory_mb: 64
    storage_mb: 45
  heavy:
    cpu_percent: 40
    memory_mb: 128
    storage_mb: 45
```

| Field | Unit | Description |
|---|---|---|
| `cpu_percent` | % of one core | Sustained CPU usage at this load level |
| `memory_mb` | MB | RSS memory at this load level |
| `storage_mb` | MB | Disk space for the DDI + data dir combined |

`storage_mb` is the same across load levels (storage is not load-dependent).
`low` = idle/minimal activity. `moderate` = typical use. `heavy` = peak load.

**DDI overhead:** the packaged `.raw` DDI is larger than a bare squashfs would be.
Authors should account for the GPT header, verity hash tree, partition alignment, and
the signature partition when estimating `storage_mb`. As a rough heuristic, add ~10%
over the raw root filesystem size for small images (less for larger ones as overhead
is mostly fixed).

buildctl does not validate these values; they are declared by the package author
and used by appctl as a signal, not a hard contract.

---

## Host baseline

`offlinelab-resources.service` runs once per boot after mounts are available,
before `multi-user.target`. It measures the baseline cost of the OS itself and
writes the result to `/var/lib/appctl/resources.json`.

Schema:

```json
{
  "total_memory_mb": 512,
  "total_storage_mb": 28000,
  "cpu_cores": 4,
  "baseline_memory_mb": 98,
  "baseline_cpu_percent": 8,
  "measured_at": "2026-06-07T10:00:00Z"
}
```

| Field | Description |
|---|---|
| `total_memory_mb` | Total RAM from `/proc/meminfo` MemTotal |
| `total_storage_mb` | Total size of `/data` partition |
| `cpu_cores` | Number of online CPUs from `/sys/devices/system/cpu/online` |
| `baseline_memory_mb` | Average RSS of all running processes sampled over 10 seconds |
| `baseline_cpu_percent` | Average CPU usage sampled over 10 seconds (across all cores, normalised to one core) |
| `measured_at` | ISO 8601 timestamp of the measurement |

The baseline is re-measured on every boot. It reflects the current OS state including
all already-installed apps that auto-start, not just the bare OS.

---

## Install-time check

appctl checks available resources against the app's `moderate` estimate before
installing. `moderate` is used because it represents typical running conditions.

```
available_memory = total_memory_mb - baseline_memory_mb
available_storage = total_storage_mb - used_storage_mb  (df on /data)
```

| Condition | Behaviour |
|---|---|
| `available_memory < moderate.memory_mb` | Error; refuse install |
| `available_memory < moderate.memory_mb * 1.5` | Warn; proceed |
| `available_storage < moderate.storage_mb` | Error; refuse install |
| No `resources.json` exists | Warn and proceed (baseline not yet measured) |
| Package has no `resources` field | Proceed without check |

`--ignore-resources` bypasses all checks. Intended for testing and edge cases.

---

## `resources.sh` framework module

A framework library module provides read access to the baseline from shell scripts
and other framework tools:

```bash
resources::get <key>            # read any field from resources.json
resources::available_memory     # total_memory_mb - baseline_memory_mb
resources::available_storage    # free space on /data in MB
resources::cpu_cores            # number of online CPUs
```

---

## Buildroot implications

- `offlinelab-resources` package ships the measurement service and script
- Runs as: `offlinelab-resources.service` (`After=local-fs.target`, `Before=multi-user.target`)
- Writes to `/var/lib/appctl/resources.json` (requires `/data` to be mounted)
- `resources.sh` added to `FRAMEWORK_INIT_MODULES` in `framework/library/import.sh`
- `jq` required for JSON read/write (`BR2_PACKAGE_JQ=y`, already required)
