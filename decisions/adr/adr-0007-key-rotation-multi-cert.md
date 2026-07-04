# ADR-0007 — Key rotation: gradual multi-certificate transition

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

Signing keys eventually rotate. A rotation mechanism must (a) let devices
verify packages signed under both the old and new keys during a transition,
and (b) not force every device to re-download its entire installed base at
once — critical for low-power, intermittently-connected devices.

Each package's metadata JSON carries a `signing_key_id` (the fingerprint of
the signing key), and devices store per-key certificates at
`/etc/verity.d/<repo-name>-<key-id>.crt`. The question is the *transition
strategy* on top of that mechanism.

## Decision

Adopt **Option A — gradual rotation** as the primary strategy.

- A new key signs new packages going forward.
- Old packages keep their existing signatures.
- Devices transition at their own pace; both old and new key certs coexist in
  `verity.d/`.
- No forced re-download of already-installed packages.

**Option B — clean cut-over** (re-sign all packages, bump a `key_rotation`
counter, force re-verification) is documented as an alternative suitable for
small repositories, but is not the primary strategy.

## Consequences

- Rotation is non-disruptive: devices are never forced to re-download.
- Old and new certificates coexist on devices during transition.
- The `key_rotation` counter mechanism (increment triggers re-verification on
  `repo refresh`) is available for the cut-over path if a repo ever needs it.

## Alternatives considered

### Option B — clean cut-over (re-sign everything, bump counter)

Documented but not the default. Suitable only for small repositories that can
afford to re-sign every package and force re-verification everywhere. Too
disruptive as the primary strategy for low-power, offline-leaning devices.

## References

- Related: ADR-0006 (two signing keys per repo).
- Original discussion: internal (not published).
