# The Index Contract

**Status:** draft (2026-07-05), distilled from
[ADR-0033](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0033-index-terminology-trust-architecture.md)
as amended by **[ADR-0037](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0037-ddis-carry-trust-indexes-carry-discovery.md)**
(subscribe + import) and **[ADR-0038](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0038-single-file-package.md)**
(single-file package), plus ADR-0031/0034/0039 and the
[2026-07-04 design session](https://github.com/offline-lab/documentation/blob/main/decisions/conversation/2026-07-04-design-session.md)
(§11, §13, §16, §20–22). This is **contract #2** of the ecosystem: what a
shareable, cacheable, offline collection of apps *is*, and how trust travels
with it. Contract #1 is the [App contract](app-contract.md). The governing
principle:

> **DDIs carry trust. Indexes carry discovery.**

Naming of files and directories below is **proposed** — see Open items.

---

## What an index is

An **index** is a signed catalog plus the payload files it vouches for — a
collection of images from whoever, *indexed*. There is no "repository" in
this ecosystem.

- **An index is a filesystem layout, not a service.** Anything that holds or
  serves files is one: an HTTPS directory, a USB stick, a local folder, an
  SSH host, another device's cache. Sneakernet is the same contract as HTTP.
- **Identity is the index key, not the URL.** The signing key *is* the
  index; URLs are just locations of it. The same index may exist at many
  locations (origin server, mirror, stick, a friend's cache) — all equally
  authentic.
- **Precision rule:** "the index" names the whole published thing (catalog +
  payload); "the index *file*" names a signed catalog document, when the
  distinction matters.

## Layout (proposed)

```
<index-root>/
  index.json                  ← the manifest: identity, classes, delegation
  index.json.p7s              ← signature by the index key
  keys/
    <fingerprint>.crt         ← index cert + delegated build certs (PEM)
  apps/
    <arch>/
      catalog.json            ← per-arch app catalog (latest only)
      catalog.json.p7s
      <name>/<version>/
        <name>_<version>_<arch>.raw   ← the package: ONE file (ADR-0038)
  bases/
    <arch>/
      catalog.json
      catalog.json.p7s
      <name>/<version>/...
```

**A package is a single `.raw`** (ADR-0038): its metadata is the embedded
manifest, extracted at `add` time strictly after verification. There is no
standalone metadata file and no `.zip`.

- **Two artifact classes:** `apps/` and `bases/` (ADR-0008, layered design).
  An index may serve either or both; the manifest declares which.
- **All references inside the index are relative paths.** Never absolute
  URLs — this is what makes a verbatim copy work at any address (refines
  ADR-0010; the same-origin property becomes structural).
- Versions coexist structurally (`<name>/<version>/`); the **catalog names
  exactly one latest per name** (UAPI.10 maximum). Retention of old version
  directories is the index holder's housekeeping, not contract.
- Artifact naming per the app contract: `<name>_<version>_<arch>.raw` +
  metadata `.json` sidecar.

## The manifest

The root `index.json` is the index's identity document, signed by the index
key:

| Field | Meaning |
|---|---|
| `spec_version` | contract version of this document |
| `name` | human-readable display name (the local alias is the consumer's, not this) |
| `classes` | which of `apps` / `bases` this index serves, with their relative paths |
| `keys[]` | **the delegation set**: every cert this index accepts, each with `key_id` (SHA-256 of DER cert, lowercase hex), role (`index` / `build`), relative `cert_path`, `active` flag |
| `key_rotation` | monotonic counter bumped on key set changes (ADR-0007) |
| `version` | monotonic index version, bumped on every publish (see Trust) |
| `published_at` | unixtime set at signing; cross-checked against `version` — any mismatch = bail (see Trust) |

**Delegation-by-inclusion:** the signed `keys[]` list *is* the trust
statement — "I, the index holder, vouch for these builders." No per-cert
countersignatures. Key roles are positional in this list; certs themselves
carry no markings (resolves Q-B5).

## Per-arch catalogs

Each `catalog.json` is signed by the index key and lists **the latest
version of each name** for that arch and class:

| Entry field | Meaning |
|---|---|
| `name`, `version`, `arch` | identity (version = UAPI.10; `version` is the **DDI version the author assigns** — inner software versions are untracked by design) |
| `path` | relative path to the `.raw` |
| `sha256`, `size` | of the `.raw` — download-integrity anchor |
| `signing_key_id` | which build cert signed this image |
| `added_at` | unixtime the DDI was published into this index (the second signing moment: DDI signed at build, index at publish) |
| `runtime` | `portable` / `nspawn` (from the app contract declaration) |
| `base` | base lineage (`name` + `sysext_level`) — what `get` uses to resolve the closure |
| `description` | search field, projected from the embedded manifest — `search` is index-file text matching only, never opens DDIs |

A `type` field (`apps` / `bases`) guards against class confusion.

## Trust

- **Trust rides the build signature, never the index signature**
  (ADR-0037). The index signature provides *catalog integrity and
  anti-freeze for subscribers* — an index is a collection anyone can copy
  DDIs into; its signature is the signer's curation bookkeeping, not a
  vouching mechanism.
- **Two gates.** *get-gate:* signed catalog + `sha256` match — download
  integrity. *up-gate:* systemd verifies the build signature embedded in
  the DDI at every start (app contract §2) against the accepted-cert store.
  The two-signature cocktail: build with your key, be published under
  anyone's index key.
- **Monotonicity (anti-rollback/freeze):** every signed manifest/catalog
  carries the pair `generation` (monotonic counter) + `built_at` (unixtime
  at signing), bumped together on every publish. **The two must always move
  together — any disagreement is "iffy, bail out":** equal generation with
  a different timestamp → refuse (two catalogs claiming the same
  generation); newer generation with older timestamp → refuse; older
  generation with newer timestamp → refuse. Consumers remember the highest
  consistent pair per index identity and refuse anything older.
  Already-cached content stays usable; only the *catalog* is
  downgrade-protected. The counter is the machine rule (no clock trust);
  the timestamp doubles as the human staleness display. **Monotonicity
  applies to subscriptions only** — imports (ADR-0037) consume no foreign
  catalog, so the stale-catalog override question is moot. Field naming per
  §20/§21 rulings: the counter is the index's `version`; "generation" is
  dead.
- **Presence ≠ authenticity.** A partial copy may carry the full signed
  catalog while holding a subset of payload; `get` of an absent entry fails
  loudly. The catalog promises hashes are authentic, not that files are
  present.
- **Consumer-side storage:** pinned index keys and delegated build certs are
  stored per the VOA hierarchy (UAPI.11; `repository-metadata` and `image`
  purposes, per-index `$context`) — ADR-0034. The up-gate additionally
  requires the delegated build certs in `/etc/verity.d/` until systemd
  consumes VOA (T99); that store is flat, so per-index scoping is enforced
  at the get-gate plus runtime state (an image that bypassed a trusted `get`
  is refused at `up`).

## Subscribe and import (ADR-0037)

Content reaches a consumer by exactly two paths:

- **Subscribe.** `get <alias>/<name>` against a signed index at any
  location — https, ssh, or `file://` on a stick *if its maker signed an
  index for it*. The subscriber gets catalog integrity + the anti-freeze
  pair. Never trust.
- **Import.** Raw DDI files from anywhere (a directory, a stick, a friend's
  collection). Each file's **build signature** is verified against certs
  the consumer accepts — the signer's cert travels in the PKCS7 and is
  shown at import; accepting a new builder is an explicit act. Verified
  DDIs are added to the consumer's **own index**, re-signed with their own
  key. Selective and merge-friendly by construction.

**Every index is always signed.** There is no "local" exemption: an index
lives on a disk, and a disk may be a USB drive moved to another machine —
at which point it *is* an external index. Sneakernet chains re-curate at
every hop; content trust rides the build signatures end to end.

## Resolution

- Addressing is explicit: `get <alias>/<name>` — the alias is a local,
  consumer-chosen name bound to a pinned index key at `index trust`. No
  bare names, no default index.
- `get` fetches the **latest** version only (UAPI.10 max in the catalog);
  there is no downgrade-via-get. Local retention and on-disk revert are
  consumer policy, outside this contract.
- `get` resolves the **closure**: each `stack` entry is satisfied from an
  installed/cached base or fetched (bases class) — from any *trusted* index
  that serves it; if the closure cannot be satisfied, the whole `get` fails
  loudly and nothing half-usable lands in the cache.

## Authoring

A conformant author (reference implementation: `buildctl index …`):

- **`init`** — explicit ceremony: create the layout, generate the index
  keypair, write + sign the manifest. Identity keys are never created as a
  side effect.
- **`add <artifact>`** — the ADR-0038 sequence: probe the GPT (type UUIDs),
  verify the build signature against the accepted certs (unknown builders
  refused — accepting a new builder's cert is a separate explicit act),
  verity-verify, **then** extract the embedded manifest; derive the
  destination path from the *verified* identity (filenames are untrusted —
  files may be renamed to convention); project the entry fields into the
  catalog; re-sign; bump the index `version` + timestamp.
- **`update`** — full rescan/repair of a local tree, re-sign.
- **All operations are local-filesystem-only.** Transport to wherever the
  index lives is the operator's tool (`scp`, `rsync`, a stick). The index
  key never leaves the author's host (ADR-0009's surviving core).
- Catalog hygiene (description/publisher/license present) is enforced at
  `add` — the *published* floor is the index holder's standard, above the
  app contract's build floor.
- Updates must be atomic per signed file (write + sign to temp, rename), so
  a reader never observes an unsigned or half-written catalog.

## Consuming

- **`index trust <url|path>`** — the explicit ceremony: fetch the manifest,
  show identity + fingerprint, pin the index key, install the delegated
  build certs. Trust publishers, not media: a known identity at a new
  location (a friend's stick) needs no new ceremony; an unknown identity
  always does.
- **`index list`** — trusted identities, their aliases, known locations,
  staleness (age of newest seen catalog).
- **`index drop <alias>`** — untrust; refuses while apps from that index
  remain provisioned; non-destructive once none remain (everything is
  re-`get`-able after a future re-trust).

---

## Open items (for review)

1. **File names** (proposed, unconfirmed): root manifest `index.json`,
   per-arch `catalog.json`. *(Class dirs `apps/` + `bases/` confirmed
   2026-07-05.)* Related and parked: the **"index" noun itself** may get a
   better name, together with the unnamed distribute tool (ADR-0039).
2. ~~`.zip` transport bundle~~ — **RESOLVED: dropped** (payload already
   compressed inside the DDI).
3. ~~Anti-rollback shape~~ — **RESOLVED:** `version` + `published_at`
   cross-checked pair; subscriptions only; the stale-catalog `--force`
   question is **moot** under ADR-0037 (imports consume no foreign catalog).
4. ~~Catalog search fields~~ — **RESOLVED:** `name` + `description`
   matching; freeform tags rejected; **categories killed entirely
   (2026-07-06, §24 — no added value)**. Search is index-file-only.
6. ~~`up --get` across tools~~ — **RESOLVED by ADR-0040** (one binary, legs
   as namespaces): the composition flags work naturally within one tool.
