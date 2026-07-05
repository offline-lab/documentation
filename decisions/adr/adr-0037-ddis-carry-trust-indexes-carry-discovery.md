# ADR-0037 — DDIs carry trust; indexes carry discovery (subscribe + import)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-07-05 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | Amends ADR-0033 (replaces its carrier/curator model) |

## Context

ADR-0033's verbatim-mirror ("carrier") model — copy a whole index tree,
origin signature included — produced corner cases: partial copies (catalogs
listing absent files), stale-catalog refusals blocking legitimate offline
use, and a never-merge rule. The underlying error was conceptual: the index
signature was treated as a trust root. It never was one — an index is just a
collection of DDIs anyone can copy into; "publisher X vouched for this exact
set" was never real.

## Decision

> **DDIs carry trust. Indexes carry discovery.**

Trust belongs to the **app author's build signature**, embedded in the image
(UAPI.3) and verified against the consumer's accepted-cert store. The index
*file* exists for discovery and version tracking; its signature provides
**integrity and anti-freeze — never trust**.

Two acquisition paths, coexisting:

- **Subscribe:** `get <alias>/<name>` against a signed index at any location
  (https, ssh, `file://` on a stick if its maker signed one). The index
  signature buys the subscriber catalog integrity plus the
  `version`/timestamp anti-rollback pair. Monotonicity applies **only to
  subscriptions**.
- **Import:** take raw DDI files from anywhere; verify each build signature
  against certs the consumer accepts (the cert travels in the PKCS7 and is
  shown at import; acceptance is explicit); add to one's **own index**.
  Selective and merge-friendly by construction.

**Every index is always signed.** There is no local/shared distinction: an
index lives on a disk, and a disk may be a USB drive moved to another
machine — at which point it *is* an external index. The collection key is
created at an explicit collection-init ceremony, never as a side effect.

Retired by this model: carrier-vs-curator, the never-merge rule,
presence≠authenticity handling for foreign catalogs, and the stale-catalog
`--force` question (moot — no foreign catalog is consumed offline).
Demoted: delegation-by-inclusion becomes a **cert-distribution
convenience** at subscribe time (origin suggests builder certs; consumer
pins them in one ceremony), not the trust root.

## Consequences

- Sneakernet chains re-curate at every hop under the hop's own key while
  content trust rides the build signatures end to end.
- With ADR-0038 (metadata inside the image), even descriptions become
  builder-attested rather than curator-attested.
- Devices accumulate accepted *builder* certs (the store that has existed
  since ADR-0002); the flat-`verity.d` caveat is unchanged.
- The index contract and ADR-0033's affected sections require rewriting.

## Alternatives considered

### Verbatim-mirror carrier model (ADR-0033)
Superseded: partial-copy and staleness corner cases, and it misattributed
trust to the catalog signature.

### Unsigned local collections (sign only when sharing)
Rejected: media mobility makes any collection external at any moment.

## References

- `decisions/conversation/2026-07-04-design-session.md` §21–22.
- ADR-0002 (trust store), ADR-0038 (single-file package), ADR-0039 (tools).
