# ADR-0017 — package.yaml embedded in the DDI

| | |
|---|---|
| **Status** | Accepted — elevated by ADR-0038 (2026-07-05): the embedded manifest is no longer a convenience copy but **the** package metadata; the standalone `.json` is gone |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

For build-time provenance and traceability, it is useful to keep the
package's build manifest (`package.yaml`) alongside the built artifact. The
question is whether to embed it inside the DDI and, if so, whether to also
include the Dockerfile that produced it.

## Decision

buildctl ships `package.yaml` **inside the DDI** at
`/usr/share/<name>/package.yaml` for build-time provenance.

The Dockerfile is **not** included, due to copyright/attribution concerns for
third-party packages.

## Consequences

- The build manifest travels with the image, aiding inspection and
  reproducibility.
- No third-party Dockerfile licensing/attribution risk is introduced.
- Provenance is limited to the manifest, not the full build recipe.

## Alternatives considered

### Include the Dockerfile as well

Rejected. Dockerfiles may carry third-party copyright or attribution
obligations; shipping them inside redistributed packages creates a licensing
surface the project does not want to manage.

## References

- Original discussion: internal (not published).
