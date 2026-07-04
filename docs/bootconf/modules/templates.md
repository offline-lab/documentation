# templates

Renders Go `text/template` files with config-supplied variables and writes the result to a destination path.

## What it does

For each configured template entry:

1. Reads the source file and parses it as a Go `text/template`.
2. Executes the template with the configured variables.
3. Writes the rendered output to the destination path.

If the destination already exists, the rendered output is written to `<destination>.new` instead. Existing files are **never overwritten**.

## Config

```yaml
templates:
  enabled: true
  templates:
    - source: /boot/firmware/templates/app.conf.tpl
      destination: /etc/app/app.conf
      chmod: "640"
      variables:
        listen_address: "127.0.0.1"
        port: "8080"
        log_level: "info"
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | | Enable the module |
| `templates[].source` | string | | Source template file path |
| `templates[].destination` | string | | Destination path for rendered output |
| `templates[].chmod` | string | `640` | Octal permission string |
| `templates[].variables` | map | | Key/value pairs available in the template |

## Template syntax

Templates use Go's `text/template` syntax. Variables are accessed with dot notation:

```
# app.conf.tpl
listen = {{ .listen_address }}:{{ .port }}
log_level = {{ .log_level }}
```

Renders to:

```
# app.conf
listen = 127.0.0.1:8080
log_level = info
```

Missing keys are **fatal**. If a variable referenced in the template is not present in `variables`, the module fails with an error. This is enforced via `missingkey=error` so typos and missing entries are caught early.

## Dry-run

In dry-run mode, the template is still **parsed and executed** — syntax errors and missing variables are reported — but nothing is written to disk.

```
INFO [templates] would render /boot/firmware/templates/app.conf.tpl → /etc/app/app.conf (dry-run)
```

This means `bootconf run --dry-run` catches template errors before the next real boot.

## Permissions

The rendered file is written as `root:root`. The `chmod` value is applied after writing. Values above `0777` are rejected.

## vs. files

Use `files` when you want to place a static file as-is. Use `templates` when the content needs to be generated from variables that differ between deployments.
