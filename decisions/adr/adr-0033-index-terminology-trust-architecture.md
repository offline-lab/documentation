# ADR-0033 — "Index" replaces "repository"; the trust architecture

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0008, ADR-0009, ADR-0010 (terminology + refinements) |

## Context

"Repository" implied a service and borrowed apt/docker semantics. The thing is
a collection of images from whoever, *indexed*: a signed catalog plus the
payload it vouches for. The trust design made the index the essence — identity
is the index key, trust is the index signature, "latest" is an index entry.
Offline distribution (USB sticks, sneakernet, device-to-device) must be the
same contract as HTTP, and mirroring must need no cryptography.

## Decision

**Terminology:** "index" replaces "repo/repository" ecosystem-wide. One noun;
verbs carry the role (buildctl: `index init/add/update`; appctl:
`index trust/list/drop`). Addressing is always explicit: `get <index>/<name>`
— no bare names, no hidden default registry. Precision rule: "the index" = the
whole published thing; "the index file" = the signed document.

**An index is a filesystem layout, not a service.** Anything that holds files
is one: HTTPS dir, USB stick, local folder, another device's cache. All URLs
inside are **relative** (refines ADR-0010), so the layout is
location-independent.

**Trust architecture:**

- **Two gates.** *get-gate:* signed index + artifact hash match governs what
  enters the cache. *up-gate:* systemd verifies the DDI's embedded build
  signature (`/etc/verity.d/`) at every start. Build signatures travel inside
  the image; index signatures wrap the catalog (the two-signature cocktail:
  build with your key, published under someone else's index key).
- **Delegation-by-inclusion.** The signed manifest lists the build certs the
  index holder accepts. Trusting an index = trusting its curated builder set.
  No per-cert countersignatures. Key roles are positional (index key =
  identity; listed certs = delegation) — resolves Q-B5.
- **Identity is the index key, not the URL.** Aliases bind to pinned keys;
  URLs are just locations. Trust publishers, not media: a known index on a
  stranger's stick works immediately; an unknown one needs the explicit
  `index trust` ceremony.
- **Carrier vs. curator.** Verbatim mirroring (cache, stick, `cp -r`) needs no
  keys and cannot tamper. Serving the same DDIs under your own index key is a
  *new* index (curation). Carriers never re-sign; catalogs from different keys
  are **never merged** — a multi-index stick is subtrees side by side.
- **Presence ≠ authenticity.** A partial mirror may carry the full signed
  index; `get` of an absent entry fails loudly.
- **Index monotonicity.** A device never accepts an index file older than the
  last seen for that identity (anti-rollback/freeze).
- **Latest-only remote** (affirms ADR-0008): `get` fetches only the latest
  (UAPI.10 ordering); no downgrade-via-get. Layout stores `<name>/<version>/`
  so versions coexist; local retention is end-user configurable (default
  current + previous); revert is an on-disk operation.
- **Flat-store caveat (documented):** `/etc/verity.d/` is global; per-index
  scoping is enforced at the get-gate plus appctl state (refuses to `up`
  images that bypassed a trusted `get`), not by the run-time store.

## Consequences

- Renames pending: `repository.json` (manifest name TBD),
  `docs/specs/repository.md`, all "repo" language in specs/schemas.
- appctl's old `repo add` becomes `index trust`.
- Storage namespacing `<root>/apps/<index-hash>/…` uses the index-key
  fingerprint (ADR-0035).

## Alternatives considered

### Keep "repo" on the consumer side only
Rejected: one thing, one name; role lives in the verbs.

### Exact-pin trust (image hash in device config)
Rejected: kills base patching and offline flexibility; the two gates cover it.

## References

- `decisions/conversation/2026-07-04-design-session.md` (§11, §13).
- ADR-0006/0007 (two keys, rotation — unchanged), ADR-0031, ADR-0034.
