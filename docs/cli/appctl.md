# appctl

appctl is the host-side CLI for running DDI apps on **any systemd host**
(≥ 250 with OpenSSL; ≥ 254 for layered apps). It turns "image present" into
"service running, correctly wired" — systemd only *attaches*; appctl provides
*up*.

Source: [github.com/offline-lab/appctl](https://github.com/offline-lab/appctl)

> **Status:** designed 2026-07-04/05 ([ADR-0032](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0032-appctl-lifecycle-verbs.md),
> [ADR-0035](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0035-standardized-app-storage.md),
> [ADR-0036](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0036-foreign-host-baseline.md));
> unwritten. This page describes the designed surface.

## The model

Two independent axes, data orthogonal to both:

- **Cache axis:** `get` ↔ `rm` — fetch images into the local cache / drop them.
  Passive, cheap. A small device can cache hundreds of apps.
- **Run axis:** `up` ↔ `down` — activate / stop. Only this axis spends
  resources.
- **Data** survives `down` *and* `rm`. Only `drop`'s guarded path destroys it.

Two promises, never broken: **no implicit network** (only `get`/`--get` may
touch it; bare `up` on an uncached image fails loudly) and **no implicit data
loss**.

## Commands

| Command | What it does |
|---|---|
| `get <index>/<name>` | Fetch the latest version + its base closure into the cache (the only network verb) |
| `up <name>` / `down <name>` | Activate (attach + wire storage/uid/tmp + start declared units) / stop |
| `rm <name>` | Drop the cached image; data untouched; `get` restores exactly |
| `drop <name>` | Total guarded teardown: image + environment + uid/gid **+ data** — `THIS IS DESTRUCTIVE` |
| `up --get`, `get --up`, `down --rm`, `rm --down` | Composition: a verb moves its own axis; the flag opts into the other |
| `index trust <url\|path>` | Trust ceremony: pin an index's key, install its delegated build certs |
| `index list` / `index drop <alias>` | List trusted indexes / untrust (refuses while its apps remain provisioned) |
| `list` / `status` | What's cached, what's up (unprivileged) |
| `recover` | Idempotent reconcile: re-derive all generated artifacts from state (read-only hosts run this at boot) |
| `doctor` | Extendable rule set checking the host contract |

Addressing is always explicit — `get offline-lab/mpd`, never a bare name and
never a hidden default registry.

## Storage

Every app gets the same layout on every OS, always mounted:
`<root>/apps/<index-hash>/<app>/{config,data}` (+ a private `/tmp`).
`<root>` is relocatable; `config` is the operator's sanctioned override
surface. Per-app uids (configurable base, default 6000+) isolate apps from
each other; the same uid is used on every start — data is never chowned.

## Trust

Two gates: the signed index governs what enters the cache (`get`); systemd
verifies the DDI's embedded build signature at **every start** (`up`), against
certs installed at `index trust`. See the
[security model](../specs/security-model.md).
