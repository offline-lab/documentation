# Design Session — 2026-06-15

## Recap and Resolution Log

This session challenged the existing buildctl/appctl design from first principles.
Major outcome: the package format shifts from a custom 5-file set to the UAPI
DDI standard, and runtime verity/signature verification moves from custom appctl
code to systemd's native userspace verification.

---

## 1. Product Definition

### What this is

A universal toolchain (buildctl + appctl) for building, distributing, and running
signed, verified systemd portable services and nspawn containers. Works on any
systemd host with portablectl installed — from a 512MB Pi Zero 2W to a rack
server.

### The core value: the bridge

```
Docker (build)  ───────────────────  systemd portable (run)
    │                                         │
    ├─ familiar Dockerfile                    ├─ no daemon
    ├─ universal build tool                   ├─ works on 512MB SBC
    ├─ cross-arch via buildx                  ├─ native systemd lifecycle
    │                                         ├─ namespace isolation
    │                                         ├─ dm-verity integrity
    │                                         │
    └─────────→ buildctl ──────────→          │
                   packages as DDI             │
                   signs with PKCS7            │
                   publishes to repo           │
                   │                           │
                   ↓                           │
                 repo ──────→ appctl ──────────┘
                              downloads
                              verifies
                              attaches via portablectl
```

Docker solved build ergonomics but demands a runtime daemon that excludes
low-power hardware. systemd portable services solve the runtime but have no build
tooling, signing, or distribution. **buildctl + appctl bridge that gap: use Docker
(or mkosi/shell/make) to build, use systemd to run.**

The same DDI built from a Dockerfile on a developer's Mac runs on a Pi Zero and
a rack server. No Docker at runtime. No daemon. Just systemd.

### What it is NOT

- Not a Docker replacement
- Not a mkosi clone
- Not an Offline Lab OS exclusive tool
- Does not duplicate what portablectl/systemd-nspawn/systemd already handle
- Does not share data between apps (hard isolation constraint)

---

## 2. Foundational Decisions

### 2.1 Platform: systemd + portablectl

systemd IS the host abstraction. portablectl, sysusers, tmpfiles, systemctl,
security profiles, unit files — all cross-distro. The host prerequisite is:
**systemd + portablectl installed. Nothing else.**

No "host abstraction layer" is needed. systemd provides the cross-distro
compatibility layer.

### 2.2 Universality: standard FHS paths

The tool uses standard Linux paths everywhere. Offline Lab OS adapts its
constrained filesystem to standard expectations via bind mounts.

| Concern | Standard path | Offline Lab OS backing |
|---|---|---|
| appctl state | `/var/lib/appctl/` | bind from `/data/` |
| appctl images | `/var/lib/appctl/images/<uuid>/` | bind from `/data/` |
| app data | `/var/lib/appctl/apps/<hash>/<name>/` | bind from `/data/` |
| signing certs | `/etc/verity.d/` | bind from `/data/` |
| metadata | `/var/lib/appctl/` | bind from `/data/` |

On any other systemd host, these paths just work natively. The complexity of
Offline Lab OS's read-only rootfs + ephemeral `/etc` stays in the OS layer
(bind mounts, boot services), not in appctl.

For `/etc/sysusers.d/` specifically (ephemeral on OL OS): either bind mount the
standard path from persistent storage, or have appctl call `systemd-sysusers`
directly at rehydrate. The rehydration command is idempotent — on a normal
distro it's a harmless no-op.

### 2.3 Trust model: full crypto, hardware-limited

**Hardware constraints (Pi Zero 2W):**
- No TPM
- No Secure Boot (no UEFI firmware)
- No encrypted storage

**What the crypto protects:**

| Threat | Protected? | Mechanism |
|---|---|---|
| MITM on download | Yes | PKCS7 signature on roothash |
| Malicious repo (without build key) | Yes | 2-key model: repo has index key, not build key |
| Accidental corruption / partial download | Yes | dm-verity roothash verification |
| Tampered image at rest on running system | Yes (kernel) | dm-verity runtime block enforcement |
| Physical access to device | **No** | Kernel/U-Boot mutable without Secure Boot |
| Root compromise | **No** | Attacker can disable verification |

**The honest boundary:** the crypto secures the **distribution path** (build →
repo → download → install). It does not and cannot secure the **device** on Pi
hardware. On x86 with UEFI Secure Boot + TPM, the full chain becomes enforceable.

**dm-verity stays** despite Pi limitations because:
- The platform is expanding to x86 and standard ARM64 where Secure Boot is available
- PKCS7 + roothash verification at install time works on all hardware
- Runtime enforcement depends on hardware capability (marginal on Pi, real on x86)

### 2.4 Multiple build backends

Any tool that produces a rootfs directory → buildctl packages it as a signed DDI.

```
Dockerfile ──┐
mkosi.conf ──┼──→ rootfs directory ──→ buildctl ──→ signed DDI
build.sh ────┤
Makefile ────┘
```

Auto-detection: buildctl sees what's in the directory and picks the backend.
No `--backend` flag needed. mkosi is first-class from the start (systemd ecosystem
native), not deferred to Phase 6.

The backend produces a filesystem tree. Everything after that (validation, chown,
embed package.yaml, squashfs, dm-verity, PKCS7, DDI creation) is backend-agnostic.

---

## 3. Major Finding: UAPI Alignment

### 3.1 The alignment gap

The original design used a custom 5-file format. The UAPI Group specifications
define standards for exactly this use case that systemd handles natively.

| Original design | UAPI standard | Status |
|---|---|---|
| 5-file set (squashfs + companion files) | **DDI** (UAPI.3): GPT with root + verity + sig partitions | Non-standard |
| Custom verity setup (losetup + veritysetup) | **DPS** (UAPI.2): systemd-dissect handles natively | Reinventing |
| `.squashfs.roothash.p7s` naming | DPS signature partition: JSON `{rootHash, signature, certificateFingerprint}` | Non-standard |
| `/data/config/keys/` cert store | **VOA** (UAPI.11) / systemd `verity.d/` | Non-standard |
| Custom PKCS7 verification in appctl | systemd native userspace verification | Reinventing |

### 3.2 DDI format (UAPI.3 + UAPI.2)

A Discoverable Disk Image is a GPT partition table containing:

```
Partition 1: Root (arch-specific type UUID)       ← squashfs filesystem
Partition 2: Verity (arch-specific type UUID)     ← dm-verity superblock + hash tree
Partition 3: Signature (arch-specific type UUID)  ← JSON: {rootHash, signature, certificateFingerprint}
```

Partition UUIDs encode the root hash:
- Root partition UUID = first 128 bits of root hash
- Verity partition UUID = last 128 bits of root hash

Naming: `<name>_<version>.raw` (underscore version separator, per UAPI spec).

### 3.3 systemd native userspace verification

**Verified from systemd source code** (`src/shared/dissect-image.c`, lines 3080-3256):

systemd explicitly built userspace PKCS7 verification because kernel keyring cert
installation is too messy for the multi-publisher model:

```c
/* Because installing a signature certificate into the kernel chain is so messy,
 * let's optionally do userspace validation. */
```

**The verification flow (from source):**

1. DDI has signature partition (JSON with `rootHash` + PKCS7 `signature`)
2. systemd-dissect activates verity (`do_crypt_activate_verity`)
3. If signature present + policy requires SIGNED:
   - Try kernel keyring verification (`crypt_activate_by_signed_key`)
   - If that fails (cert not in keyring) → **fall back to userspace**
4. Userspace verification (`validate_signature_userspace`):
   - Searches for `*.crt` files in:
     ```
     /etc/verity.d/          ← admin override (highest priority)
     /run/verity.d/          ← runtime
     /usr/local/lib/verity.d/ ← local vendor
     /usr/lib/verity.d/      ← distro vendor (lowest priority)
     ```
   - Loads each as X.509 PEM certificate
   - `PKCS7_verify(signature, certs, roothash)` with `PKCS7_NOINTERN|PKCS7_NOVERIFY`
   - Succeeds if any cert validates the signature
5. If userspace verification succeeds → activate dm-verity via root hash
6. If userspace verification fails → check if policy allows unsigned verity

**Key detail:** `CONF_FILES_FILTER_MASKED` flag is used — symlinks to
`/dev/null` (masking) are supported, same concept as VOA.

This is a **fully standard, already-implemented** mechanism. No kernel keyring
needed. No custom verification code in appctl needed for runtime.

### 3.4 Cert storage: verity.d/

systemd's `verity.d/` is the **already-implemented** cert hierarchy. VOA
(UAPI.11) is a draft spec that generalizes this concept further. For now,
`verity.d/` works.

Build signing certs go in `/etc/verity.d/<key-id>.crt` (PEM format X.509).
systemd discovers and uses them automatically during DDI dissection.

---

## 4. Package Format Change

### Before: 5 custom files

```
<name>-<version>-<arch>.squashfs
<name>-<version>-<arch>.squashfs.roothash
<name>-<version>-<arch>.squashfs.roothash.p7s
<name>-<version>-<arch>.squashfs.verity
<name>-<version>-<arch>.json
```

### After: DDI + metadata

```
<name>_<version>_<arch>.raw     ← DDI (GPT: root squashfs + verity + signature)
<name>_<version>_<arch>.json    ← appctl metadata (ports, volumes, resources, etc.)
```

Transport: both files in a zip.

### What's inside the DDI

The DDI contains everything systemd needs for verity + signature verification:
- Root partition: the squashfs filesystem
- Verity partition: dm-verity superblock + hash tree
- Signature partition: JSON `{rootHash, signature, certificateFingerprint}`

The metadata JSON is appctl-specific management data (package name, version,
description, ports, volumes, resources, lifecycle hooks). It does not belong
inside the portable service filesystem.

### Build-time signing still in buildctl

buildctl still needs PKCS7 signing (pure Go, `go.mozilla.org/pkcs7`) to create
the signature partition content. But this is build-time only, on the developer
machine. No verification code needed at runtime — systemd does it.

---

## 5. Runtime Architecture

### Install flow (simplified from original 16 steps)

```
1. Download DDI + metadata JSON
2. (Optional) appctl pre-verifies PKCS7 in userspace before staging
3. Stage DDI to /var/lib/appctl/images/<uuid>/
4. Ensure build cert is in /etc/verity.d/
5. Allocate uid, create sysusers snippet, call systemd-sysusers
6. Create app storage dirs (/var/lib/appctl/apps/<hash>/<name>/)
7. Generate drop-in (User=, Group=, BindPaths=)
8. portablectl attach <ddi.raw>
   → systemd-dissect discovers root/verity/sig partitions by GPT type UUID
   → reads roothash + signature from signature partition
   → kernel verification fails → userspace verification via verity.d/ → succeeds
   → sets up dm-verity → mounts verified squashfs
   → discovers service units → copies to /etc/systemd/system.attached/
   → generates drop-in with RootImage=
9. portablectl enable + systemctl start <name>.service
```

### What appctl no longer needs to do

- **PKCS7 verification at runtime** — systemd does it natively via `verity.d/`
- **dm-verity device setup** — systemd-dissect handles it natively
- **losetup / veritysetup** — systemd handles loop + verity internally
- **Companion file management** — everything is inside the DDI

appctl's runtime job reduces to: repo management, uid allocation, storage
namespacing, drop-in generation, lifecycle hooks, rehydration orchestration.

### Rehydration

After reboot, portablectl attachments are gone (on OL OS, `/etc` resets). The
rehydration command re-attaches all installed services:

```
appctl rehydrate:
  for each installed package:
    portablectl attach <ddi.raw>
    (systemd re-verifies signature, re-sets up verity, re-discovers units)
    regenerate drop-in
    portablectl enable
```

On a normal distro (no overlay reset), rehydration is a harmless no-op —
everything is already attached. On OL OS, it rebuilds the ephemeral state from
the persistent DB.

---

## 6. Performance on Low-Power Hardware

### Pi Zero 2W constraints

- 512 MB RAM
- Quad-core Cortex-A53 (ARMv8)
- SHA256 may run in software (~15 MB/s) due to Cortex-A53 erratum on early silicon
- ~1W power consumption

### dm-verity costs (worst case, software SHA256)

| Image size | Blocks to verify | First-read overhead | At 45 MB/s (crypto ext.) |
|---|---|---|---|
| 4 MB (mosquitto) | ~1,000 | ~270ms | ~90ms |
| 10 MB (ircd) | ~2,500 | ~670ms | ~220ms |
| 25 MB (web app) | ~6,400 | ~1.7s | ~560ms |
| 50 MB (heavier app) | ~12,800 | ~3.3s | ~1.1s |

These are **one-time costs at first read**. After files are in the page cache,
there is zero verity overhead.

### Where costs land

- **Service startup:** adds 0.3-3 seconds depending on image size (one-time)
- **Runtime:** effectively zero (files cached, no ongoing verification)
- **Boot rehydrate (4 services):** 4-8 seconds (one-time)
- **Memory (hash cache):** ~80-400KB per service (negligible on 512MB)

### Comparison to Docker

| | Docker on Pi Zero 2W | Our approach (DDI + dm-verity) |
|---|---|---|
| Runtime daemon | containerd: 30-50MB RAM **continuously** | None |
| Integrity guarantee | None | dm-verity + PKCS7 signed |
| Startup overhead | Container creation + overlay mount | Squashfs mount + verity verify |

Our approach is **lighter than Docker** even with dm-verity, because there is no
daemon. The verity CPU cost is one-time; Docker's memory cost is continuous.

### Scaling across hardware

- **Pi Zero 2W:** 2-4 small apps, slow boot, tight memory — works, no daemon overhead
- **Pi 4:** 10-20 apps, faster boot, comfortable headroom
- **x86 server:** dozens of apps, fast boot, Secure Boot enables full trust chain

Same format, same tooling. The constraints are the hardware's, not the tool's.

---

## 7. Build Pipeline (The Convergence Point)

### Where all backends meet

All backends converge at a **rootfs directory on disk**. Everything before that
is backend-specific. Everything after is buildctl's job.

```
Dockerfile ──→ docker build → docker export → rootfs dir ─┐
                                                            │
mkosi.conf ──→ mkosi (output=directory) → rootfs dir ──────┤
                                                            │
build.sh ────→ script writes to outdir → rootfs dir ───────┤
                                                            │
Makefile ────→ make writes to outdir → rootfs dir ──────────┘
                                                            │
                    ┌───────────────────────────────────────┘
                    │
                    ↓  CONVERGENCE POINT: validated rootfs directory
                    ↓
            ┌─ merge rootfs/ skeleton (if provided, overrides backend output)
            ├─ generate missing required files (os-release, service unit)
            ├─ validate contents
            ├─ chown 0:0 -R
            ├─ embed package.yaml at /usr/share/<name>/package.yaml
            ├─ create squashfs (pure Go, zstd)
            ├─ compute dm-verity (pure Go: hash tree + roothash)
            ├─ sign roothash with PKCS7 (pure Go: go.mozilla.org/pkcs7)
            ├─ create DDI: GPT(root + verity + signature partitions)
            │   set partition UUIDs from roothash (first/last 128 bits)
            │   write signature partition JSON: {rootHash, signature, certificateFingerprint}
            └─ output: <name>_<version>_<arch>.raw + <name>_<version>_<arch>.json
```

### Skeleton feature

An optional `rootfs/` directory in the project, merged into the backend output
**after** the backend runs. Skeleton files override backend output. This lets
developers provide custom configs, service units, or anything else that should
take precedence over what the backend built.

Works identically across all backends — buildctl handles the merge, not the
backend.

### Auto-generated required files

buildctl generates any **missing** required files:

| File | Generated from | Condition |
|---|---|---|
| `/etc/os-release` | package.yaml (`name`, `version`) | Always generated if missing; validated if present |
| `/usr/lib/systemd/system/<name>.service` | package.yaml (`command` field) | Generated if missing AND `command` is set |
| `/usr/share/<name>/package.yaml` | Always embedded by buildctl | Always |

If the developer provides a service unit (in `rootfs/` or backend output), it
takes precedence. `command` is ignored. Developer has full control when they
want it.

---

## 8. What Changed from Original Design

### Eliminated

| Original component | Why eliminated |
|---|---|
| 5-file package format | Replaced by DDI (UAPI standard) |
| Custom PKCS7 verification in appctl | systemd does it natively via `verity.d/` |
| Custom dm-verity setup (losetup + veritysetup) | systemd-dissect handles it natively |
| Companion file naming convention (`.roothash`, `.p7s`, `.verity`) | Everything inside the DDI |
| `/data/config/keys/` cert storage | Replaced by `/etc/verity.d/` (standard systemd path) |
| `/data/offline-lab/packages.db` | Replaced by `/var/lib/appctl/packages.db` (FHS) |
| All `/data/` hardcoded paths | Replaced by standard FHS paths; OS uses bind mounts |

### Simplified

| Original | Simplified to |
|---|---|
| appctl install: 16 steps including manual verity setup | ~9 steps; verity is one `portablectl attach` call |
| appctl needs `go.mozilla.org/pkcs7` for runtime | Only buildctl needs PKCS7 (build-time signing) |
| 2-tool PKCS7 code (sign in buildctl, verify in appctl) | Sign in buildctl only; verify is systemd native |
| Custom verity library in appctl | Not needed; systemd handles verity |

### Kept (unchanged)

| Component | Why kept |
|---|---|
| Pure-Go squashfs in buildctl | Still needed to create the root partition filesystem |
| Pure-Go dm-verity computation in buildctl | Still needed to create the verity partition |
| Pure-Go PKCS7 signing in buildctl | Still needed to create the signature partition |
| Per-app uid allocation (sysusers) | appctl owns this for portable mode; nspawn uses namespace isolation |
| Storage namespacing | appctl owns `/var/lib/appctl/apps/<hash>/<name>/` |
| Lifecycle hooks | appctl manages pre/post start/update/remove |
| Resource checks | appctl checks before install |
| Drop-in generation (User=, Group=, BindPaths=) | appctl generates at install time (portable mode) |
| Repo model (signed index, offline-capable) | Full model from the start; buildctl publishes, appctl downloads |
| 2-key signing model (build key + index key) | Unchanged; protects multi-publisher distribution |

---

## 9. Open Standards References

| Spec | Title | How we use it |
|---|---|---|
| [UAPI.2](https://uapi-group.org/specifications/specs/discoverable_partitions_specification/) | Discoverable Partitions Specification | Partition type UUIDs for root/verity/signature; verity signature partition JSON format |
| [UAPI.3](https://uapi-group.org/specifications/specs/discoverable_disk_image/) | Discoverable Disk Images | DDI format: GPT + DPS partitions + dm-verity; naming convention (`.raw`, `_` version separator) |
| [UAPI.11](https://uapi-group.org/specifications/specs/file_hierarchy_for_the_verification_of_os_artifacts/) | VOA (Verification of OS Artifacts) | Future cert storage hierarchy; `verity.d/` is the current implemented precursor |
| systemd `verity.d/` | Userspace dm-verity cert verification | Implemented in `src/shared/dissect-image.c`; `validate_signature_userspace()` function |

---

## 10. Thinnest POC

A service that prints "hello world" every second. Minimal files, no volumes,
no ports, no devices, no repo.

### Developer side

```
hello/
  package.yaml
  build.sh
```

**package.yaml:**
```yaml
name: hello
version: 1.0.0
arch: arm64
description: Hello world service
publisher: test
command: /usr/bin/hello.sh
```

**build.sh:**
```bash
#!/bin/bash
set -eu
out="$1"
mkdir -p "$out/usr/bin"
cat > "$out/usr/bin/hello.sh" << 'EOF'
#!/bin/bash
while true; do
  echo "hello world"
  sleep 1
done
EOF
chmod +x "$out/usr/bin/hello.sh"
```

### What buildctl does

1. Run `build.sh /tmp/buildctl-xxx/` → rootfs has `/usr/bin/hello.sh`
2. No `rootfs/` skeleton → skip merge
3. Missing `/etc/os-release` → generate `ID=hello\nVERSION_ID=1.0.0`
4. Missing service unit → generate `/usr/lib/systemd/system/hello.service` from `command`
5. Validate (os-release matches, service unit exists, no User=/Group= in unit)
6. `chown 0:0 -R`
7. Embed package.yaml at `/usr/share/hello/package.yaml`
8. Create squashfs
9. Compute dm-verity (hash tree + roothash)
10. Sign roothash with PKCS7
11. Create DDI (GPT: root squashfs + verity + signature partitions)
12. Generate metadata JSON
13. Output: `hello_1.0.0_arm64.raw` + `hello_1.0.0_arm64.json`

### What the operator does

```
# Copy build cert to verity.d/
cp build-cert.crt /etc/verity.d/hello-build.crt

# Attach the DDI
portablectl attach hello_1.0.0_arm64.raw

# Start the service
systemctl start hello.service
```

systemd-dissect handles: partition discovery, verity setup, userspace signature
verification via `verity.d/`, squashfs mount, service unit discovery.

`journalctl -u hello` shows "hello world" every second.

### No repo needed for first POC test

The thinnest POC tests the core DDI + verity + portablectl flow from a local
file. The repo layer (index, signing, key exchange) is implemented as part of
v1 but can be tested separately once the basic attach + verity works.

---

## 11. Resolved Open Items

### 11.1 Two-tool split: keep, with shared schema module

**Decision: keep buildctl and appctl as separate binaries.**

After the DDI shift, the tools share very little code:
- Package metadata structs (package.yaml, metadata JSON)
- Repo index format structs
- That's the extent of the overlap

buildctl is heavy (GPT/DDI creation, squashfs writing, verity computation, PKCS7
signing, multiple build backends, repo publishing). appctl is lighter (repo
management, uid allocation, storage namespacing, drop-in generation, lifecycle
hooks, rehydration, dual runtime management).

They run in completely different environments (workstation vs device), have
completely different dependencies, and communicate through a standard format
(DDI + metadata JSON).

A shared `pkg/schema` Go module handles the struct overlap without forcing a
monolithic binary.

### 11.2 Repo model: full model from the start

**Decision: implement the full repo model in v1.**

Not staged. The full model includes:
- Root index.json (keys[] + arches[], signed by index key)
- Per-arch index.json (latest version per package, signed by index key)
- 2-key signing model (build key + index key)
- Same-server rule (zip_url and metadata_url must resolve to same origin as base_url)
- Key rotation infrastructure (signing_key_id field, option A gradual rotation)
- Concurrent publisher flock on repo host

Rationale: the repo model is the distribution layer. Without it, the ecosystem
can't function. Building it from the start avoids a painful migration later.

### 11.3 Inter-app communication: deferred to later session

**Decision: defer to a dedicated design session.**

Constraints established:
- **No shared volumes** — apps must NEVER access each other's data directories.
  This is a hard security constraint, not a preference.
- **Disco integration** — the plan is to use disco (local network discovery
  daemon) for inter-app service discovery eventually.
- Deferred because: the ecosystem needs to exist before apps need to find each
  other. This is a Phase 2 concern that deserves its own design session.

### 11.4 Dual runtime mode: portable + nspawn in v1

**Decision: support both runtime modes from v1. Declared by packager, not operator.**

The same DDI works with both modes because systemd-nspawn uses the **same
dissect-image.c code** as portablectl. Same GPT parsing, same verity setup, same
userspace PKCS7 verification via `verity.d/`. The cert placed at repo-add time
works for both modes with zero changes.

#### Runtime declaration in package.yaml

```yaml
runtime: portable    # default — portablectl attach, RootImage=, systemctl managed
# or
runtime: nspawn      # systemd-nspawn --image=, machinectl managed

# Optional nspawn-specific config (ignored when runtime: portable)
network: host        # host (default) | private | none
```

The `runtime` field flows through to the metadata JSON. appctl reads it at
install time and selects the appropriate Runtime implementation.

#### Runtime abstraction in appctl

```go
type Runtime interface {
    Attach(imagePath string, meta *schema.Metadata, uid int) error
    Detach(name string) error
    Start(name string) error
    Stop(name string) error
    IsRunning(name string) (bool, error)
    Rehydrate(meta *schema.Metadata) error
}
```

Two implementations:

| | PortableRuntime | NspawnRuntime |
|---|---|---|
| Attach | `portablectl attach <ddi.raw>` | Generate `/etc/systemd/nspawn/<name>.nspawn` |
| Drop-in/config | `.service.d/99-appctl.conf` with `RootImage=`, `User=`, `BindPaths=` | `.nspawn` with `Bind=`, `RootHash=` |
| Start | `systemctl start <name>.service` | `systemctl start systemd-nspawn@<name>` |
| Stop | `systemctl stop <name>.service` | `systemctl stop systemd-nspawn@<name>` |
| Status | `systemctl status <name>` | `systemctl status systemd-nspawn@<name>` |
| Rehydrate | portablectl attach + regenerate drop-in + enable | systemctl enable systemd-nspawn@<name> |
| Isolation | Per-app uid + security profile | PID/mount/network namespace |
| User inside service | `app6000` (allocated by appctl) | root (namespace provides isolation) |
| Storage binds | `BindPaths=` in drop-in | `Bind=` in `.nspawn` file |
| Network | Host (profile can restrict) | Configurable: host, private, none |
| Verity | systemd-dissect via `RootImage=` | systemd-dissect via `--image=` |
| Boot overhead | Minimal (just a different root) | Slightly heavier (namespace setup) |

#### Why nspawn is cheaper than it sounds

Both modes use the same DDI and the same systemd-dissect internals:

```
DDI (.raw with root + verity + signature partitions)
    │
    ├── runtime: portable
    │   → portablectl attach <ddi.raw>
    │   → systemd-dissect processes partitions
    │   → verity.d/ cert verification
    │   → RootImage= in drop-in → systemctl manages
    │
    └── runtime: nspawn
        → systemd-nspawn --image=<ddi.raw>
        → systemd-dissect processes partitions (SAME code path)
        → verity.d/ cert verification (SAME mechanism)
        → .nspawn config → systemctl manages
```

The shared components (repo, download, DDI staging, cert management, verity,
storage dirs, DB) are identical. Only the `Runtime` implementation differs — and
that's a clean interface boundary.

#### Why packager decides, not operator

Some apps genuinely require a specific mode:
- An app expecting to be PID 1 only works with nspawn
- An app needing host D-Bus only works as a portable service

The packager knows the app's requirements. The operator can't override in v1.

---

## 12. Concrete Workflow

### Phase 0: One-time setup (publisher)

**On the build machine:**
```
# Generate build keypair (signs DDI signature partitions)
buildctl key generate --name myrepo
→ myrepo.key (private, never leaves this machine)
→ myrepo.crt (public cert, published to repo)
```

**On the repo host:**
```
# Generate index keypair (signs index files)
buildctl key generate --name myrepo-index --index
→ myrepo-index.key (private, stays on repo host)
→ myrepo-index.crt (public cert)

# Publish build cert to repo
cp myrepo.crt /var/www/packages/keys/signing-<key-id>.crt

# Configure repo
cat > /var/www/packages/repo.yaml << EOF
repo_path:  /var/www/packages
base_url:   https://packages.example.com
repo_name:  My Packages
index_key:  ./keys/myrepo-index.key
index_cert: ./keys/myrepo-index.crt
EOF

# Bootstrap the root index (keys + arches)
buildctl index generate /var/www/packages
→ writes index.json + index.json.p7s (signed with index key)
→ writes packages/<arch>/index.json + .p7s for each arch
```

### Phase 1: Developer builds and publishes

```
myapp/
  package.yaml
  Dockerfile              ← or mkosi.conf / build.sh / Makefile
  rootfs/                 ← optional skeleton (overrides backend output)
    etc/mosquitto/mosquitto.conf
```

```yaml
# package.yaml
name: mosquitto
version: 2.0.18
arch: arm64
description: MQTT message broker
publisher: offline-lab
homepage: https://mosquitto.org
license: EPL-2.0
runtime: portable          # or nspawn
command: /usr/sbin/mosquitto
ports:
  - port: 1883
    protocol: tcp
    expose: true
volumes:
  config: /etc/mosquitto
  data: /var/lib/mosquitto
resources:
  moderate:
    cpu_percent: 5
    memory_mb: 32
    storage_mb: 10
```

```bash
# Build (auto-detects Dockerfile, produces DDI)
buildctl build --key ~/keys/myrepo.key
→ ./dist/mosquitto_2.0.18_arm64.raw    (DDI: root + verity + signature)
→ ./dist/mosquitto_2.0.18_arm64.json   (metadata)

# Validate the built image (optional but recommended)
buildctl validate image ./dist/ --cert ~/keys/myrepo.crt

# Publish to repo (rsync files + update index via SSH)
buildctl publish ./dist/ --repo user@repo.example.com:/var/www/packages
→ rsyncs DDI + metadata to packages/arm64/mosquitto/2.0.18/
→ SSHes to repo host, runs: buildctl index update
→ index key signs the updated per-arch index + root index
```

### Phase 2: Operator installs on device

```bash
# Add the repo (one-time per repo)
appctl repo add https://packages.example.com --name myrepo
→ fetches root index.json + index.json.p7s
→ verifies index signature with index cert (trust-on-first-use)
→ fetches build cert from keys/signing-<key-id>.crt
→ stores build cert at /etc/verity.d/myrepo-<key-id>.crt
→ fetches per-arch index for this device's arch
→ caches package entries in packages.db

# Search
appctl search mqtt
→ mosquitto  2.0.18  MQTT message broker  [myrepo]

# Install
appctl install mosquitto
→ finds mosquitto in package cache
→ resource check (memory, storage available?)
→ downloads mosquitto_2.0.18_arm64.zip
→ extracts DDI + metadata
→ stages DDI to /var/lib/appctl/images/<uuid>/
→ reads runtime mode from metadata (portable or nspawn)
→ allocates uid (portable mode only), writes sysusers snippet
→ creates /var/lib/appctl/apps/myrepo-hash/mosquitto/{config,data}/
→ attaches via the appropriate Runtime:
    portable: portablectl attach + drop-in (User=, BindPaths=, RootImage=)
    nspawn:   .nspawn file (Bind=, RootHash=) + enable systemd-nspawn@<name>
→ systemctl start <name>.service  (or systemd-nspawn@<name>)
→ service running, verity-protected, signature-verified
```

### Phase 3: Ongoing management

```bash
# List installed
appctl list
→ mosquitto  2.0.18  running  portable  [myrepo]

# Update
appctl update mosquitto
→ downloads new version, verifies, swaps attachment, restarts
→ old version retained for rollback

# Rollback
appctl rollback mosquitto

# Remove
appctl remove mosquitto
→ data retained unless --purge

# Refresh repo index
appctl repo refresh
```

### Phase 4: Boot rehydration

```bash
# At boot (appctl-rehydrate.service)
appctl rehydrate
→ for each installed package:
    read runtime mode from metadata
    portable: portablectl attach + regenerate drop-in + enable
    nspawn:   systemctl enable systemd-nspawn@<name> (already persistent)
→ all services restored
```

---

## 13. v1 Scope

### In scope for v1

| Component | Notes |
|---|---|
| DDI build pipeline (Docker backend first) | Core value — produces signed DDI from source |
| mkosi backend | First-class from start (systemd ecosystem native) |
| shell/make backends | Simple backends for packages without Docker |
| PKCS7 signing + DDI creation (GPT) | The package format |
| Repo model (full: 2-key, per-arch index) | Distribution layer from the start |
| `buildctl key generate`, `publish`, `index update/generate` | Publisher tooling |
| `appctl repo add/list/remove/refresh` | Repo management + cert import to `verity.d/` |
| `appctl search` | Search cached index |
| `appctl install/remove/list` | Core lifecycle |
| Dual runtime: portable + nspawn | Both modes in v1; packager declares |
| `portablectl`/`systemd-nspawn` integration | systemd handles verity natively |
| Per-app uid allocation (portable mode) | Isolation via sysusers |
| Storage namespacing | `/var/lib/appctl/apps/<hash>/<name>/` |
| Drop-in / .nspawn generation | Per-runtime-mode config |
| Rehydration | Boot recovery for both runtime modes |
| Metadata JSON | Package contract between tools |
| Lifecycle hooks | pre/post start/update/remove |
| Resource checks | Pre-install validation |
| `appctl update/rollback` | Version management |
| Image retention | Default 3 per app for rollback |
| `buildctl new` | Template generation |
| `buildctl validate` | Project + image validation |

### Deferred (Phase 2+)

| Component | Why deferred |
|---|---|
| Inter-app communication / discovery | Needs dedicated design session; disco integration |
| `appctl compose` | Multi-app bundles; depends on inter-app design |
| `appctl exec` | nspawn ad-hoc command execution |
| configctl | Unified host config DSL |
| Key rotation workflow | Format supports it; operational workflow deferred |
| Strip optimization | Build-time binary stripping; needs careful lib detection |
| `repo pause/block` | Administrative; not needed for single-publisher v1 |
| Operator runtime override | Packager declares in v1; override is future |
| sysext/confext management | Already handled by boxctl; not an appctl concern |

---

## 14. Next Steps

Items remaining for implementation:

1. **GPT creation in pure Go** — **RESOLVED.** Use `github.com/diskfs/go-diskfs`
   (MIT, pure Go, v1.9.3, 24 importers). Provides `Table.Write()` and
   `Partition.WriteContents()`. Root partition type constants included
   (`LinuxRootArm64`, `LinuxRootX86_64`, etc.). Verity and verity-sig partition
   types are defined as string constants from the DPS spec. Works with image
   files on macOS.
2. **Test: portablectl attach with DDI** — confirm the full verity + signature
   verification flow works on a real systemd system
3. **Test: systemd-nspawn --image= with DDI** — confirm nspawn uses the same
   verity.d/ verification path
4. **Update existing specs** — migrate `docs/specs/` from 5-file format to DDI;
   update paths from `/data/` to FHS standard
5. **Design `pkg/schema` module** — shared Go structs for package.yaml, metadata
   JSON, repo index formats
6. **Design the buildctl backend interface** — formalize the Backend contract
   (Detect, Build, RequiredDeps, Templates)
7. **Inter-app communication design session** — dedicated session for disco
   integration and service discovery (no shared volumes)
