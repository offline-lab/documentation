# Security Model

> **Amended (2026-07-05).** The two-key model is **affirmed** and now framed as
> the **two-gate architecture** of
> [ADR-0033](https://github.com/offline-lab/documentation/blob/main/decisions/adr/adr-0033-index-terminology-trust-architecture.md):
> the *get-gate* (signed index + hash match governs what enters the cache) and
> the *up-gate* (systemd verifies the DDI's build signature at **every start**).
> New: **delegation-by-inclusion** (the signed manifest's cert list is the
> delegation; key roles are positional — resolves Q-B5, no cert marking),
> identity = index key, carrier-vs-curator, index monotonicity, and the
> documented flat-`verity.d` caveat. Terminology: repo → index. Where this page
> conflicts, ADR-0033 wins.

This page describes the trust chain for app packages, how signing keys are managed,
and what each security mechanism protects against.

---

## Trust chain

```
build key  (private, on build machine only, never on repo server)
  └── DDI signature partition  ← JSON: {rootHash, signature, certificateFingerprint}
        └── dm-verity root hash ← inside the signature partition + encoded in GPT partition UUIDs
              └── verity partition (superblock + hash tree) ← inside the same DDI
                    └── root partition (squashfs)  ← image blocks, verified at read time

index.json.p7s  ← PKCS7 signature over the repo index
  └── index.json ← package listing, verified at repo refresh
```

Both signatures are PKCS7. The build-key signature lives **inside the DDI** in the
signature partition (JSON: `{rootHash, signature, certificateFingerprint}`). There are
no companion files; everything systemd needs for verification is encoded in the GPT
partition table. See [package-format.md](package-format.md) for the full DDI layout and
partition UUID encoding rules.

The build key never touches the repo server. A compromised repo server can replace
files, but cannot forge valid signatures without the build key.

---

## What each layer protects

| Threat | Protected? | Mechanism |
|---|---|---|
| MITM on download | Yes | PKCS7 signature on roothash (inside DDI signature partition) |
| Malicious repo (without build key) | Yes | 2-key model: repo has index key, not build key |
| Accidental corruption / partial download | Yes | dm-verity roothash verification at attach |
| Tampered image at rest on running system | Yes (kernel) | dm-verity runtime block enforcement |
| Physical access to device | **No** | Kernel/U-Boot mutable without Secure Boot |
| Root compromise | **No** | Attacker can disable verification |

The crypto secures the **distribution path** (build → repo → download → install). It
does not and cannot secure the device on Pi hardware (no Secure Boot, no TPM, no
encrypted storage). On x86 with UEFI Secure Boot + TPM, the full chain becomes
enforceable. See "What this model does not protect" below.

---

## Signing keys

Two independent signing keys are used for app packages. They have different trust
levels, live on different machines, and must never be mixed up.

### Build key: package integrity (high trust)

Lives on the **build machine only**. Never copied to the repo server. Never committed
to version control.

- `<repo>.key`: private build key. Signs the DDI signature partition JSON for every
  package (build-time only, via pure-Go `go.mozilla.org/pkcs7` in buildctl). No
  verification code runs at runtime — systemd handles that natively.
- `<repo>.crt`: public certificate. Published in the repo's `keys/` directory.
  Imported by `appctl repo add`. Safe to share publicly.

Loss of this key means the repo can no longer publish signed packages. A compromised
build key means an attacker can forge package signatures; treat it like a CA key.

### Index key: catalog integrity (lower trust)

Lives on the **repo host**. Signs `index.json.p7s` for each arch index after a
publish. Can be stored on the repo server because its blast radius is limited: a
compromised index key lets an attacker manipulate the package catalog (advertise old
versions, hide packages) but **cannot forge package content**. systemd verifies the
build-key signature in the DDI signature partition at attach time regardless of what
the index says.

- `<repo>-index.key`: private index key. Stays on the repo host.
- `<repo>-index.crt`: public certificate. Also published in `keys/`. appctl uses it
  to verify the index; it does not use it to verify packages.

These are separate certs with separate `key_id` values. appctl knows which is which
from the `keys[]` array in the root index and from the `signing_key_id` on each
package entry (which always points to the build key cert).

### RAUC OTA signing

RAUC uses a separate PKI for signing update bundles (`.raucb` files):

- `.rauc/ca.cert.pem`: CA certificate baked into the OS image at build time.
  Devices use this to verify update bundles.
- `.rauc/ca.key.pem`: CA private key. Stays on the signing machine, never in the
  image, never committed.
- `.rauc/cert.pem` / `.rauc/key.pem`: signing cert/key used by `rauc bundle`.

These are distinct from app package signing keys. The RAUC PKI covers OS update
integrity; app signing covers individual package integrity. Both use PKCS7 but
with separate key material and separate verification paths.

The `.rauc/` directory is gitignored. See the build docs for how to provision it.

---

## Key creation

Generate a build keypair on the build machine:

```
buildctl key generate --name offline-lab --out ./keys/
```

Produces `offline-lab.key` (secret, stays on build machine) and `offline-lab.crt`
(public, publish to repo). Never copy the `.key` to the repo server.

Generate an index keypair on the repo host:

```
buildctl key generate --name offline-lab-index --index --out ./keys/
```

Produces `offline-lab-index.key` (stays on repo host) and `offline-lab-index.crt`
(public, publish to repo alongside the build cert). The `--index` flag marks this
cert as an index-signing key; buildctl and appctl use this distinction to know which
cert verifies packages and which verifies the index.

---

## Key import on device

```
# HTTP or HTTPS repo
appctl repo add https://packages.offline-lab.com --name offline-lab

# USB or local filesystem repo
appctl repo add file:///mnt/usb/offline-lab-repo --name offline-lab
```

Fetches `repository.json` and `repository.json.p7s`, downloads the active certs
from `keys/`, verifies the manifest signature against the index cert
(trust-on-first-use), then:

- Writes the **build cert** to `/etc/verity.d/<repo-name>-<key-id>.crt`. systemd reads
  this at attach time to verify the DDI signature partition. The cert is published at
  `keys/signing-<key-id>.crt` in the repo.
- Stores the **index cert** in appctl's internal state
  (`state/repos/<hash>.json`). appctl uses it
  to verify index signatures on subsequent `repo refresh` calls. systemd does not need
  it.

All subsequent attach operations trigger systemd's native userspace verification of the
DDI signature partition against the build cert. Index refreshes verify against the
index cert. **appctl performs no PKCS7 verification itself at runtime.**

`appctl repo remove <name>` removes the repo, deletes the build cert from
`/etc/verity.d/`, and drops the index cert from the repo's state record. On key compromise,
remove and re-add the repo after the operator rotates the affected key.

On Offline Lab OS, `/etc/verity.d/` is bind-mounted from persistent `/data/` storage at
boot, because `/etc` is an overlayfs whose upper layer is wiped on every boot. On any
other systemd host the standard path works natively.

---

## Multi-repo

Each repo has its own independent signing key. Users import keys per repo at
`appctl repo add` time. There is no central CA, no cross-signing, and no coordination
between repo operators. Any publisher can create a repo and signing key without
involving the appctl maintainers.

---

## Allowed protocols

HTTP, HTTPS, and `file://` are all permitted. This mirrors Debian's apt transport
model: transport confidentiality is provided by HTTPS when available, but content
integrity comes from the PKCS7 signatures regardless of transport. HTTP is safe for
offline and local network repos where HTTPS certificates are impractical, as long as
signing is in place. `file://` is required for USB and air-gapped repo use.

---

## Signature verification

### At install time (appctl stages, systemd verifies)

appctl downloads the DDI and metadata JSON, optionally pre-checks the PKCS7 signature
in userspace for early failure, then:

1. Stages the DDI to `/var/lib/appctl/images/<uuid>/<name>_<version>_<arch>.raw`.
2. Ensures the matching build cert is present at
   `/etc/verity.d/<repo-name>-<key-id>.crt`.
3. Hands off to `portablectl attach` (or `systemd-nspawn --image=` for
   `runtime: nspawn`).

From this point, **systemd performs all signature and verity verification natively**.
appctl has no PKCS7 verification code at runtime.

### systemd userspace verification flow

Verified by live test (2026-06-16, Fedora 44 VM, systemd 259, OpenSSL 3.5.5). The flow
in `src/shared/dissect-image.c` (`validate_signature_userspace()`, lines ~3080-3256) is:

1. `portablectl attach <ddi.raw>` invokes systemd-dissect.
2. systemd discovers the root, verity, and signature partitions by GPT type UUID (per
   the Discoverable Partitions Specification, UAPI.2).
3. Reads the signature partition JSON: `{rootHash, signature, certificateFingerprint}`.
4. **Tries kernel keyring verification first** (`crypt_activate_by_signed_key`).
   - In the open multi-publisher model, certs are not in the kernel keyring, so this
     always fails. systemd logs this at debug level and falls through — it is expected
     behavior, not an error.
5. **Falls back to userspace verification** (`validate_signature_userspace()`):
   - Scans `*.crt` files in the `verity.d/` hierarchy (see below).
   - Loads each as an X.509 PEM certificate.
   - Calls `PKCS7_verify(signature, certs, roothash, PKCS7_NOINTERN|PKCS7_NOVERIFY)`.
   - Succeeds if any cert validates the signature.
6. On success, activates dm-verity via the root hash (no signature sent to the kernel).
7. On failure, refuses to attach unless the image policy allows unsigned verity. appctl
   sets an explicit image policy in drop-ins (and `.nspawn` files) that makes signature
   verification failure fatal. See [Image policy](#image-policy) below.

Userspace verification is enabled by default. Three independent guards all default to
on: the `DISSECT_IMAGE_ALLOW_USERSPACE_VERITY` flag (set unconditionally in
`dissect_open_image()`), the `$SYSTEMD_ALLOW_USERSPACE_VERITY` environment variable,
and the `systemd.allow_userspace_verity=` kernel command-line argument.

**Hard requirement:** systemd must be compiled with OpenSSL (`HAVE_OPENSSL`). Without
it, userspace verity verification is impossible. OL OS (Buildroot) must ensure the
systemd package is built with OpenSSL support.

### Image policy

systemd's default image policy accepts any protection level
(`verity+signed+encrypted+unprotected+unused+absent`), meaning unsigned verity is an
acceptable fallback. Without an explicit policy, a DDI whose signature verification
fails can still be activated as unsigned verity — defeating the purpose of signing.

**Decision:** every image appctl attaches — single-image app, base image, or
extension image — MUST be cryptographically signed. Unsigned images are never
distributed, never accepted at install, and never activated at runtime. There is no
fallback path.

**Canonical policy string:**

```
root=signed:=absent
```

Read as:

- `root=signed` — the root partition must exist, must have dm-verity, and must be
  accompanied by a valid PKCS7 signature over the roothash. systemd auto-derives
  matching requirements for the `root-verity` and `root-verity-sig` partitions from
  the `signed` flag on `root`.
- `=absent` (empty partition identifier) — the default for any partition type not
  explicitly listed. Every other partition type (`usr`, `home`, `srv`, `tmp`, `var`,
  `swap`, `esp`, `xbootldr`) is forbidden. The DDI must contain only root,
  root-verity, and root-verity-sig partitions — exactly what buildctl produces.

This policy applies to every image class. Anything looser (`verity`, `unprotected`)
admits unsigned images. Anything tighter (`encrypted`) requires LUKS, which does not
apply to read-only squashfs DDIs.

**Where appctl writes it:**

- Portable mode (single image, systemd ≥ 250): `ImagePolicy=root=signed:=absent` in
  the service drop-in at
  `/etc/systemd/system.attached/<name>.service.d/99-appctl.conf`.
- nspawn mode: `ImagePolicy=root=signed:=absent` in the `.nspawn` file.

The policy string is a documented contract. Operators and packagers can rely on it
being stable; it is not configurable at runtime. See
[systemd.image-policy(7)](https://www.freedesktop.org/software/systemd/man/latest/systemd.image-policy.html)
for the full policy syntax.

**Verified by live testing** (2026-06-16, Fedora 44, systemd 259): without an explicit
policy, removing the cert from `/etc/verity.d/` did NOT prevent the image from
mounting — systemd fell back to unsigned verity. With `ImagePolicy=root=signed:=absent`,
the same test correctly refuses attachment.

### `/etc/verity.d/` hierarchy

systemd searches these directories in priority order (highest first), matching the
[UAPI.11 (VOA)](https://uapi-group.org/specifications/specs/file_hierarchy_for_the_verification_of_os_artifacts/)
file hierarchy for verification of OS artifacts:

| Path | Use |
|---|---|
| `/etc/verity.d/` | Admin override (highest priority) |
| `/run/verity.d/` | Runtime (volatile, e.g. temporarily added for testing) |
| `/usr/local/lib/verity.d/` | Local vendor |
| `/usr/lib/verity.d/` | Distro vendor (lowest priority) |

`*.crt` files are PEM-encoded X.509 certificates. Masking via a symlink to `/dev/null`
is supported (the `CONF_FILES_FILTER_MASKED` flag is honored), so an admin can disable
a specific cert without deleting it.

appctl writes build certs only to `/etc/verity.d/`. On Offline Lab OS, `/etc/verity.d/`
is bind-mounted from persistent `/data/` storage at boot, because `/etc` is an overlayfs
whose upper layer is wiped on every boot. On any other systemd host, the standard path
works natively.

### At runtime (dm-verity)

systemd-dissect activates dm-verity with the root hash during attach. The kernel
verifies every block read against the hash tree. An image that has been modified after
install will fail to mount or cause read errors on tampered blocks.

This check happens in the kernel on every read from the squashfs. It cannot be bypassed
from userspace.

### At repo refresh (appctl)

`appctl repo refresh` re-downloads `index.json` and verifies `index.json.p7s` against
the stored index cert before updating the local package cache. A tampered or unsigned
index is rejected. This verification is performed by appctl directly (not systemd),
because the index is a JSON catalog, not a DDI.

---

## Repository trust rules

**Same-server rule:** appctl rejects any package download URL that resolves to a
different server than the repo's `base_url`. A legitimate index cannot be used to
redirect downloads to a different server.

**No redirect following across origins:** if a repo server responds with an HTTP
redirect to a different origin or base URL, appctl rejects it. Redirects within the
same origin are permitted (e.g. HTTP to HTTPS on the same host).

**Single source of truth:** the `base_url` set at `appctl repo add` time is the
authoritative origin for that repo. Index and packages must come from that origin.

---

## Repo status and blocklist

Each repo's state record at `state/repos/<hash>.json` carries a `status` field:

| Status | Behaviour |
|---|---|
| `active` | Normal operation; refresh, install, update allowed |
| `paused` | No automatic refresh or updates; manual install still works |
| `blocked` | All operations rejected; installed packages from this repo still run |

`appctl repo pause <name>` and `appctl repo block <name>` manage this field.
A repo operator can optionally publish a signed blocklist via their index (future).

---

## What this model does not protect

**Honest boundary.** Crypto secures the **distribution path** (build → repo → download
→ install). It does not and cannot secure the device on Pi hardware: there is no TPM,
no Secure Boot (no UEFI firmware), and no encrypted storage. dm-verity and package
signing protect against software-level tampering and supply-chain attacks; they do not
protect against a determined attacker with physical access to removable storage.

dm-verity stays in the design despite the Pi limitation because:

- The platform is expanding to x86 and standard ARM64 where UEFI Secure Boot is
  available and the full chain becomes enforceable.
- PKCS7 + roothash verification at install time works on all hardware.
- Runtime enforcement depends on hardware capability (marginal on Pi, real on x86).

A Secure Boot implementation for Pi exists, but adds limited value here: even with a
verified boot chain, the storage is still removable and replaceable. This is an accepted
hardware boundary. RAUC bundle signing protects OTA update integrity within this
boundary.

**Physical access to removable storage:** these devices boot from SD cards or
removable NVMe. An attacker with physical access can remove the storage medium, modify
it on another machine, and return it.

**Root on the device:** a process running as root can call `portablectl attach`
directly without going through appctl, bypassing install-time pre-checks. Root access
is assumed to be a fully compromised state.

**Key rotation latency:** if a signing key is compromised, already-installed packages
on devices will continue to pass dm-verity (the block hashes are still valid). Devices
must rotate the repo cert and update affected packages.

---

## Key rotation

When a repo operator needs to rotate their signing key, two approaches are available.

### Option A: Gradual rotation (recommended for large or offline-first repos)

1. Generate a new keypair: `buildctl key generate`
2. New packages published from this point are signed with the new key. Old packages
   keep their existing signatures; no re-download required.
3. Publish the new cert in the repo. Devices fetch it during the next `appctl repo refresh`.
4. `appctl repo add-key <name> <cert>` stores the new cert alongside the old one on device.
5. systemd verifies each package at attach time against the cert matching its
   `signing_key_id` field. Old packages verify against the old cert; new or updated
   packages verify against the new cert.
6. After 90 days (configurable, or manually), the old cert is pruned:
   `appctl repo remove-key <name> <key-id>`. Any package still signed with the old key
   must be updated before the old cert is removed.

This approach is safe for air-gapped and offline devices; they transition at their own
pace without forced re-downloads.

### Option B: Clean cut-over (for small repos or post-compromise)

1. Generate a new keypair.
2. Re-sign all packages: `buildctl rebuild --all` (see buildctl docs).
3. Bump the `key_rotation` counter in `index.json`.
4. `appctl repo refresh` detects the counter change and re-downloads and re-verifies
   all installed packages from that repo against the new cert.
5. Remove the old cert from the repo.

This is simpler for repos with few packages but requires devices to be reachable to
complete the rotation.

### Cert storage on device

```
/etc/verity.d/<repo-name>-<key-id>.crt   ← one file per key ID per repo (build certs)
```

`signing_key_id` in the package metadata JSON carries the fingerprint of the build key
that signed the DDI signature partition. appctl uses it to match the package to the
correct cert at install time. systemd reads the cert at attach time. If no matching
cert is in `/etc/verity.d/`, attachment fails.

Index certs are stored in appctl's repo state records under
`state/repos/<hash>.json`, not in `/etc/verity.d/`. systemd does
not need them.

---

## Permanent design decisions

**Userspace verification is the permanent answer, not a stopgap.** systemd's
`validate_signature_userspace()` via `verity.d/` is the chosen mechanism for runtime
signature verification. This is not a compromise pending kernel-keyring support.

The kernel `.secondary_trusted_keys` keyring path requires every repo key to be
cross-signed by a CA baked into the kernel. This is incompatible with the open,
multi-publisher repo model where any publisher creates their own key without involving
offline-lab. systemd's userspace path sidesteps this entirely.

VOA (UAPI.11, Verification of OS Artifacts) is a draft spec that generalizes the
`verity.d/` concept. The current implementation is systemd's `verity.d/` hierarchy.
Migration to VOA, if it ever materializes, is a systemd concern — appctl's contract
(put the cert in the right place) does not change.
