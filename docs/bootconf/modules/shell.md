# shell

Executes shell commands at boot via `bash -c`, capturing output to log files.

## What it does

For each configured command:

1. Checks whether to skip (firstboot sentinel present).
2. Runs the command with `bash -c <command>`.
3. Writes stdout, stderr, and exit code to `<directory>/<name>.log`.
4. If `firstboot: true`, writes a sentinel file after the run.
5. If the command exits non-zero and `allow_fail: false`, stops processing and marks the module as failed.

Commands run **in order**. The module stops at the first failure when `allow_fail: false`.

## Config

```yaml
shell:
  enabled: true
  directory: /var/lib/bootconf/shell
  commands:
    - name: init-database
      allow_fail: false
      firstboot: true
      command: |
        /usr/local/bin/init-database.sh
        exit 0

    - name: health-check
      allow_fail: true
      firstboot: false
      command: systemctl is-active myservice
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `directory` | string | | Directory for log files and firstboot sentinels |
| `path` | string | | Prepend a directory to `PATH` for every command (e.g. `/usr/lib/framework/bin`). Inherits environment `PATH` when empty. |
| `commands[].name` | string | | Command name. Used as the base for log and sentinel filenames. |
| `commands[].command` | string | | Shell command passed to `bash -c` |
| `commands[].allow_fail` | bool | `false` | If `false`, a non-zero exit stops the module and reports failure |
| `commands[].firstboot` | bool | `false` | If `true`, the command runs only once |

## Log files

For each run, bootconf writes `<directory>/<name>.log`:

```
Exit code: 0
--- stdout ---
database initialized
--- stderr ---
```

The log is always written, regardless of whether the command succeeded or failed.

## First-boot commands

When `firstboot: true`, bootconf checks for a sentinel file at `<directory>/<name>.firstboot` before running:

- If the sentinel exists: the command is skipped silently.
- If the sentinel does not exist: the command runs, and the sentinel is written **after** the run, regardless of exit code.

A first-boot command that fails will not loop forever: the sentinel prevents re-execution on subsequent boots. If you want to retry a failed first-boot command, delete the sentinel file.

## Failure handling

| `allow_fail` | Exit code | Outcome |
|---|---|---|
| `false` (default) | 0 | Continue to next command |
| `false` (default) | non-zero | Stop module, report failure |
| `true` | 0 | Continue to next command |
| `true` | non-zero | Log the failure, continue to next command |

## Dry-run

In dry-run mode, commands are **not executed**. The firstboot check is also skipped.

```
INFO [shell] would run command "init-database" (dry-run)
INFO [shell] would run command "health-check" (dry-run)
```
