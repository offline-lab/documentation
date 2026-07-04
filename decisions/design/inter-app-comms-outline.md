# Inter-App Communication — Design Session Framework

**Status:** Framework / pre-design. Not a decision document.
**Audience:** The future design session that resolves how Offline Lab apps
discover and connect to each other on the same host.
**Predecessor:** [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §11.3 deferred this topic with
the constraints restated below. This document picks that thread up.

---

## 1. Purpose of this document

This is **not** the design. It is the agenda and reference material for the
session that will produce the design. It exists to:

- State the problem precisely enough to debate it.
- Fix the constraints so the session does not relitigate settled decisions.
- Survey the option space with honest pros/cons, including the ways each option
  fails.
- Surface the open questions that *must* be answered before a design can be
  committed.
- Propose one starting direction (disco-based) as a concrete thing to react to,
  not as a recommendation.

The session should leave with: a chosen discovery mechanism, a chosen transport
mechanism (these may differ), a position on the nspawn private-network case, and
a set of changes to `package.yaml` / metadata if any.

---

## 2. Problem statement

Offline Lab runs multiple apps concurrently on one device as systemd portable
services or systemd-nspawn containers. Today, app A has **no way to learn that
app B exists, let alone how to reach it**. There is no discovery layer and no
convention for same-host connectivity.

The narrow question:

> How does an app running on the host find, and open a connection to, another
> app running on the same host — without either app touching the other's data,
> and without breaking the isolation model that is the whole point of the
> platform?

This is two sub-problems that must not be conflated:

1. **Discovery** — "what services exist, and where?" (name resolution, presence,
   port lookup).
2. **Transport** — once you know where, how bytes actually move (loopback TCP,
   Unix socket, D-Bus, etc.).

Several options below conflate the two; one of the session's jobs is to decide
them independently. A common outcome in systems like this is a layered design
(X for discovery, Y for transport), and the proposed direction in §8 follows
that shape.

---

## 3. Constraints

### 3.1 Hard constraints (settled, non-negotiable)

These come from the decision records, the project context, and the prior design session.

| # | Constraint | Origin |
|---|---|---|
| C1 | **No shared volumes.** Apps must never access another app's data directory. This is a security boundary, not a preference. | [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §11.3 |
| C2 | **No weakening of isolation.** Portable services isolate via per-app uids + security profiles; nspawn isolates via PID/mount/network namespaces. Any solution must preserve these. | the project context, design session §11.4 |
| C3 | **Must work for both runtime modes** (`portable` and `nspawn`) declared in `package.yaml`. A solution that only works for one mode is incomplete. | design session §11.4 |
| C4 | **appctl is a CLI, not a daemon.** Any "registration" it does happens as an install/start/stop side-effect, re-applied idempotently at boot by `restore-apps.service`. No long-running appctl process. | the project context |
| C5 | **Offline-first.** No dependency on external DNS, DHCP, or internet. Mechanisms must function on an isolated device. | the project context |
| C6 | **Low power.** No continuous background polling, no multicast churn on the wire, mindful of 512 MB RAM. | the project context |
| C7 | **Read-only rootfs, ephemeral `/etc`.** Persistent state lives in `/data` (or FHS-equivalent bind); `/etc` resets every boot. | the project context, the decision records |
| C8 | **Firewall is nftables**, not iptables. | the decision records |

### 3.1.1 Preliminary ruling on C1 and shared socket directories

> **Ruling ([resolutions 2026-06-16](../conversation/2026-06-16-resolutions.md) §F4):** A shared socket directory at
> `/run/appctl/` is **not** a violation of C1. C1 protects app *data*
> directories — files an app reads/writes as part of its function. A socket
> directory contains IPC endpoints (Unix socket files, not regular files),
> created by appctl, connected to via the kernel. This is analogous to
> `/run/dbus/system_bus_socket` or `/var/run/docker.sock`, which nobody
> considers "shared volumes" in the data isolation sense.
>
> This ruling removes the C1 blocker for options §5.3 (Unix domain sockets)
> and any design that bind-mounts a shared socket directory into nspawn
> containers. The consent model (how app A authorizes app B to connect) is
> still an open question for this session to resolve (Q11).

### 3.2 Derived constraints (follow from the runtime model)

The single most important fact for this design:

> **nspawn supports three network modes** (`package.yaml`: `network: host |
> private | none`). For `private` and `none`, the container has its own network
> namespace and **its own `127.0.0.1`**. Loopback-based transport between a
> host-network app and a private-network app does not work without explicit
> bridging or port forwarding.

See [design session 2026-06-15](../conversation/2026-06-15-design-session.md) lines 644-657 (runtime comparison table) and
620-624 (the `network:` field). This one fact invalidates or complicates several
options below, and any design that does not address it has a hole.

Other derived facts:

- Portable services run as `app<uid>` (uid ≥ 6000), host network by default.
- nspawn containers run as root *inside* the namespace; isolation comes from the
  namespace, not a uid.
- `package.yaml` already declares `ports[]` (`{port, protocol, expose}`). The
  `expose: true` flag currently means "apply an nftables accept rule" — i.e. it
  is about **external** reachability, not inter-app reachability. The session
  must decide whether to overload this field or add a new one.
- Apps already have a lifecycle hook system (`pre_start`, `post_start`, etc.)
  that could participate in registration.

---

## 4. Background: how apps run today

Grounding for the option survey. All of this is from existing specs/designs.

### 4.1 Runtime modes

| | Portable | nspawn |
|---|---|---|
| Isolation | per-app uid + systemd security profile | PID/mount/network namespace |
| Network | host (profile may restrict) | configurable: `host` (default), `private`, `none` |
| User inside service | `app6000` (allocated by appctl) | root (namespace isolates) |
| Storage | `BindPaths=` in drop-in | `Bind=` in `.nspawn` |
| Rehydrate on boot | `portablectl attach` + regenerate drop-in | `systemctl enable systemd-nspawn@<name>` |

### 4.2 Existing service declaration

```yaml
# package.yaml
runtime: portable          # or nspawn
network: host              # nspawn-only; ignored for portable
ports:
  - port: 1883
    protocol: tcp
    expose: true           # currently: nftables accept rule for EXTERNAL access
```

There is **no field today** that says "this service is intended to be consumed
by other apps on this host." `expose` is about the firewall edge, not inter-app
discovery. The session must decide whether discovery reuses `ports[]`, adds a
`provides:`/`consumes:` block, or uses runtime registration.

### 4.3 disco today

`disco` is an implemented daemon (separate repo) providing:

- UDP broadcast protocol for **device-level** peer discovery on the LAN.
- NSS module (`libnss_disco.so.2`) for resolving peer device names without DNS.
- Optional GPS time sync.

Critically, disco knows about **devices**, not **apps**. It has no concept of
"mosquitto is running on port 1883 on this device." Any disco-based approach
(§8) requires extending it or feeding it app-level records.

---

## 5. Options survey

Each option is described, then evaluated against the hard constraints.
"Discovery vs transport" is called out per option because most options only
solve one half.

### 5.1 Loopback networking (IP + port)

**Mechanism.** Apps listen on `127.0.0.1:<port>`; peers connect to
`127.0.0.1:<port>`. No discovery mechanism — the port is assumed known.

**Solves:** transport only.

- Portable mode: works directly (host network).
- nspawn `network: host`: works (shares host loopback).
- nspawn `network: private|none`: **fails.** Container loopback is a different
  namespace; `127.0.0.1:1883` inside the container is not the host's.

**Pros.**
- Zero infrastructure. Uses existing sockets code in every app.
- No new dependencies, no daemon, no files.

**Cons.**
- No discovery. Peers must know ports by out-of-band means.
- Port conflicts: only one listener per port. Requires a reservation scheme
  (which is option 5.2).
- Dead for private-network nspawn apps without port forwarding.

**Constraint check:** C1 ok. C2 ok. **C3 fails** (private/none nspawn). C4-C8 ok.

---

### 5.2 Well-known ports / port reservation

**Mechanism.** appctl reads `ports[]` at install time and reserves each port in
its database (one app per port; conflict = install error). Other apps discover
ports by calling `appctl list` / `appctl info <app>` or by reading the same
metadata. Peers then connect over loopback (5.1).

**Solves:** discovery (static, declared). Transport delegated to loopback.

**Pros.**
- Reuses the existing `ports[]` field — no schema change for the basic case.
- Deterministic: a port, once reserved, is stable for that app's install.
- appctl already owns install lifecycle, so reservation is a natural side-effect.
- Offline, no daemon, no wire traffic.

**Cons.**
- Static: doesn't reflect whether the app is *actually running* and listening.
  A reserved-but-stopped app still "claims" the port.
- Conflict handling is harsh — two apps wanting 1883 cannot coexist. (MQTT and
  a second MQTT-like service is a real scenario.)
- **Inherits 5.1's failure for private-network nspawn.** The port is reserved
  on the host; the private-network container isn't reachable on it.
- "Well-known" only works if ports are fixed. Dynamic allocation (to avoid
  conflicts) breaks the "well-known" property and pushes you back to needing
  real discovery.

**Constraint check:** C1 ok. C2 ok. **C3 fails** (private/none nspawn). C4 ok.
C5-C8 ok.

---

### 5.3 Unix domain sockets

**Mechanism.** Apps create a listening socket at a well-known path, e.g.
`/run/appctl/<name>.sock`. Peers connect to the path.

**Solves:** both discovery (filesystem presence = liveness signal) and
transport.

**Pros.**
- Liveness is implicit: the socket exists iff a listener is bound. No stale
  registrations.
- Filesystem permissions give free ACLs: appctl can set socket owner/group/mode
  to gate which apps may connect (e.g., a per-consumer supplementary group).
- No network namespace involvement — but see the con below.
- Fast, local-only, no port conflicts.

**Cons.**
- **The shared socket directory is a kind of shared volume.** It contains only
  sockets, not data, so it does not violate C1's *intent* — but it does require
  every app to see the same `/run/appctl/`. For portable services this is free
  (shared `/run`). For nspawn it requires bind-mounting the dir into every
  container, which the session must bless as "not a shared data volume."
- **nspawn private/none network is fine for sockets** (they're filesystem, not
  network) — *if* the socket dir is bind-mounted in. This is the one transport
  that can work uniformly across all three nspawn network modes.
- Only fits request/response and stream protocols. An app that exposes a raw
  TCP service (mosquitto, ircd) would need a socket-to-TCP shim. Most existing
  server software does not natively listen on Unix sockets.
- Socket path length limits (`sun_path` ≈ 108 bytes) constrain naming.

**Constraint check:** C1 — *borderline, needs explicit session ruling* (socket
dir is shared but contains no data). C2 ok (perms enforce). **C3 ok** *if*
socket dir is bind-mounted into nspawn containers — the one mode-uniform
transport. C4 ok (appctl creates the dir and perms at install). C5-C8 ok.

---

### 5.4 D-Bus (system bus)

**Mechanism.** Apps expose services on the system bus under well-known names
(e.g., `com.offlinelab.mosquitto`). Peers discover via D-Bus name activation /
`ListNames`, connect via the bus.

**Solves:** discovery (name-based) and transport (D-Bus messages).

**Pros.**
- Built-in service discovery and introspection.
- Mature ACL model (D-Bus policy files).
- Activation: the bus can start the service on first call.

**Cons.**
- **Most server apps do not speak D-Bus.** mosquitto, ircd, httpd, postgres —
  none expose D-Bus. Using D-Bus means writing a per-app adapter service, which
  is a large ongoing burden and a new thing to package.
- **nspawn containers don't see the host bus by default.** Reaching the system
  bus from a container requires bind-mounting `/run/dbus/system_bus_socket` and
  setting `DBUS_SYSTEM_BUS_ADDRESS`, plus policy. Private-network nspawn is
  fine (D-Bus is filesystem-backed), but the bind-mount requirement returns.
- The prior design session explicitly noted "an app needing host D-Bus only
  works as a portable service" — so D-Bus-as-transport pushes every consumer
  toward portable mode, violating the mode-neutrality in C3.
- Heavyweight for a 512 MB Pi Zero. The bus daemon is another always-running
  component.
- Couples the inter-app contract to D-Bus types/marshalling. Fine for control
  planes; awkward for high-throughput data (e.g., streaming).

**Constraint check:** C1 ok. C2 ok. **C3 effectively fails** (nspawn + D-Bus
needs host bus bind-mount and biases toward portable mode). C4 ok. C5-C7 ok.
**C6 strained** (dbus-daemon is a resident service).

---

### 5.5 DNS / service discovery (systemd-resolved, mDNS/DNS-SD)

**Mechanism.** Each app gets a local name (e.g., `mosquitto.local`) or is
advertised via DNS-SD service types (`_mqtt._tcp`). Resolved via systemd-resolved
or avahi.

**Solves:** discovery. Transport delegated to loopback/network.

**Pros.**
- Standard, well-understood model. Tools and libraries already do name lookup.
- Generalizes naturally to cross-device discovery (same mechanism, wider scope).
- DNS-SD service types carry port + metadata, not just names.

**Cons.**
- **mDNS is multicast and chatty.** On a Pi Zero on a power bank, continuous
  multicast traffic conflicts with C6 (low power). avahi-daemon is a resident
  service.
- systemd-resolved is lighter but still a resident daemon, and its mDNS support
  is oriented to the *host*, not per-app services inside containers.
- **nspawn private-network containers are in a different broadcast domain.**
  mDNS does not cross namespaces without a forwarding agent. So this fails the
  same private-network case as loopback.
- Name collisions on `.local` are real and hard to resolve without a central
  authority.
- Overlaps with disco's existing role, risking two parallel discovery systems.

**Constraint check:** C1 ok. C2 ok. **C3 fails** (private/none nspawn). C4 ok.
C5 ok. **C6 strained** (multicast/daemon). C7 ok. C8 orthogonal.

---

### 5.6 Disco-based

**Mechanism.** Extend disco to carry app-level service records in addition to
device records. appctl pushes `{app, port, transport, runtime}` into disco at
start and removes it at stop (idempotent, re-applied by `restore-apps.service`
on boot). Apps query disco — or read appctl state that disco has written — to
find peers.

**Solves:** discovery. Transport delegated to loopback (5.1) or sockets (5.3).

**Pros.**
- Reuses an existing, on-device, offline-native component. Consistent with the
  project's stated direction ("use disco for inter-app service discovery
  eventually").
- disco already has an NSS module and a query path; extending its record type is
  incremental, not greenfield.
- appctl's involvement is pure side-effect (no daemon), satisfying C4.
- Centralizes discovery in one place instead of fragmenting across mDNS + D-Bus
  + files.

**Cons.**
- disco is currently device-level, not app-level. This is real new scope: a new
  record type, a registration API, a query API, and a lifecycle contract between
  appctl and disco.
- Ties app presence to disco's health. If disco is down, discovery is down (apps
  that already know their peers' ports are unaffected — disco is discovery, not
  transport).
- disco is itself a daemon. It is already accepted as a resident service, so
  this doesn't *add* a daemon — but it does raise disco's criticality.
- **nspawn private-network still fails for the transport leg.** disco can tell
  you "mosquitto is on port 1883," but a private-network container still can't
  reach `127.0.0.1:1883`. Disco-based discovery does not solve transport for
  that mode; it must be paired with sockets (5.3) or nspawn port forwarding.

**Constraint check:** C1 ok. C2 ok. C3 — *discovery* ok across modes; *transport*
still needs a separate decision. C4 ok. C5 ok. C6 ok (disco is already running;
no new wire traffic if records ride existing announcements). C7 ok (state in
`/data`). C8 ok.

---

### 5.7 Environment variable injection

**Mechanism.** At install (or start), appctl writes connection facts into peer
apps' environments via drop-ins: `Environment=MOSQUITTO_ADDR=127.0.0.1:1883`.

**Solves:** discovery (declarative, static). Transport delegated to loopback.

**Pros.**
- Trivially simple. No daemon, no query API, no files to parse at runtime.
- Declarative: the wiring is visible in appctl's generated drop-ins.
- Works uniformly for portable (`Environment=` in `.service.d`) and nspawn
  (`Environment=` in `.nspawn`).

**Cons.**
- **Static and stale.** Set at install time; does not update when a peer
  restarts on a new port, is uninstalled, or is down. An env var pointing at a
  stopped app is a silent failure.
- **N-by-N wiring problem.** To wire N apps you must declare each app's peers,
  which means a dependency/relationship declaration in `package.yaml` that does
  not exist today.
- No liveness signal — the var exists whether or not the peer is running.
- Only carries address facts; useless for socket or D-Bus style discovery.
- **Inherits 5.1's private-network failure** for the address it injects.

**Constraint check:** C1 ok. C2 ok. C3 ok for *injection* but the injected
address fails for private-network nspawn. C4 ok. C5-C8 ok.

This is better as a complement to a runtime discovery mechanism (hand off the
common-case wiring to env vars, fall back to live lookup) than as a primary
solution.

---

## 6. Constraint evaluation matrix

| Option | C1 no-shared-volumes | C3 portable | C3 nspawn host | C3 nspawn private/none | C4 no daemon | Discovery | Transport |
|---|---|---|---|---|---|---|---|
| 5.1 Loopback | ok | ok | ok | **fail** | ok | no | yes |
| 5.2 Well-known ports | ok | ok | ok | **fail** | ok | static | via 5.1 |
| 5.3 Unix sockets | *needs ruling* | ok | ok (bind) | ok (bind) | ok | implicit | yes |
| 5.4 D-Bus | ok | ok | needs host-bus bind | ok (bind) | **strains C6** | yes | yes |
| 5.5 DNS/mDNS | ok | ok | ok | **fail** | **strains C6** | yes | via 5.1 |
| 5.6 Disco | ok | ok | ok | discovery ok / transport **fail** | ok | yes | via 5.1/5.3 |
| 5.7 Env vars | ok | ok | ok | address **fail** | ok | static | via 5.1 |

**What the matrix says at a glance:**

- The only transport that works across **all three** nspawn network modes is
  **Unix domain sockets** (5.3), and only if the session rules that a shared
  socket directory is acceptable under C1.
- Every loopback-derived option (5.1, 5.2, 5.5, 5.7) breaks for
  private/none-network nspawn. This is the single biggest fork in the design.
- disco (5.6) is the strongest *discovery* layer but does not solve transport on
  its own.
- No single option satisfies everything. A layered answer is likely.

---

## 7. Open questions the design session must answer

### 7.1 Discovery scope and semantics

- **Q1.** How does a web dashboard app discover that mosquitto is running on
  port 1883? Walk through the concrete flow end to end for the chosen mechanism.
- **Q2.** How does an app declare what it *provides* to other apps, and what it
  *consumes*? Is this declarative in `package.yaml` (a new `provides:`/`consumes:`
  block) or dynamic (registered at runtime), or both?
- **Q3.** Is there a well-known "service registry" — a file, an appctl
  subcommand, a disco query API, or a socket? If a file, where does it live so
  it survives the ephemeral-`/etc` reset (C7)? If an API, who serves it given
  C4 (appctl is not a daemon)?

### 7.2 Lifecycle and liveness

- **Q4.** What happens to connections when an app is updated or restarted? Do
  clients get a clean failure, a stale-connection hang, or a reconnect path?
- **Q5.** How is "this service is actually listening right now" distinguished
  from "this service is installed"? (The gap that makes 5.2 and 5.7 stale.)
- **Q6.** On boot, after `restore-apps.service` rehydrates attachments, what
  re-publishes service records, and in what order, so that an app starting early
  can already see its peers?

### 7.3 nspawn networking — the central problem

- **Q7.** How does nspawn `network: private` and `network: none` participate in
  inter-app communication at all? Options to evaluate:
  (a) declare that private/none-network apps cannot consume or provide inter-app
      services (document the limitation);
  (b) mandate `network: host` for any app that opts into inter-app comms;
  (c) use nspawn `Port=` forwarding per consumed service;
  (d) use Unix sockets bind-mounted into the container (the only mode-uniform
      transport per §6).
- **Q8.** Does the answer to Q7 push the platform toward sockets-as-transport
  even for apps that natively speak TCP? If so, who writes the socket-to-TCP
  shim — the packager, or an appctl-provided sidecar?

### 7.4 Schema and metadata

- **Q9.** Does `ports[].expose` keep its current meaning ("external firewall
  rule") and gain a sibling field for inter-app intent, or does `expose` get
  overloaded? Overloading risks "I want external access" vs "I want other apps
  to reach me" becoming ambiguous.
- **Q10.** Is the discovery contract declarative (package.yaml, static) or
  runtime (registered at start, reflects reality) — and what are the migration
  costs if we pick wrong?

### 7.5 Security and isolation

- **Q11.** If a shared socket directory is permitted under C1, what exactly
  stops app X from connecting to app Y's socket when Y didn't consent? (Supplementary
  groups per consumed service? An explicit ACL file? appctl as gatekeeper?)
- **Q12.** Does inter-app visibility require explicit mutual consent (both
  provider declares and consumer declares), or can any app discover any other?
  The former is safer; the latter is simpler.

### 7.6 Scope boundaries

- **Q13.** Is cross-device app-to-app communication (app on device A reaching
  the same app on device B) in scope, or explicitly out? (This document assumes
  out — see §9 — but the session should confirm, because it changes disco's
  role.)
- **Q14.** Does this design need to support non-TCP transports (e.g., an app
  that only speaks raw UDP, or a database using its own wire protocol), or is
  "TCP and Unix sockets" sufficient for v1?

---

## 8. Proposed starting direction (disco-based, layered) — for reaction, not adoption

Given the project's stated intent to use disco and the analysis above, the
session has a concrete strawman to react to:

**Separate discovery from transport.**

- **Discovery layer: disco, extended with app service records.**
  - appctl writes an app service record into disco on `appctl start` /
    rehydrate, and removes it on `appctl stop` / `appctl remove`. Pure
    side-effect; no appctl daemon (C4).
  - Record carries: app name, transport type (`tcp` / `unix`), address
    (`127.0.0.1:1883` or `/run/appctl/mosquitto.sock`), runtime mode, and a
    liveness flag.
  - Discovery query: an app asks disco (via the existing query path or a small
    CLI) "where is mosquitto?" and gets back the current record. This answers
    Q1 and Q5 together — the record exists iff the app is running.
  - Records persist in `/data` (C7) so they survive reboot; correctness is
    re-established by the rehydrate pass (C4, Q6).

- **Transport layer: loopback TCP by default; Unix sockets where mode-neutrality
  matters.**
  - For portable apps and `network: host` nspawn apps, loopback TCP (5.1) — the
    zero-friction default.
  - For `network: private|none` nspawn apps, fall back to Unix sockets (5.3)
    with the socket dir bind-mounted into the container. This is the only
    mode-uniform transport (§6) and resolves Q7/Q8 without forcing every app
    onto sockets.

- **Declarative wiring (optional complement): env vars** (5.7) generated by
  appctl from a `consumes:` block in `package.yaml`, for the common case where
  a peer's address is stable. Apps that need liveness fall back to the disco
  query. This addresses Q2 and Q10 with "both": declarative for the happy path,
  runtime query for accuracy.

**What this deliberately does not decide (leaves to the session):**

- Whether the shared socket directory is acceptable under C1 (Q11) — if not,
  the private-network nspawn case (Q7) reopens.
- The exact schema additions to `package.yaml` (Q9).
- Whether disco gains a first-class query API or apps read a file disco writes
  (Q3).
- The consent model (Q12).

**Why propose this shape rather than a single mechanism:** the matrix in §6
shows no single option works. The layered shape lets the session argue
discovery and transport independently, and it matches the project's existing
direction (disco) without committing to disco as transport.

---

## 9. Out of scope

- **Remote / cross-device app communication.** Reaching an app on a different
  device is normal IP networking and uses disco's *existing* device-level
  discovery. This design is strictly same-host, app-to-app. (See Q13.)
- **App-internal IPC** (threads, in-process buses). Not a platform concern.
- **Human/operator UI for service browsing.** That is a tooling concern on top
  of whatever discovery mechanism is chosen.
- **Re-litigating C1-C8.** The constraints in §3 are inputs.
- **Changing the runtime modes or network modes themselves.** Those are settled
  in [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §11.4.

---

## 10. Inputs the session should have open

- [design session 2026-06-15](../conversation/2026-06-15-design-session.md) §11.3 (deferral) and §11.4 (runtime modes,
  network modes, the runtime comparison table at lines 644-657).
- `pkg-schema-design.md` §3.3 (`package.yaml` struct, `Port`, `NetworkMode`,
  `Runtime`).
- the decision records — volumes (two-key), per-app user allocation, firewall =
  nftables.
- the disco tool documentation — what disco is today.
- [disco architecture overview](../../docs/disco/architecture-overview.md), [disco NSS module](../../docs/disco/nss.md) — the current record model
  and NSS integration that an app-level extension would build on.

---

## 11. Success criteria for the design session

The session is done when it has produced:

1. A chosen **discovery** mechanism, with the schema/API surface it implies.
2. A chosen **transport** mechanism (which may differ per runtime/network mode).
3. An explicit ruling on the **nspawn private/none-network** case (Q7).
4. An explicit ruling on whether a **shared socket directory** satisfies C1
   (Q11), if sockets are in play.
5. A `package.yaml` delta (new fields or clarified semantics for `expose`/`ports`)
   if the design requires one.
6. A boot/rehydrate ordering answer (Q6).
7. The set of changes this implies for appctl, disco, and the specs, listed as
   tasks.

Anything left as "TBD" after the session should be recorded
as an open question (with the reason it blocked the session).
