# 2026-07-04 — Design session: tools-as-product pivot

Live design session that reframes the whole project and resets the tooling
direction. This record is updated as the session proceeds; it captures decisions
as they are made and flags their impact on existing ADRs. ADRs will be minted
(or superseded) from this log once each area settles.

---

## 1. The pivot

**The tools are the product; the OS is a customer.** Offline Lab OS is a
personal side project and is explicitly *not* the thing being built. What is
being built is a general-purpose, cross-distribution way to package, distribute,
and run services as immutable signed DDI images on *any* systemd host — from a
BMC to a supercomputer — with `docker run` ergonomics and near-zero overhead.

Mission (ratified in-session):

> A way to package any Linux service — Debian, RHEL, Alpine, whatever it was
> built from — into a small, immutable, signed image; carry and share those
> images offline; and run them on any systemd host with a single command, no
> daemon, no layer pulls, and near-zero overhead. Start it, stop it, move on —
> the data stays. Docker's ergonomics and Flatpak's delivery, minus the daemon,
> the bloat, and the isolation tax.

### `buildctl` is killed

The existing `buildctl` implementation is to be removed. Its core mistake was
reimplementing image assembly (squashfs / dm-verity / GPT / PKCS7 in pure Go) —
a job **mkosi and systemd-repart already do better**, since they are built by
the same project that defines the DDI format. buildctl was "three tools in a
coat" (rootfs production + image assembly + repository publishing) and worst at
the one that was already solved.

**Consequence:** we do not assemble images ourselves. Image assembly is
delegated to the best existing tool (mkosi / systemd-repart, run in a container
or build VM on macOS). See §Impact for the ADRs this moots.

## 2. The engine is free; the envelope is ours

systemd provides the entire runtime engine — DDI, dm-verity, PKCS7 signing,
`portablectl`, `systemd-nspawn`, extension images for base+app layering. **We do
not rebuild any of it, and we do not build a rival OS.** Our value is entirely
the *envelope* around the engine:

- a **pleasing build experience** for cross-distro DDI apps (mkosi is powerful
  but bare);
- **offline-first distribution** — carry, cache, share, and *trust* images with
  no internet;
- **easy run/management** — one command up, one command down, state survives.

## 3. The product is a contract, not a set of tools

An ecosystem is defined by its contracts, and there are exactly two:

1. **What a DDI-app *is*** — the format + conventions that make an image a
   runnable, opinionated, trustable app.
2. **What a *distribution* is** — the format of a shareable, cacheable,
   offline collection of apps, and how trust/signing works across it.

The CLIs (`appctl`, a builder, a publisher — names open) are **replaceable
reference implementations** of those contracts. This is why "build on macOS" may
be a Makefile, `docker`, or mkosi-in-docker interchangeably: conformance to the
app contract is what matters, not the tool. The real output of this design
session is those two contracts.

## 4. Runtime model

- Core case is the **light portable service** ("nicer portable services," the
  way Docker was "nicer chroots") — shares the host kernel/network, near-zero
  overhead.
- **Isolation is optional and developer-declared.** The DDI is runtime-agnostic:
  the same image can be run light (`portablectl`) or walled-off (`nspawn`). The
  developer bakes a declared default runtime mode into the app; it travels with
  the image; the operator runs it as shipped. Affirms and reframes
  **ADR-0011** (dual runtime) as a *developer build/ship choice*, not an
  operator toggle.

### Lifecycle & verbs

The run leg is two independent axes, with data orthogonal to both:

- **Cache axis** — `get` (fetch an image into the local cache; passive,
  offline-friendly) ↔ `rm` (drop the image from the cache; data untouched).
  Fills/empties the local library.
- **Run axis** — `up` (activate on demand: attach + wire storage/uid/tmp +
  start the declared units) ↔ `down` (stop, but keep everything). Only this
  axis spends resources — this is what lets one small device hold a large cache
  and run only a few apps at a time.
- **Data** — orthogonal; survives `down` **and `rm`**. Data is sacred: `get` an
  app again after `rm` and its state returns exactly as left. Wiping data is a
  separate, deliberately high-friction, guarded explicit act — never a flag you
  trip over, never a side effect of removing an image.

`get` was chosen over `acquire` deliberately. **CLI ergonomics is a first-class
value: verbs are short and fun to type** (`get`, `up`, `down`), never literal or
ceremonial.

### Composition grammar (confirmed)

A verb moves its own axis; an `--<other>` flag opts into moving the second axis
too. One uniform rule, teachable in a sentence, across all four verbs:

- `up --get` — run it; fetch first if not cached (the `docker run` equivalent)
- `get --up` — fetch it; start it too (prefetch + launch)
- `down --rm` — stop it and drop it from the cache
- `rm --down` — remove it; stop it first if running

### Offline-by-default (locked)

**Only `get` (or an explicit `--get`) may touch the network.** Bare `up` is
strict and offline: if the image is not cached it **fails loudly** ("not cached —
`get` it first") and never silently fetches.

This is an instance of a defining product principle:

> **The tool performs no implicit network I/O, ever. Network happens only on
> explicit request.**

This is the deliberate inverse of Docker (which blocks on a pull when you least
expect it) and is what makes "works on a train / during an outage / off-grid" a
guarantee rather than a hope. The operator is always in control of when the
network is touched.

### The removal ladder (`down` → `rm` → `drop` → wipe)

Getting rid of things escalates in destructiveness; each rung requires a more
explicit act (the "no implicit destruction" principle made physical):

1. `down` — stop the running service. Image, environment, data all intact.
2. `rm` — remove the cached **image**. Environment + data intact; `get` restores
   it exactly.
3. `drop` — **total, irreversible teardown**: image, environment (config, dirs,
   uid/gid) **and data** — all gone, no backsies — behind the loud
   `THIS IS DESTRUCTIVE` confirmation guards. There is deliberately **no**
   "de-provision but keep data" middle state; that split-brain (leftovers after
   a `drop`) is exactly what we refuse.

Because `drop` takes everything, the uid-vs-data ownership tension **disappears**
— there is never preserved-data-with-a-lost-uid, so **ADR-0012**'s allocation
model is no longer under pressure from removal. `drop` on a running/cached app
refuses ("`down` it first") to honor no-surprises.

Backlog (far future, out of scope): `drop --backup` zips the data aside before
obliterating; a future `import` takes such a backup, `get`s the app, allocates a
fresh uid/gid, and chowns the data into place.

## 5. The app contract — five questions

A DDI-app is defined by what it can answer on its own, so the runtime never
guesses:

1. **Who am I?** — stable name + version; unique enough to manage, cache,
   catalog. *Mandatory.*
2. **Can you trust me?** — proof the image is authentic and unmodified, bound to
   a signer, so no compromised image can masquerade as this one. *Mandatory.*
3. **How do I run?** — everything needed to start correctly with one command:
   *which units are activated* on `up`, light vs. isolated, what it needs from
   the host (the "opinion"). *Mandatory.* **This is the gap systemd leaves:**
   `portablectl attach` / DDI mounting only makes the unit files *available* —
   it does not start anything (`systemctl start` is still manual). The app must
   declare which service(s) come up when it is brought up; turning "image
   acquired" into "service running" is precisely what we provide. (Relates to
   ADR-0016 lifecycle hooks — activation is the always-present base case.)
4. **What must survive me?** — config/data that persists across stop/start, host
   moves, and power loss, kept separate from the disposable image. *Mandatory
   (even if "nothing").*
5. **Do I stand on anything?** — alone, or on a shared base image (what makes
   apps tiny). *Optional.*

## 6. Storage & state model (resolved this session)

Resolves the "how much can an operator bend the opinion (#3)?" question:
**a small, fixed set of standardized knobs — storage *location* and *config
contents* — over an otherwise fixed structure.**

### Standardized layout

Every app is given a predefined, identical-on-every-OS storage layout, always
mounted into the image runtime:

```
<root>/apps/<repo-hash>/<appname>/config
<root>/apps/<repo-hash>/<appname>/data
```

- `<root>` is **relocatable** (operator may point it at another disk/location);
  the **structure below it is fixed and identical on every host OS.** The layout
  is defined by *our contract*, not by the host's FHS — required because the
  tools must run on any systemd OS, not just Offline Lab OS.
- `<repo-hash>` namespaces apps by their source repository, so two apps of the
  same name from different repos never collide and data is tied to provenance.
- `config` is the **operator-editable** directory (the one sanctioned override
  surface for the app's opinion).
- `data` is the app's persistent private data.
- Each app also gets its **own `/tmp`** (private, ephemeral).

This evolves the earlier OL-OS-specific `/var/lib/appctl/...` FHS scheme
(**ADR-0005**, `schemas/on-device-state.md`) into a relocatable,
contract-defined layout. Still exactly two persistent targets — affirms
**ADR-0013** (config + data only, no freeform paths).

### Guarantees the runtime must provide

- **Apps cannot access each other's data.** (Affirms ADR-0013 + ADR-0012.)
- **An app cannot mount another app's data as its own.** (Affirms ADR-0013 —
  the two targets are the only reachable mounts; system controls the path.)
- **An app always starts with the same uid+gid**, so start/stop never needs to
  re-`chown` the data. (Affirms ADR-0012's "reinstall reuses original uid";
  adds the explicit gid + no-chown-on-start rationale.)
- **An app only starts when its signature verifies** — a run-time trust gate.
  (Affirms ADR-0002 / ADR-0004 signed-only policy; now also enforced by the run
  tool at start, not only at install.)
- **Each app has its own `/tmp`.** (New; portable-service `PrivateTmp`-style
  isolation. Not previously recorded.)

### Portability consequence (flagged)

On Offline Lab OS these guarantees leaned on the OS (initramfs overlay wipe,
`/data` bind-mounts — ADR-0021). On a **general systemd host we don't control**,
the run tool itself must create the per-app user, set up the mounts, provide the
private `/tmp`, and enforce the isolation — there is no OL-OS machinery doing it.
This is a design constraint for the run leg, not yet a resolved ADR.

## 7. Base images (first-class citizens)

Tiny apps require a shared base: a DDI carrying a common userland (debootstrap /
apt / apk output — e.g. `debian-base`, `alpine-20`) on top of which an app ships
only its own few libraries + binaries as an extension. The runtime layering is
systemd's (`portablectl attach --extension`, extension-release matching) — see
**ADR-0028 / ADR-0029** and `design/layered-images.md`. This session **promotes
base images from an opt-in feature to a first-class part of both contracts.**

- **App contract (question #5, lineage):** an app declares the base it layers on
  — the "mark" — by base *identity* (name + compatibility level), not an exact
  content hash. systemd matches an extension to its base by os-release `ID` +
  `SYSEXT_LEVEL`, so a patched-but-compatible base must keep working without
  rebuilding every app.
- **Distribution contract:** bases are a distinct image *class* in repo and cache
  (**ADR-0008** bases/images split) and may live in a **separate base
  repository** with its own signing key (**ADR-0006 / ADR-0010**). The repo
  separation is organizational; first-class status in the envelope is not.
- **Trust:** every image — base and app — is independently signed (verity +
  signature). The app declares only the base *identity* it needs; at attach the
  runtime verifies the app's signature **and** the base's signature
  independently, then checks compatibility. **An app never vouches for base
  content — the base vouches for itself.** This is what lets a base be
  security-patched and re-signed while existing apps keep matching it by level.

**Lifecycle — falls out of the two locked principles:**

- `get <app>` resolves the **dependency closure**: if the app's base is not
  cached, `get` fetches it too — network, and only under `get`. If the base
  cannot be satisfied, the whole `get` fails loudly; no half-usable app lands in
  the cache.
- `up` **never** fetches a base. A missing base is a loud failure ("base X not
  cached — `get` it"), exactly like a missing app image. (No implicit network.)
- **Bases are not directly user-deletable** — there is no `rm`/`drop` for a base.
  They are dependency-managed infrastructure: fetched as a closure under `get`,
  reclaimable only when **no cached app depends on them** (ref-count zero,
  **ADR-0029**). And unlike Docker, an orphaned base is **kept by default** — on
  a train you may want it for the *next* app you pull from your cache; deleting
  it would need a network `get` you can't do offline. Reclaiming disk is an
  **explicit space-prune**, never automatic. Bases hold no sacred data (they are
  always re-`get`able), so this is safe.

### Base updates & the minor-version guarantee

A base can be updated **without touching the app**, because the app matches by
level (§app-contract). `get` a newer compatible base; on the next `down`+`up`
(or restart) the app attaches the new base and the old one becomes orphaned
(kept until pruned).

The guarantee that a Debian 13.1→13.2 bump won't break the app is **not one we
invent — we inherit it.** The compatibility level *is the base publisher's
ABI-stability promise*, aligned to how that distro actually versions: Debian
stable point releases are ABI-stable by policy, so `debian-base`'s level is the
major (13), and any 13.x satisfies it. A distro without that promise (rolling)
forces its base publisher to bump the level more often. The app trusts the base
publisher's level the same way it trusts the base publisher's signature; a base
that breaks ABI within its declared level is a base-quality bug, bounded by the
base being independently signed and trusted.

This also settles the earlier fork by *requirement*, not preference: "update the
base without rebuilding the app" is **only possible under level-match.** So
level-match is binding; an exact build-base identity, if recorded, can only be
**audit metadata** that never gates the runtime.

### Size: sharing is the strategy (not a storage trick)

Based-apps are tiny; bases are larger. The footprint win comes from **many apps
sharing few bases**, and the levers are policy, not clever block-dedup:

- **Level-match is the single biggest lever** (already chosen): all
  `debian-base:13` apps share **one** cached base that updates in place, instead
  of fragmenting into one base per app/version. Exact-pin would have exploded the
  count — another reason it loses.
- **A small, curated set of official generic bases** (few, minimal, widely
  shareable) that targeting is the path of least resistance in the build tool.
  The fewer/blessed the bases, the higher the share ratio.
- **Fat-app as the deliberate opt-out:** an app that declares no base ships
  self-contained and larger. Based (tiny, shares) vs. fat (standalone) is an
  explicit developer spectrum, not a trap.
- Rejected as premature: block-level dedup / content-chunk stores across opaque
  squashfs DDIs. Over-engineering; the sharing policy captures the win.

### Layering: distro base + optional runtime layer + app (cap 3)

> **Superseded 2026-07-05 (§20): the language/runtime layer is removed.**
> The cap is now **2 — one distro base + the app**. Language variety becomes
> flat base flavors (`debian-python` is a complete base). Rationale in §20.

The stack is capped at **3 layers**, affirming `design/layered-images.md`:

| Layer | Role | Example |
|---|---|---|
| 0 | distro **base** (exactly one) | `debian-base` |
| 1 | optional runtime/language layer (the "+1") | `debian-python` |
| 2 | the app | `myservice` |

"One base" means **one distro base** — you never stack multiple distro bases.
The single permitted intermediate is a runtime/language extension. **No more than
3**: no deeper chains, no dependency hell.

This keeps the layered-dedup size win: the distro base is stored once and shared
by every app and every language layer above it; a language delta is stored once
and shared by every app using it; only the small app delta is per-app.

### Standards alignment: adopt UAPI.4 + UAPI.3 (don't invent a format)

Our extension model already *is* the UAPI.4 Extension Image spec — we adopt it as
the normative substrate rather than inventing our own, which is what keeps "runs
on any systemd host" literally true. Conformance points:

- An app image is a **UAPI.4 sysext**: carries
  `/usr/lib/extension-release.d/extension-release.<name>`, **no `os-release`**
  (the base owns identity). Packaged as a **UAPI.3 signed DDI** (verity + PKCS7),
  which UAPI.4 explicitly defers to.
- Matched by UAPI.4 fields, **exact string match**: `ID=` (must equal the
  base's), `SYSEXT_LEVEL=` (our compatibility level; `VERSION_ID=` only if level
  absent), `ARCHITECTURE=`. Confirms "match by level" == UAPI.4 exact
  `SYSEXT_LEVEL` match — no range semantics.
- Declare **`SYSEXT_SCOPE=portable`** — apps run as portable services; this is
  UAPI.4's scope value for that.
- We do **not** use `ID=_any` for apps (explicit base binding), and **not**
  confext (`/etc`) for config — config is our mutable operator-owned bind-mount,
  not a signed immutable `/etc` extension.
- We are a **stricter subset**: UAPI.4 permits arbitrarily many extensions per
  base; we cap at **two** (an optional runtime layer + the app) — 3 layers total.
  Legal and simpler.

**Two-signature / mix-and-match (affirmed):** base and app are each independent
UAPI.3 DDIs with their own verity+signature. A base signed by *us* and an app
signed by a *third-party developer* attach together, each verified separately —
the "cocktail": anyone builds on our signed bases and ships apps signed with
their own key.

**To write:** a **base-image spec** (first-class in the envelope) defining a base
as "a UAPI.4-matchable base DDI — `os-release` with `ID` + `SYSEXT_LEVEL`,
runtime libs, no unit files, UAPI.3-signed," plus the curated official-base
policy.

**Open:** how few official bases, and who curates them (the ecosystem-policy
decision).

## 8. Impact on existing records

**Affirmed / reframed:** ADR-0001 (DDI format), ADR-0002/0004 (signed-only,
now also a run-time gate), ADR-0011 (dual runtime → developer-declared),
ADR-0012 (per-app uid → + gid, no-chown), ADR-0013 (two targets),
ADR-0021 (reboot-proofing, OL-OS-specific), ADR-0028/0029 (layered images →
the base+app "tiny apps" pillar).

**Likely superseded / moot (buildctl internals — confirm before removing):**
ADR-0018 (skeleton merge), ADR-0019 (BuildResult), ADR-0024 (buildctl pure-Go
macOS — the pure-Go/macOS-native dream is over; build delegates to mkosi/docker
in a container), ADR-0027 (build & signing impl details), and the design notes
`backend-interface.md`, `pkg-schema-design.md`, `specs-ddi-migration.md`,
`packaging-plan.md`.

**Needs new/updated records once settled:**
- Storage layout: relocatable contract-defined `<root>/apps/<repo-hash>/<appname>/{config,data}` + private `/tmp` (updates ADR-0005 + on-device-state, or a new ADR).
- Delegated image assembly (new ADR superseding ADR-0024/0027).
- The two ecosystem contracts (app format + distribution) — design notes.

## 9. Open / next

**Parked (explicitly deferred this session):**

- **The 3-layer cap is an artificial complexity guard, not a fundamental limit.**
  It exists to keep dependency-resolution sane; it may be revisited if a real
  need appears.
- **Cross-layer build-time dependency resolution.** Shipping a language DDI (the
  "+1" layer) is desirable but carries a hard, unsolved problem: *how does an
  app-layer package install dependencies that need the interpreter/toolchain
  living in the language layer?* (e.g. `pip install` for an app whose Python is
  in the layer below.) `layered-images.md` §6.2 sketches the Docker `FROM
  <oci-base>` approach; whether that generalizes is unresolved. Work out later.

**Next threads (untouched):**

- **The distribution contract (contract #2)** — entirely undesigned: where `get`
  fetches from, the offline cache format, how trust travels with an image, how
  `get` discovers which repo serves a named base. This is the other half of the
  ecosystem.
- Define the **app contract** in full (the five questions → concrete answers).
- How the run leg enforces the storage guarantees on a host it does not own.
- Naming of the tools (open).

## 10. State at pause (2026-07-04, ~90% context)

**Decided this session (part 1):** tools-are-the-product / OS-is-a-customer; buildctl
killed; engine (systemd DDI/verity/portablectl/nspawn) is free, envelope is ours;
the product is two contracts (app + distribution) with tools as replaceable
reference implementations; nicer-portable-services core with optional
developer-declared isolation; app = five questions (identity, trust, run-intent,
state, lineage); *attach ≠ up* (activation is ours); the two-axis lifecycle
(`get`/`rm` cache, `up`/`down` run) + total `drop`; the removal ladder;
composition grammar (`--get`/`--up`/`--down`); **no implicit network, no implicit
data loss**; relocatable fixed-structure storage `<root>/apps/<repo-hash>/<app>/{config,data}`
+ private `/tmp`; base images first-class (get-closure, kept-offline,
level-matched, two-signature cocktail); 3-layer cap (base + runtime + app);
**adopt UAPI.4 + UAPI.3 as the format substrate.**

---

## 11. Distribution contract (session continued)

### Defining property

**A repository is a filesystem layout, not a service.** No server-side logic,
ever. Anything that holds or serves files is a repo: an HTTPS directory, a USB
stick, a local folder, an SSH host, another device's cache. Sneakernet is the
same contract as HTTP, not a fallback. (Affirms and hardens the static-file
design of ADR-0008/0009.)

### Addressing (locked)

**`get <repo>/<name>`, always.** No bare names, no hidden default registry —
the deliberate inverse of Docker's silent `docker.io/` prepending. `<repo>` is a
local alias chosen at `repo add`; every publisher can have an `mpd`, and the
operator always sees which one they're getting.

### Versions & retention (locked)

- **Remote repos serve latest only.** `get` always fetches the latest version —
  no exceptions, no downgrade-via-`get`. (Affirms ADR-0008 latest-only, now with
  the offline rationale attached.)
- **Retention is a local policy.** The on-disk layout stores images as
  `<name>/<version>/`, so multiple versions coexist structurally; keeping N
  versions locally is the operator's choice, not the repo's problem. **The
  retention count is end-user configurable** (default: current + previous,
  N=2); pruning beyond N is local housekeeping.
- **Revert is an on-disk operation** — repoint the app at a still-cached older
  version. Never a download.

### Version format (locked)

**Adopt UAPI.10** (Version Format Specification) as the version scheme: `~`
pre-release, `^` post-release, `systemd-analyze compare-versions` as the
reference comparator — already present on every systemd host ("engine is free").
"Latest" in an index = maximum by UAPI.10 ordering. Supersedes the old buildctl
"version must be semver" validation.

### Trust architecture (ratified)

- **Two gates.** *get-gate:* the repo's signed index (index key) + artifact
  hash match governs what enters the cache. *up-gate:* systemd verifies the
  DDI's embedded signature (build key, via `/etc/verity.d/`) before attach.
  Build signatures travel inside the image; repo signatures wrap the catalog.
- **Delegation-by-inclusion.** The repo manifest lists the build certs the repo
  holder accepts; the manifest is signed by the index key. That signed list *is*
  the "sign the image keys with the repo key" the session asked about — no
  per-cert countersignatures needed. Trusting a repo = trusting its curated
  builder set.
- **Repo identity is its index key, not its URL.** The alias binds to a pinned
  key; URLs are just locations of that identity (origin, mirror, stick, a
  friend's cache). Trust publishers, not media.
- **Carrier vs. curator.** A *verbatim mirror* copies files exactly — origin's
  signed index included — and therefore needs no keys and can't tamper.
  *Re-publication* (serving the same DDIs under your own index key) is a new
  repo, i.e. curation; the builders' signatures inside the images still verify
  (the two-signature cocktail). Carriers never re-sign; merging catalogs from
  multiple repos into one index is forbidden — a multi-repo stick is several
  verbatim subtrees side by side, each with its own keys.
- **Presence ≠ authenticity.** A partial mirror (e.g. a cache) may carry the
  full signed index while holding a subset of the files; `get` of an absent
  entry fails loudly. The index promises hashes are authentic, not that files
  are present.
- **Index monotonicity.** Indexes carry a timestamp/counter; a device never
  accepts an index older than the last one it saw for that repo identity
  (anti-rollback/freeze). Already-cached content stays usable.
- **Relative URLs only** inside index/manifest, so the layout is
  location-independent and verbatim mirroring works anywhere (refines
  ADR-0010's same-origin rule).
- **Known limitation (flagged):** `/etc/verity.d/` is a flat trust store — once
  a build cert is installed, any image signed by it passes the up-gate
  regardless of delivering repo. The strong gate is acquisition; the run tool
  additionally records which repo delivered each image and refuses to `up`
  images that bypassed a trusted `get` (state-level, not crypto).

### Authoring vs. carrying

Repo authoring is buildctl's job (see §12) — an explicit ceremony that scaffolds
the layout, generates the index keypair, and writes the signed manifest. Only
the author (index key holder) can change a catalog; everyone else is a carrier.
A device's cache is created by `get`, never by authoring — same layout, no
authoring key.

---

## 12. The build leg (session continued, 2026-07-05)

### buildctl lives (the name, not the code)

The tool keeps the name **buildctl** — "buildctl is dead, long live buildctl."
The codebase is removed; the name still describes the job. **Build and index
tasks stay in one codebase** (easier testing); a `repoctl` split is possible
later but not preferred now.

### Signing is inside `build` (locked)

There is no separate `sign` step and no flag to skip it: **an unsigned image
cannot be produced.** `buildctl build` = backend rootfs → conformant tree →
signed DDI, one motion. A separate sign step would imply unsigned images exist;
they don't, anywhere in the ecosystem.

### buildctl does no distribution transport (locked)

**A repo/index operation is always local.** Publishing to a remote repo host is:
move the files with whatever you like (`scp`, `rsync`, a USB stick), then run
the index task **on that host** against the local directory. buildctl never
ships bytes over the network for distribution — transport is explicitly the
operator's tool of choice. This extends "no implicit network" to its strongest
form (buildctl-side: *no distribution network I/O at all*), matches
"a repository is a filesystem layout," and makes sneakernet publishing identical
to server publishing. It **supersedes ADR-0009's ssh/rsync automation**: the
two-step publish survives conceptually (files first, index second, index key
never leaves the repo host), but the tool no longer automates the transport.
(Build *backends* may fetch during a build — `docker pull`, apt — that is the
backend's business, explicitly invoked by the operator.)

### Command surface (proposed shape)

```
buildctl build [--backend=docker|mkosi] [--key=<build-key>] <dir>
    # rootfs via backend → validated conformant tree → signed DDI + metadata
buildctl index init <dir>
    # authoring ceremony: repo layout + index keypair + signed manifest
buildctl index add <repo-dir> <artifact...>
    # place an artifact INTO the repo at the correct derived path
    # (images/<arch>/<name>/<version>/ from its own metadata), verify its build
    # signature against the manifest's delegation set, update + re-sign index
buildctl index update <repo-dir>
    # full rescan of a local repo dir, update + re-sign the index
    # (repair / bootstrap; latest per UAPI.10)
```

The operator never computes a destination path: `buildctl index add /data/repo
/tmp/hello_1.0.0_arm64.raw` files the artifact correctly — the artifact knows
its own name/version/arch. Hand-copying into the layout is legal (it's just
files) but `add` is the supported, error-proof path.

`index add` is also **where curation trust is enforced**: it verifies the
artifact's build signature against the certs listed in the repo manifest and
refuses unknown builders — accepting a new builder's cert into the manifest is a
separate, explicit act (verb TBD). "Adding an image to your repo is the trust
decision," made mechanical.

**Config file with a repo section.** buildctl gets a per-user config file
(XDG: `~/.config/buildctl/...`) holding a `repo` section: named repo aliases →
local paths, one marked default, plus a default build-key path for `build`.
`index add <artifact...>` with no `--repo` targets the default configured repo;
`--repo=<alias|path>` overrides. Precedence is strict and boring:
**flag > config > loud error** — if nothing is configured and no flag is given,
buildctl errors; it never guesses. (Positional args to `index add` are
artifacts only; the repo always arrives via flag or config — no dir-vs-file
sniffing.) Backend choice stays out of the user config: it belongs to the
project (`package.yaml`), not the user.

`index` is the repo-holder keyword — deliberately distinct from appctl's
device-side `repo add/list` so the two vocabularies never collide.

Publish flow end to end:
`build` → move the artifact anywhere near the repo host (your transport) →
`index add <repo> <artifact>` on that host. Done.

### Q-B5 resolved as a side effect

Index keys need no cert marking (`--index` OID/filename hacks dead): **key roles
are positional in the signed manifest** — the index key is the repo identity;
build certs are the listed delegation set. A cert is just a cert; the manifest
says what it's for.

### Backends (ratified)

**v1 backends: `docker`, `mkosi` (in-container on macOS), and `shell`.** The
`make` backend is cut — shell subsumes it: if you have `build.sh`, you can call
`make` from it. The shell contract stays the old, proven one: buildctl invokes
`build.sh <outDir>` and the script populates the rootfs tree.

The backend is **never guessed** — declared in `package.yaml` or given as
`--backend`; marker-file auto-detection dies (explicit over implicit: a Docker
project with an incidental Makefile must never surprise-build the wrong way).

### `index init` — the authoring ceremony (ratified)

The repo-authoring ceremony is **explicit**: `buildctl index init <dir>`
scaffolds the layout, generates the index keypair, writes the signed manifest.
No auto-scaffold or silent keygen on first `add` — an identity key coming into
existence as a side effect is exactly the magic this session kills.

`repo create` was considered and rejected for vocabulary hygiene. The rule
first adopted here ("authors speak `index`, consumers speak `repo`") was
**superseded minutes later by §13**: one noun (`index`) ecosystem-wide, with
verbs carrying the role.

## 13. Terminology: "index" replaces "repo" ecosystem-wide (ratified)

There is no "repo" anywhere in the ecosystem. The thing formerly called a
repository is **an index**: a collection of images from whoever, *indexed* — a
signed catalog plus the payload files it vouches for. The name follows the
essence the trust architecture already established: identity = the index key,
trust = the index signature, "latest" = an index entry, presence ≠ authenticity
(files are payload; the index is the authority).

**One noun, role carried by verbs:**

- buildctl (author): `index init` (ceremony), `index add <artifact>` (curate),
  `index update` (rescan/re-sign).
- appctl (consumer): `index trust <url|path>` — the explicit trust ceremony,
  named for what it actually does (pins the index key; replaces the old
  `repo add`) — plus `index list` and `index drop <alias>` (untrust).
  **`index drop` refuses while any app from that index is still provisioned**
  ("drop those apps first"); once none remain it is non-destructive by
  construction — unpin key, remove alias + cached subtree, everything
  re-gettable after a future re-trust. Destructiveness lives at exactly one
  altitude: the app. An index drop can never be a backdoor data wipe.
- Addressing: `get <index-alias>/<name>`.
- Storage namespacing: `<root>/apps/<index-hash>/...` where the hash is the
  **index-key fingerprint** — naming now aligns with identity.
- A device cache = verbatim partial copies of trusted indexes + payload.
- A stick can carry several indexes side by side (never merged).

**Precision rule** (the one cost, handled): "the index" names the whole
published thing (catalog + payload); "the index *file*" names the signed
document itself, when the distinction matters.

---

## 14. Run-leg guarantees on foreign hosts (ratified)

### The reframe: the foreign host is the *easy* case

§6 flagged that on a host we don't control, appctl must deliver the guarantees
itself "because there is no OL-OS machinery." Working it through inverts the
picture: **the boring persistent systemd host is the base case the tool is
designed for; OL OS is the weird customer** (ephemeral `/etc`, overlay wipe)
that uses its own machinery (bind-mounts from `/data`, restore service —
ADR-0021) to *look like* a boring persistent host. appctl itself knows nothing
about overlay wipes. Reboot-proofing becomes an OS-side conformance concern,
not an appctl feature.

### The host contract

What appctl requires of any host — and nothing more:

- systemd ≥ 250 built with OpenSSL (≥ 254 for layered apps) — ADR-0003/0028.
- `portablectl` (and `systemd-nspawn` for isolation-mode apps).
- Root privilege for state-changing verbs.
- A writable, persistent `<root>` (default `/var/lib/appctl`, relocatable).

Checked by an explicit preflight (**`appctl doctor`**): reports exactly what the
host is missing, never fixes anything silently. Cheap subset re-checked on `up`.

### Guarantee → mechanism (every mechanism is stock systemd/Unix)

| Guarantee (§6) | Mechanism on any systemd host |
|---|---|
| Apps can't read each other's data | Per-app uid + `0700` app dirs — plain Unix perms |
| App can't mount another app's data | **Two gates on units:** buildctl conformance validation rejects shipped units declaring host mounts (extends the no-`User=` rule); appctl re-validates at `up` and refuses loudly. Only appctl's generated drop-in ever grants `BindPaths=` |
| Same uid+gid every start, no re-chown | appctl allocates once, records in its state (file-per-record, ADR-0026), writes a `sysusers.d` snippet; `/etc` persists on normal hosts so it sticks |
| Starts only if signature verifies | Certs installed into `/etc/verity.d/` at `index trust`; drop-in pins `RootImagePolicy=signed:=absent` — **systemd re-verifies at every start**, not only at install (ADR-0002/0004) |
| Private `/tmp` | `PrivateTmp=yes` in the drop-in |
| Power-cut resume | `systemctl enable` + persistent `/etc`: the host comes back up and so do the apps that were `up`. No restore daemon needed on normal hosts (OL OS re-derives via its own machinery) |

### The drop-in is the keystone

appctl's entire runtime authority is one generated drop-in per app:
`User=`/`Group=`, `BindPaths=` to exactly `{config,data}`, `PrivateTmp=`,
`*ImagePolicy=`, runtime-mode specifics. **The image ships intent (the unit);
the host ships placement (the drop-in).** Developer owns the unit; appctl owns
the drop-in; neither touches the other's file. This is ADR-0015's reason
restated as the central design seam of the run leg.

### Ratified rulings (this turn)

- **OL-OS specifics leave the tools entirely.** All persistence/wipe/RO-rootfs
  machinery is the operating system's job; the tools carry **no reservations
  for OL OS**. The OS-side duty list lives at the umbrella root:
  `offline-lab/OS-CONFORMANCE.md` (host contract, `/etc` artifacts to persist
  or replay, restore machinery, `/data` wiring, firewall question, uid-range
  ownership).
- **uid allocation: error on clash, never work around.** Configurable base
  range in the appctl config (default 6000+), monotonic never-reuse; if the
  next uid is occupied by a foreign user, appctl **errors loudly** and tells
  the operator to configure a different range. No silent skipping (stricter
  than the proposed skip-occupied; refines ADR-0012).
- **Privilege model: bounded by systemd.** `portablectl`/`systemctl`
  state-changes go through D-Bus + polkit, so state-changing verbs effectively
  need root (or polkit rules). We don't fight it: read verbs run unprivileged;
  for non-root operation we *document* a pattern (an `appctl` group +
  sudoers/polkit snippet, like the `docker` group) rather than build one.
- **`doctor` = an extendable rule set** (brew-doctor style): start simple
  (systemd version/OpenSSL, portablectl present, root/privilege path, writable
  `<root>`, uid-range sanity), grow rules as reasons to yell accumulate (e.g.
  "appctl group exists" once the sudoers pattern is documented). Cheap subset
  re-checked on `up`.

### `appctl recover` (added, ratified)

**An idempotent reconcile verb: re-derive every generated artifact from
persistent state.** For each recorded app whose images + config/data persist
but whose generated environment is gone (sysusers snippet, verity.d certs,
attachment + drop-in, enable state), `recover` recreates it — with the
**recorded** uid/gid, so data ownership is correct without a chown — and
brings back `up` whatever was recorded as up. On a healthy host it's a no-op,
so it's safe to run at every boot.

This resolves the OS-CONFORMANCE "restore-vs-reconcile" question in favor of
the generic verb: a read-only OS (OL OS or any other) ships a trivial boot
unit that runs `appctl recover`; appctl still knows nothing about overlay
wipes. Not an OL-OS reservation — a friendly generic verb for every RO/wiped
host and for disaster repair generally.

Boundary: `recover` requires the state records (they live on the persistent
volume next to the data). Data *without* state records is the far-future
`import` case (T71), not recover's job.

**Deferred (confirmed):** `appctl compose` — multi-app groups that work
together — stays post-v1 (already tracked as T53).

---

## 15. Sweep executed (2026-07-05)

This session was distilled into **ADR-0030…0036** (see `decisions/README.md`),
and the corpus was reconciled:

- Superseded: ADR-0024, ADR-0027 (by 0031). Deprecated: ADR-0018, ADR-0019.
- Amended (status notes added): ADR-0001, 0005, 0008, 0009, 0010, 0011, 0012,
  0021, 0028, 0029.
- Design notes bannered: `backend-interface.md`, `pkg-schema-design.md`,
  `packaging-plan.md`, `specs-ddi-migration.md`, `layered-images.md`.
- Specs bannered: `build.md`, `repository.md`, `package-format.md`,
  `security-model.md`, `lifecycle.md`, `reboot-proofing.md`,
  `user-allocation.md`, `sysext.md`, `schemas/on-device-state.md`.
- CLI pages rewritten to the designed surfaces: `docs/cli/buildctl.md`,
  `docs/cli/appctl.md`; per-tool sections (`docs/buildctl/`, `docs/appctl/`)
  bannered.
- Umbrella: `OS-CONFORMANCE.md` created; `OPEN-QUESTIONS.md` statuses updated
  (Q-B5/Q-C1/Q-A5 resolved, Q-A1 OS-side, Q-C2–C4 folded into contract
  homework); `DESIGN-SESSION-HANDOVER.md` marked completed with fork
  dispositions; T70/T71 added to `BACKLOG.md`.

**Remaining homework (unchanged):** write the two contract specs (app +
index) from this record; rewrite the bannered specs against them; rework the
JSON schemas; base-image spec; sysext spec (Q-C5); base curation policy;
cross-layer build deps (parked).

---

## 16. UAPI family audit (2026-07-05, **ratified** — folded into ADR-0034)

> Ratification note: the UAPI.9 inside-view raised an RO-filesystem concern,
> resolved in discussion — the mounts are per-unit namespace bind mounts
> (nothing writes to host or image `/etc`), and the image must ship the empty
> mount-point dirs (`/etc/<name>/`, `/var/lib/<name>/`), created by buildctl
> at build time (a mount point cannot be created on a read-only squashfs).
> On OL OS, `recover` + the `<root>` bind-mount cover the host side.

---

## 17. App-contract drafting rulings (2026-07-05)

The app contract was drafted (`docs/specs/app-contract.md`, T93). Rulings made
during review:

- **Activation is `<name>.service` / `<name>.socket`; no activation-list
  field.** Additional execution comes from the `lifecycle:` hooks and
  systemd-wired oneshots. *(An earlier wording of this bullet asserted my own
  incorrect hook framing; corrected — the hook model was then redesigned in
  §18.)* `stack:` stays as the lineage field.
- **`expose`/`devices`/`resources` are core, not cut.** Device access and
  port declarations are essential to the ecosystem; their concrete definition
  (device-class → `/dev` mapping — revives Q-A4 — and expose semantics vs the
  OS-side firewall) is scheduled up-front as **T101**. The schema work (T95)
  blocks on T101 for these fields only.
- **Manifest is YAML only.** `package.json` dropped: JSON is comment-hostile,
  and JSON is valid YAML anyway.

---

## 18. Lifecycle hooks redesign (2026-07-05, ratified)

The hook model is redesigned, not just re-anchored. Rulings:

- **Hooks stay, strengthened — this is a partial redesign, not a trim.**
  Rationale (operator): hooks serve a wide range — copy files, run
  migrations, run tasks before the main job, chown a socket, and corner
  cases like starting side software from the same image (a worker beside a
  webservice). These units are not started by portablectl/nspawn, so the
  runtime rolls its own start mechanism. Killing or shrinking hooks would
  push developers into unmaintainable bash without systemd's error
  handling. "If someone wants to run 15 jobs before the main task, that is
  the dev's choice and we should provide it."
- **Each stage is an ordered list of unit files** (was: one unit per hook).
  Amends ADR-0016; the explicit-or-absent principle is unchanged.
- **Stage set (ratified):** `pre_start` / `post_start` fire on **every
  `up`**; `pre_stop` / `post_stop` on every `down`; `pre_drop` before
  teardown. Upgrade stages (`pre_upgrade`/`post_upgrade`) are defined with
  the upgrade design (T103). No verb-anchored renaming ceremony — the
  familiar `pre_/post_` names stay (rename-for-its-own-sake rejected as
  slop).
- **Idempotency lives in the units, not the tool:** hooks fire every time
  their stage fires; one-time behavior is the unit's own
  `ConditionPathExists=`-style guard. Consequently **`recover` replays hooks
  like a normal `up`** — the condition guards make it safe — which requires
  storage mounts to be in place before recover runs (already the OS-side
  ordering: `<root>` mounts, then recover).
- **Failure semantics (stricter than the old spec):** a failing pre-stage
  hook **aborts its verb loudly**; `--force` skips. Replaces the old
  "pre_remove failure is ignored" rule — consistent with the guarded-force
  grammar.
- Systemd-wired oneshots inside the image remain available and preferred for
  pure ordering concerns; hooks are the runtime-invoked stages.
- **Env-var set ratified in the T98 rewrite (2026-07-05):** keep `APP_NAME`,
  `APP_VERSION`, `APP_CONFIG_DIR`, `APP_DATA_DIR`; **drop** `APP_FIRST_RUN`
  (condition guards replace it) and `APP_PREV_VERSION` (moves to T103's
  upgrade stages). Also routed to T103: the storage-layout tension between
  ADR-0020 (uuid-keyed image dirs) and the ADR-0037 local collection
  (`<name>/<version>/` index layout) — entangled with retention/revert/vpick.

## 19. systemd research digest (2026-07-05) + parked design debt

Operator-directed reading of 0pointer.net (v256–v261 stories, Amutable) to
find usable engine features. Finds:

- **`systemd-vpick` / `.v/` directories (v256):** `RootImage=`,
  `ExtensionImages=`, nspawn and portabled natively resolve a `<name>.raw.v/`
  directory to the newest contained version — **UAPI.10 ordering over our
  exact `<name>_<version>_<arch>` filename convention**, with arch filtering
  and optional try-counters (`+LEFT-DONE`, A/B-style fallback).
- **Portabled image pinning (v260) + `portablectl reattach` (v248):** v260
  portabled pins the attached image (unchangeable without explicit
  reattach) — upstream's own endorsement of pin-by-default; `reattach`
  swaps with restart-not-stop and preserves the fd store; old↔new matched by
  the name before the first `_` (our convention, again).
- **`.mstack/` mount stacks (v260):** a directory *is* a declared layer
  stack (`layer@0.raw → base.raw`, symlinks into a store, optional writable
  top), consumed by `RootMStack=`, nspawn `--mstack=`, `mount -t mstack`;
  `importctl pull-oci` lands OCI images as mstacks. Candidate future shape
  for the layered-app runtime view (upgrade = repoint a symlink); verity /
  ImagePolicy semantics and portable-profile fit **must be verified** before
  adoption (T103).
- **Unprivileged portable services (v260):** portabled runs as a user
  service (`portablectl --user`) on fresh kernels — future softening of the
  root-only privilege model; `doctor` rule candidate.
- Minor: v258 factory-reset rework + `systemctl reload` reloads confexts
  (OS/boxctl side); **Amutable** = new company by the systemd founder (Jan
  2026, image-based verified Linux) — strategic neighborhood awareness.
- Proposed and pending: the **runtime view as engine-native symlink farms**
  (`.v/` for fat apps, `.mstack/` for layered) materialized over the
  verbatim cache — carrier-pure cache, `ls`-inspectable runtime state.
  Decide within T103.

**Parked design debt (operator, 2026-07-05):** three "will become an issue"
items tracked as tasks — **T102 secrets** (signed public images can never
contain secrets; systemd-creds/`LoadCredentialEncrypted=` candidates),
**T103 upgrading images** (the digest above), **T101 `/dev` device access**
(bluetooth/video/audio — already scheduled). Plus **T104 unit-file
validation in buildctl** and **T105 CLI tools shipped separately from the OS
image** (see TODO).

---

## 20. Index-contract review rulings (2026-07-05)

Rulings from the T94 review:

### The language layer is killed (cap: base + app)

The 3-layer ruling (§base-layering) is **amended: max 2 layers — one distro
base + the app.** Language/runtime variety becomes **flat base flavors**
(`debian-python` = distro *plus* interpreter, a complete base, not a layer).
"We can always add it later; for now it reduces complexity to go without."

Rationale (operator + discussion):

- The OCI-twin build pattern means two artifacts *promised* identical —
  slight docker↔DDI drift is the worst kind of bug (small differences debug
  harder than large ones), and docker offers no real way to extract a single
  layer from a manifest. Simple things were getting hard.
- Size doesn't justify it: a language interpreter is MBs, not GBs.
- v260 `.mstack` keeps this reversible: a future flavor could become a
  two-layer stack behind the same name without apps noticing.
- **The additivity/overlap gate stays regardless** (recommended, not
  vetoed): at build, intersect the app layer's file list with the base's;
  any overlap is a build error — turns UAPI.4's unenforced "extensions
  should be additive" into a hard conformance rule (T104 family).

Amends: ADR-0028/0034 cap notes, app contract §5, `layered-images.md`.
Terminology confirmed: **`apps/` = functional images devs ship**; the other
class is `bases/`.

### The `.zip` transport bundle is killed

The DDI's payload is already compressed (zstd squashfs / erofs inside the
GPT image); zipping re-compresses for a few percent. Transport is the
operator's tool; anyone squeezing a slow link can compress the file
themselves.

### Catalog anti-rollback: two cross-checked fields

Per ADR-0033 monotonicity, each signed catalog/manifest carries **two
fields that must always move together**:

- a monotonically increasing **generation number** (human-readable counter;
  the operator called it "version" — named `generation` in the contract to
  avoid clashing with app/spec versions), and
- a **build timestamp** (unixtime, set when the catalog is signed).

Consistency rules (any disagreement = "iffy, bail out"):

- equal generation but different timestamp → **refuse** (two different
  catalogs claiming the same generation);
- newer generation with older timestamp → **refuse**;
- older generation with newer timestamp → **refuse**.

A consumer remembers the highest consistent pair per index identity and
refuses anything older. Open: whether a loud `--force`-class override may
accept a *stale* (older-than-watermark) catalog in offline corner cases —
under discussion; no separate "publish time" field (signing *is*
publishing — the index is files).

---

## 21. Index-contract discussion, round 2 (2026-07-05)

### Ruled

- **Field naming:** the index file carries `version` (monotonic index
  version — the "generation" name is rejected as an inconvenient way to say
  VERSION) + a publish timestamp (unixtime, set at signing; the
  cross-check/bail rules of §20 apply to this pair). **Per entry:
  `added_at`** — when the DDI was published into this index. Two signing
  moments exist and are both tracked: the DDI is signed at *build*, the
  index at *publish* (adding a DDI to an index *is* publishing). The DDI's
  own build time lives in the DDI metadata.
- **An app's `version` is the DDI version the developer assigns.** The
  version of the software *inside* is deliberately untracked — downgrading
  the inner software still bumps the DDI version. (Visibility of inner
  versions parked as T106.)
- **Search:** index-file-only text matching, confirmed against precedent
  (apt `Packages`, helm `index.yaml`, brew — all local matching, none fetch
  per-package data). Entries carry `name` + `description`. **Freeform tags
  rejected** (10k-label sprawl); at most one optional `category` from a
  small predefined curated list (Debian-Sections-style). Results shown per
  index alias (`offline-lab/mosquitto 2.0.18` vs `franks-lab/mosquitto
  2.1.0`).
- **`stack:` is reserved for the future compose feature** (multi-app stacks,
  T53). The lineage field is **`base:`** (single object: `name` +
  `sysext_level`).
- **"Sidecar" is banned.** The term is **DDI metadata** — an essential part
  of the package format (without it an app cannot run), not a second-grade
  attachment. (Kubernetes-world confusion.)

### Positions stated — model under discussion, NOT yet confirmed

- **Trust was never the index signature's job.** "Trust should be at the app
  author, not the index itself" — an index is just a collection of DDIs
  anyone can copy into; the index *file* exists for discovery and version
  tracking; **trust rides the image's build signature**. Index signing =
  integrity/anti-freeze, and (locally) the curator's own statement.
  (This demotes ADR-0033's delegation-by-inclusion from trust-root to
  cert-distribution channel — rewrite pending confirmation.)
- **Sticks:** one may build an index *on* a stick (by signing one for it),
  or copy DDIs off a stick into one's own local index. Copying whole index
  trees verbatim ("cp is a cute idea") is doubted — partial copies open
  cans of worms; leaning: **copy DDIs, sign your own local index**.
- **Indexing/searching should move to its own tool**, distinct from appctl
  and buildctl ("it's a different thing than what either does") — would
  reverse the earlier build+index one-codebase preference; implications
  under discussion.
- **Single-file package** (kill the standalone metadata file; extract the
  ADR-0017 embedded manifest at index time): direction attractive, but
  operator flagged a **chicken-and-egg concern** — the DDI must be verified
  before its embedded `package.yaml` may be read, yet the metadata seems
  needed to process the package. Execution-order walkthrough owed; under
  discussion.

### Parked

- **T106** — inner-software-version visibility (SBOM-ish?) without
  becoming overhead. "We're not a single-binary delivery mechanism… talk
  more about this later."

---

## 22. Distribution model confirmed (2026-07-05) → ADR-0037/0038/0039

### Confirmed

- **"DDIs carry trust; indexes carry discovery"** — the subscribe + import
  model is ratified (→ **ADR-0037**, amending ADR-0033). Subscribe = a
  signed index at any location; its signature buys *catalog integrity + the
  version/timestamp anti-freeze pair, never trust*. Import = raw DDIs from
  anywhere, each verified by its build signature against accepted certs,
  added to one's own index. Carrier-vs-curator, never-merge,
  presence≠authenticity, and the stale-catalog `--force` question are all
  dissolved/mooted by the model.
- **No chicken-and-egg** in the single-file package: verification is
  metadata-free by DPS construction (GPT type UUIDs → signature vs trust
  store → verity → only then read content). The **single-file package is
  ratified** (→ **ADR-0038**): the standalone DDI-metadata `.json` dies; the
  ADR-0017 embedded manifest becomes *the* manifest, extracted at
  `index add` time post-verification; the index carries the read-optimized
  projection (search never touches DDIs).
- **Every index is always signed.** The "local vs shared" distinction is
  illusory: an index lives on a disk, and a disk can be a USB drive moved to
  another computer — at which point it *is* an external index. No
  sign-on-share laziness; the collection key is created at an explicit
  collection-init ceremony.
- **Tool split ratified** (→ **ADR-0039**, reversing ADR-0031's one-codebase
  preference): **buildctl builds DDIs; appctl runs DDIs; a third (unnamed)
  tool manages getting DDIs onto the system** (indexing, subscriptions,
  import, search). Shared schema/DDI-reading code becomes a common module.

### Open / parked from this round

- **The third tool's name** — parked. "indexctl" felt opaque; possibly the
  *index* noun itself deserves a better name. Revisit.
- **Verb-boundary detail:** `up --get` composition now crosses tool
  boundaries (acquisition belongs to the third tool) — does appctl shell
  out, or does the composition flag die? Undecided.
- **OL OS ships the tools as their own sysext DDI** with the project cert
  baked into the host OS for first trust — so tool updates never require a
  RAUC image rebuild. OS-side concern, not a tools concern (T105 refined;
  OS-CONFORMANCE updated).

---

## 23. One binary (2026-07-05) → ADR-0040

**Ratified: the three Go tools become one binary** with one namespace per
leg (build / index / lifecycle); ADR-0039's separation survives as
namespaces and package layout. **The name is parked — deliberately not
chosen now** ("it's not important now"); until it lands, "buildctl" and
"appctl" are working titles for the namespaces. **`boxctl` and the bash
framework are not part of this setup at all** — they are operating-system
components (a completely different CLI belonging to OL OS), outside the
product's three legs.

Why the old monolith rejection no longer holds (all three premises
dissolved): the CGO_ENABLED conflict died with the pure-Go pipeline
(ADR-0031); cross-compiling one CGO-free codebase to macOS + arm64 is
trivial; Docker/portablectl are runtime deps of individual verbs, not the
binary. New forces for bundling: shared on-device state + local index
(two binaries over one state = version-skew bugs), the `up --get`
cross-tool composition (now resolved naturally), T105's single sysext, the
one-person release train, and the dissolved "indexctl" naming problem.
Accepted cost: one ~15–25 MB static binary on the smallest targets
(replaces three; device-slim build-tag variant possible later); leg
discipline enforced by convention instead of binary walls.
`rejected/monolithic-cli.md` carries the reversal note.

---

## 24. Schema-review rulings (2026-07-06)

From the T95 review:

- **`spec_version` is major.minor** ("some semver here: major and minor
  changes in the spec version") — current `"1.0"`, minor = compatible
  additions, major = breaking. Applies to the manifest and both index
  documents. Optional in the manifest (defaults `1.0`).
- **`category` is killed entirely** — "I don't see how we add any value
  using categories." Amends §21 (which had kept one optional predefined
  category); search is `name` + `description` text matching, nothing else.
  Index-contract open item 5 (curating the list) dissolves.
- **`sbom_url` stays** (optional pointer; relates to parked T106).
- **Hook units may also be `.mount` / `.automount`** (operator addition to
  the suffix set).
- **No committed test keys/certs, ever** (T100 ruling): tests **regenerate**
  keys and certs at runtime — dummy cryptographic material in the repo
  "will break every security linter possible."

Reviewed the rest of the UAPI family (UAPI.8 package-metadata ELF notes,
UAPI.9 file-system hierarchy, UAPI.11 verification-of-OS-artifacts hierarchy,
OSC-3008 context signalling) plus libeconf / the Configuration Files spec.
Findings:

### UAPI.11 (VOA) — the missing link for trust-material storage

VOA standardizes where verifier certs/keys live:
`$os/$purpose/$context/$technology/` under `/etc/voa/`, `/run/voa/`,
`/usr/share/voa/`. Its standard purposes map **1:1 onto our two gates**:
`repository-metadata` = index keys (get-gate), `image` = build certs
(up-gate); `trust-anchor-$role` separation matches delegation (pinned index
key = trust anchor; delegated build certs = verifiers). Crucially, the
**`$context` level provides per-index trust scoping** — the upstream answer to
ADR-0033's flat-`verity.d` caveat.

**Adopt in two steps:** (a) *now* — appctl stores its own trust material
(pinned index keys, per-index delegated certs) in VOA layout instead of an
invented state shape; the get-gate consumer is our code. (b) *later* — the
up-gate still requires `/etc/verity.d/` today (that is what systemd consumes);
track upstream VOA adoption and migrate when systemd's image verification
reads VOA. The flat-store caveat stands until (b).

### UAPI.9 (file-system hierarchy) — the *inside-the-image* half of storage

ADR-0035 defined the host side (`<root>/apps/<index-hash>/<app>/{config,data}`)
but never pinned where those land **inside** the app. UAPI.9 answers it:
**outside = our contract, inside = UAPI.9** — config → `/etc/<name>/`, data →
`/var/lib/<name>/` (the `StateDirectory=`/`ConfigurationDirectory=`
conventions). Also adopted from it:

- **Config seeding gets a standard source:** apps ship pristine defaults at
  `/usr/share/factory/etc/<name>/`; on first provision appctl seeds the config
  volume from there (previously "seed from the image", location undefined).
- **Two volume keys are confirmed sufficient:** UAPI.9's cache dir is defined
  as safe-to-flush (→ ephemeral, no persistence key needed) and logs go to
  journald. No third key.

### Configuration Files spec / libeconf — adopt the convention, not the library

Our tools' own config (appctl/buildctl) follows the vendor-defaults +
`/etc` override + drop-in + `/dev/null`-masking model (Go implementation of
the spec's semantics; libeconf is the C reference, not a dependency). For
*apps*, econf-style lookup is **recommended guidance**: vendor defaults baked
in the image (`/usr/`), operator overrides via our config mount — key-level
drop-ins for free.

### UAPI.8 (ELF package notes) — optional authoring guidance only

`.note.package` (`--package-metadata=` linker flag) makes crashes on any host
attribute the binary to app/version via systemd-coredump. Not architecture:
a recommended practice in the app-authoring docs/templates for compiled apps.

### OSC-3008 — free from the engine

Context signalling is emitted by systemd/nspawn/run0 natively; nspawn-mode
apps get terminal provenance for free. Nothing to build; revisit only if an
`appctl exec` ships (T54).

**Knock-on renames for the reconciliation sweep:** `repository.json` → an
index manifest name (TBD), `docs/specs/repository.md`, ADR-0008/0009/0010
language, and every "repo" in earlier sections of this record — where earlier
sections of this log say "repo," read "index."
