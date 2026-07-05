# Security Model

**Status:** rewritten 2026-07-05 against ADR-0037 (trust model), ADR-0038
(single-file package), ADR-0033/0034 and the
[Index contract](index-contract.md) (T98). The systemd verification flow and
image-policy sections are live-test-backed (2026-06-16, Fedora 44,
systemd 259) and survive from the previous revision.

---

## The trust principle

> **DDIs carry trust. Indexes carry discovery.** (ADR-0037)

Three layers do three different jobs; only the third is trust:

1. **dm-verity** (hash tree) proves *integrity*: content matches the
   roothash — unmodified since someone made it. Knows nothing about who.
2. **The PKCS7 signature over the roothash** is an *authenticity claim*.
   The signer's certificate rides inside the PKCS7 blob — but a signature
   carrying its own cert proves only self-consistency; anyone can sign
   their own image.
3. **The accepted-cert store** turns the claim into trust: systemd
   validates the signature against certs the operator explicitly accepted
   (`/etc/verity.d/`). Trust always belongs to the **app author's build
   key** — never to an index, a server, a stick, or a transport.

An index's signature provides *catalog integrity and anti-freeze for
subscribers* — never trust. An index is a collection anyone can copy DDIs
into; "the publisher vouched for this set" was never a real property.

## Trust chain

```
build key (private; author's build machine only)
  └── DDI signature partition ← JSON: {rootHash, signature}  (cert inside the PKCS7)
        └── dm-verity roothash ← also encoded in the GPT partition GUIDs
              └── verity partition (hash tree)
                    └── root partition (squashfs) ← blocks verified by the kernel at read time

index key (whoever maintains that index — origin, stick-maker, your device)
  └── signed manifest + catalogs ← discovery, download integrity,
                                    version/timestamp anti-rollback. NOT trust.
```

The package is **one file** (ADR-0038); everything systemd needs is inside
it. A compromised index host can rearrange the catalog but cannot forge a
single package signature.

## The two gates

| Gate | When | Checks | Provided by |
|---|---|---|---|
| **get-gate** | image enters the local collection | subscription: signed catalog + SHA-256 match (download integrity). Import: full signature + verity verification against accepted certs | the distribute tool |
| **up-gate** | **every start** | PKCS7 over roothash vs `/etc/verity.d/`, then dm-verity activation | systemd, natively — no verification code in our tools |

Known limitation (documented since ADR-0033): `/etc/verity.d/` is a **flat**
store — an accepted cert verifies any image it signed, regardless of which
index delivered it. Per-index scoping is enforced at the get-gate plus
runtime state (appctl refuses to `up` images that bypassed a trusted
acquisition), not by the store.

## What each layer protects

| Threat | Protected? | Mechanism |
|---|---|---|
| Tampered download / MITM | Yes | catalog SHA-256 (subscription) + PKCS7 over roothash (always) |
| Malicious index host (no build key) | Yes | it cannot forge build signatures; systemd verifies at every start |
| Stale/freeze attack on a subscription | Yes | `version` + `published_at` cross-checked pair; consumers refuse anything older or inconsistent (see Index contract) |
| Unknown builder on imported media | Yes | import refuses unless the builder's cert is explicitly accepted |
| Accidental corruption / partial download | Yes | dm-verity verification at attach |
| Tampered image at rest | Yes (kernel) | dm-verity runtime block enforcement |
| Physical access to removable storage | **No** | see "What this model does not protect" |
| Root compromise on the host | **No** | root can bypass anything |

## Signing keys

Two key roles, different custody, different blast radius. Roles are
**positional in the signed index manifest** (`keys[]`), never marked in the
certs themselves (Q-B5 resolved).

### Build key — trust (high stakes)

Lives on the **author's build machine only**. Signs the roothash into every
DDI's signature partition at `buildctl build` (signing is inside `build`;
unsigned images do not exist — ADR-0031). Compromise = an attacker can forge
packages; treat like a CA key. The public cert is what consumers accept.

### Index key — integrity (operational)

Every index has one — origin servers, stick indexes, and each device's own
local collection alike (**every index is always signed**; a disk can be
moved, so there is no "local only" exemption — ADR-0037). Created at the
explicit `index init` ceremony of the distribute tool (ADR-0039), never as
a side effect. Compromise = catalog manipulation for that index's
subscribers; **cannot** inject content (build signatures still gate every
start).

### OS update signing (RAUC)

Offline Lab OS signs its OTA bundles with a separate PKI. That is an
OS-side concern (`OS-CONFORMANCE.md`), fully independent of app signing.

## Getting certs onto a device

Two ceremonies, matching the two acquisition paths (ADR-0037):

- **Subscribe** — `index trust <url|path>`: fetch the manifest, show the
  index identity + fingerprint, pin the index key, and **bulk-accept the
  builder certs it distributes** (`keys[]` + `keys/` — the manifest is a
  cert-distribution channel, not a trust root). Build certs land in
  `/etc/verity.d/<index>-<key-id>.crt`; the index key is pinned in the
  tool's VOA store (UAPI.11, ADR-0034).
- **Import** — for raw DDIs from anywhere: the tool reads the signer cert
  out of the DDI's PKCS7, shows fingerprint + subject, and asks. Accepting
  a builder is an explicit act; on yes, the cert enters the store and the
  image is fully verified and added to the local index.

Untrusting an index (`index drop`) removes its pinned key and the certs
that arrived through it (refusing while its apps remain provisioned —
ADR-0032).

## Verification flows

### At acquisition

Subscription `get`: download per the signed catalog, check SHA-256.
Import: the full ADR-0038 order — GPT probe (type UUIDs) → PKCS7 vs
accepted certs → verity verification → only then extract the embedded
manifest. **Unverified images are never parsed.**

### At every start — systemd's userspace flow (live-tested)

Verified 2026-06-16 (Fedora 44 VM, systemd 259, OpenSSL 3.5.5); the flow in
`src/shared/dissect-image.c` (`validate_signature_userspace()`):

1. `portablectl attach` (or nspawn) invokes image dissection.
2. Partitions are discovered by GPT **type UUID** (UAPI.2).
3. The signature partition JSON (`{rootHash, signature}`) is read.
4. **Kernel keyring verification is tried first** and, in our open
   multi-publisher model, always fails (no certs there) — logged at debug
   level and expected, not an error.
5. **Userspace fallback:** every `*.crt` in the `verity.d/` hierarchy is
   loaded; `PKCS7_verify(...)` succeeds if any cert validates the
   signature.
6. On success, dm-verity is activated with the roothash; the kernel then
   verifies every block read.
7. On failure, attach is refused — because of the pinned image policy
   below. **No fallback to unsigned.**

Userspace verification is on by default (three independent guards all
default on). **Hard requirement:** systemd built with OpenSSL (ADR-0003).

### Image policy (live-tested)

systemd's *default* policy accepts unsigned verity — without an explicit
policy, deleting the cert did **not** prevent mounting in the live test.
Therefore every attach carries the canonical policy, written into the
generated drop-in (portable) or `.nspawn` file:

```
root=signed:=absent
```

`root=signed` — root must exist, with dm-verity and a valid signature
(requirements for verity/verity-sig partitions are auto-derived).
`=absent` — every other partition type is forbidden; the DDI contains
exactly root + verity + verity-sig. Layered apps split this into
`RootImagePolicy=`/`ExtensionImagePolicy=` (same string, systemd ≥ 254 —
ADR-0028). The string is a stable contract, not operator-configurable.

### The `verity.d/` hierarchy

systemd searches, highest priority first:

| Path | Use |
|---|---|
| `/etc/verity.d/` | admin-accepted certs (the tools write here) |
| `/run/verity.d/` | volatile/testing |
| `/usr/local/lib/verity.d/` | local vendor |
| `/usr/lib/verity.d/` | distro vendor (e.g. OL OS bakes the project cert here for the tools-sysext, T105) |

`/dev/null` symlink masking is honored. On OL OS the persistence of
`/etc/verity.d/` across the overlay wipe is the OS's duty
(`OS-CONFORMANCE.md` / `recover`).

### At subscription refresh

The distribute tool re-fetches the manifest/catalogs, verifies the index
signature against the pinned key, and enforces **monotonicity**: the
`version` + `published_at` pair must be internally consistent and not older
than the highest pair seen for that identity (see
[Index contract](index-contract.md)). Imports consume no foreign catalog, so
no staleness question arises there.

## Multi-index

Each index has its own keys. No central CA, no cross-signing, no
coordination: any publisher creates keys and publishes without involving
anyone. Any device is itself an index author (its local collection).

## Transports

HTTP, HTTPS, `file://`, ssh — all permitted (apt's model): integrity and
trust come from signatures, never from the transport. All URLs inside an
index are **relative**, so an index works identically at any location
(ADR-0033 as amended).

## Key rotation

Per ADR-0007 (gradual, multi-cert):

1. The author generates a new build keypair; new packages are signed with
   it. Old packages keep their valid signatures.
2. The new cert is published in the index's `keys[]`; subscribers pick it
   up at the next refresh (`key_rotation` counter bumps). Import users
   accept it at the next import.
3. Both certs coexist in `verity.d/` during the transition; systemd
   verifies each package against whichever cert matches.
4. The old cert is pruned once nothing depends on it.

A clean cut-over (re-sign everything, bump `key_rotation`, prune
immediately) remains the post-compromise option.

## What this model does not protect

**Honest boundary.** The cryptography secures the distribution path
(build → index → acquisition → start). It cannot secure a host whose
hardware offers no Secure Boot, TPM, or storage encryption (e.g. SD-card
SBCs): an attacker with physical access can modify the medium offline, and
root on the host can bypass every gate (attach images directly, edit the
trust store). On UEFI + TPM hardware the chain becomes enforceable
end-to-end. Already-installed packages keep passing dm-verity after a key
compromise (their block hashes remain valid) — rotation + updates close
that window.

## Permanent design decisions

- **Userspace verification via `verity.d/` is the permanent mechanism**,
  not a stopgap: the kernel-keyring path requires CA cross-signing baked
  into the kernel, incompatible with the open multi-publisher model.
- **VOA (UAPI.11) adoption is two-step** (ADR-0034): the tools' own trust
  material (pinned index keys, per-index context) uses the VOA hierarchy
  now; the up-gate migrates off flat `verity.d/` when systemd consumes VOA
  (tracked as T99 — that migration also closes the flat-store caveat).
- **No verification code in our tools at runtime.** systemd verifies;
  the tools arrange files and write policy.
