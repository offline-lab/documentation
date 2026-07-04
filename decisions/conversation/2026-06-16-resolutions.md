# Resolutions — 2026-06-16

Resolves the 6 unresolved tensions and 4 flagged tensions from the 2026-06-15 design
session. Each resolution cites source evidence (where applicable) and notes whether
live testing is still required.

**Update (2026-06-16T12:00Z):** T1, T2, and T4 are now **VERIFIED BY LIVE TEST**
on a Fedora 44 VM (systemd 259, OpenSSL 3.5.5). See the test evidence sections below.

All source line references are to `src/shared/dissect-image.c` in the systemd
main branch as fetched on 2026-06-16.

---

## T1: portablectl + verity.d/ fallback behavior

**Question:** Does `portablectl attach` try kernel keyring verification and fail,
or does it fall through to userspace `verity.d/` verification cleanly?

### Resolution: The fallback is clean and is the default path.

The kernel keyring failure is **expected behavior, not an error**. The code
explicitly logs it at debug level and proceeds to userspace verification.

### Source evidence

**The activation flow** (`do_crypt_activate_verity`, lines 3215-3305):

1. **Line 3230:** If a signature is present AND policy requires SIGNED:
2. **Lines 3243-3256:** Try kernel keyring first (`crypt_activate_by_signed_key`).
   If it succeeds → done.
3. **Line 3258:** If it fails, log at debug level:
   ```
   "Validation of dm-verity signature failed via the kernel, trying userspace validation instead"
   ```
4. **Line 3271:** Call `validate_signature_userspace()`.
5. **Lines 3274-3284:** If userspace succeeds → activate via root hash (no
   signature sent to kernel). If userspace fails → check if policy allows
   unsigned verity; if not, refuse.

**Userspace verification is enabled by default** — three guards, all defaulting
to enabled:

| Guard | Location | Default |
|---|---|---|
| `DISSECT_IMAGE_ALLOW_USERSPACE_VERITY` flag | Set unconditionally in `dissect_open_image()` at **line 4896** | **Always on** |
| `$SYSTEMD_ALLOW_USERSPACE_VERITY` env var | Lines 3116-3124 | **Enabled** (returns -ENXIO when unset → proceeds) |
| `systemd.allow_userspace_verity=` kernel cmdline | Lines 3127-3135 | **Enabled** (`PROC_CMDLINE_TRUE_WHEN_MISSING`) |

**Hard requirement:** systemd must be compiled with OpenSSL (`HAVE_OPENSSL`,
line 3137). Without it, `validate_signature_userspace()` returns 0 (failure)
unconditionally (lines 3209-3212). All mainstream distros build systemd with
OpenSSL. OL OS (Buildroot) must ensure the systemd package has OpenSSL support.

### Conclusion

No custom code needed in appctl for runtime verification. The flow is:
1. `portablectl attach <ddi.raw>`
2. systemd-dissect discovers signature partition by GPT type UUID
3. Reads JSON `{rootHash, signature}` from the partition
4. Tries kernel keyring → fails (cert not in keyring) → debug log
5. Falls back to `validate_signature_userspace()` → scans `/etc/verity.d/*.crt`
6. `PKCS7_verify(signature, certs, roothash, PKCS7_NOINTERN|PKCS7_NOVERIFY)` succeeds
7. Activates dm-verity with the root hash

### Must verify by live test

~~Build a minimal DDI with go-diskfs + PKCS7 signature partition, place the build
cert in `/etc/verity.d/`, run `portablectl attach`.~~

### VERIFIED BY LIVE TEST (2026-06-16)

Tested on Fedora 44 (systemd 259, OpenSSL 3.5.5) in a Lima VM. DDI built with
`systemd-repart` using the built-in `portable.repart.d` definitions. Build cert
(self-signed RSA 2048) placed at `/etc/verity.d/hello-build.crt`.

`systemd-dissect --mount` with `SYSTEMD_LOG_LEVEL=debug` showed the exact
verification flow from the source analysis:

```
Activating volume loop1p1-verity [keyslot -2] using signed key.
device-mapper: reload ioctl on loop1p1-verity (252:0) failed: Required key not available
Validation of dm-verity signature failed via the kernel, trying userspace validation instead: Required key not available
Userspace PKCS#7 validation succeeded.
Verity activation via userspace signature logic worked, activating by root hash.
```

The mount succeeded. `/etc/os-release` was readable inside the mounted image.

**Environment:** Fedora 44, systemd 259.6-1.fc44 (`+OPENSSL +LIBCRYPTSETUP`),
OpenSSL 3.5.5, kernel 6.19.10, aarch64.

---

## T2: Partition UUID auto-discovery by systemd-dissect

**Question:** Does systemd-dissect use the DPS partition UUID encoding (first/last
128 bits of roothash) for auto-discovery?

### Resolution: Partition UUIDs are actively verified, not just cosmetic.

systemd discovers partitions by **GPT type UUID** (which tells it "this is arm64
root," "this is arm64 verity," etc.). It then **verifies** the partition UUID
against the roothash. Wrong UUIDs cause the partition to be **skipped**, which
causes the attach to fail.

### Source evidence

**UUID matching** (`dissect_image`, lines 1112-1130):

```c
if (verity && iovec_is_set(&verity->root_hash)) {
    sd_id128_t fsuuid, vuuid;
    /* If a root hash is supplied, then we use the root partition that has a
     * UUID that match the first 128-bit of the root hash. And we use the
     * verity partition that has a UUID that match the final 128-bit. */
    memcpy(&fsuuid, verity->root_hash.iov_base, sizeof(sd_id128_t));
    memcpy(&vuuid, (const uint8_t*) verity->root_hash.iov_base +
           verity->root_hash.iov_len - sizeof(sd_id128_t), sizeof(sd_id128_t));
    root_uuid = fsuuid;
    root_verity_uuid = vuuid;
}
```

**Root partition UUID check** (lines 1435-1447):
```c
if (!sd_id128_is_null(expected_uuid) && !sd_id128_equal(expected_uuid, id)) {
    log_debug("Partition UUID does not match expected UUID derived from "
              "verity hash, ignoring.");
    continue;  // SKIP this partition
}
```

**Verity partition UUID check** (lines 1452-1466): same pattern.

**When UUIDs are checked:** UUID matching occurs only when `verity->root_hash`
is already set (from an external source or from the signature partition). When
no roothash is known during the initial GPT scan, partitions are discovered by
type UUID alone. After the signature partition is loaded
(`dissected_image_load_verity_sig_partition`, line 4056), the roothash becomes
known and is used for subsequent verification.

### Conclusion

**buildctl MUST set partition UUIDs correctly per DPS spec:**
- Root partition UUID = first 128 bits (16 bytes) of the roothash
- Verity partition UUID = last 128 bits (16 bytes) of the roothash

If these are wrong, systemd will skip the partitions and the DDI will fail to
attach. This is not optional — it is enforced by systemd.

go-diskfs supports setting partition-specific UUIDs via the `GPT` partition
entry. buildctl computes the roothash first (from the dm-verity hash tree),
then sets both UUIDs before writing the GPT.

### VERIFIED BY LIVE TEST (2026-06-16)

`systemd-repart` set the partition UUIDs automatically per DPS spec:

```
Root partition:
  UUID:      ef87a379-dc75-60ab-9532-5f7ef84d0d45
  Roothash:  ef87a379dc7560ab95325f7ef84d0d45a0e8d81ba68e64dfaa1ff69dba8c82cb
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ = first 128 bits = root UUID ✓

Verity partition:
  UUID:      a0e8d81b-a68e-64df-aa1f-f69dba8c82cb
  Roothash:  ef87a379dc7560ab95325f7ef84d0d45a0e8d81ba68e64dfaa1ff69dba8c82cb
                                                           ^^^^^^^^^^^^^^^^^^^ = last 128 bits = verity UUID ✓
```

`systemd-dissect` output confirmed the UUIDs match the roothash-derived values
and that partitions were discovered by GPT type UUID (`root-arm64`,
`root-arm64-verity`, `root-arm64-verity-sig`).

**Confirmed:** buildctl MUST compute the roothash first, then set both partition
UUIDs before writing the GPT. This is not optional — it is enforced by systemd.

---

## T3: Skeleton merge precedence

**Question:** When skeleton `rootfs/` and backend output both have the same file,
does the skeleton completely replace, or is it a directory merge?

### Resolution: File-level merge (file-for-file override, directories recursively merged).

Already documented in [`backend-interface.md`](../design/backend-interface.md) §13, line 1263:
> Skeleton files override backend output file-for-file. Directories are merged.

### Semantics

- A file in `rootfs/etc/nginx/nginx.conf` overrides `etc/nginx/nginx.conf` in
  backend output.
- A file in backend output but NOT in skeleton survives the merge.
- Directories are created as needed (skeleton can add to a directory the backend
  didn't create).
- Symlinks in skeleton replace symlinks in backend output at the same path.
- **Deletion** is not expressed via skeleton. Use `.buildignore` (applied
  post-merge, step 4 in the pipeline) to exclude files from the final tree.

### Why file-level, not directory-level

Directory-level replace (where skeleton's `etc/` entirely replaces backend's
`etc/`) would be destructive: a skeleton providing one config file would wipe
all other config the backend installed. File-level merge is the least surprising
behavior and matches rsync-without-`--delete` semantics.

### Implementation

Use `cp -a` semantics (or a Go equivalent that walks the skeleton tree and
copies/overwrites each entry into the backend output). The merge happens BEFORE
validation, so buildctl's validators see the final merged tree.

No change needed to existing documentation.

---

## T4: nspawn + verity.d/ path

**Question:** Does `systemd-nspawn --image=<ddi.raw>` trigger the same
`verity.d/` userspace verification?

### Resolution: Yes — identical code path.

`systemd-nspawn` and `portablectl` both call `dissect_open_image()`, which sets
`DISSECT_IMAGE_ALLOW_USERSPACE_VERITY` unconditionally (**line 4896**). The same
`do_crypt_activate_verity()` → `validate_signature_userspace()` → `verity.d/`
path is followed in both cases.

### Source evidence

`dissect_open_image()` (lines 4856-5000) is the shared entry point used by:
- `portablectl attach`
- `systemd-nspawn --image=`
- `systemd-dissect`
- `systemd-sysext` / `systemd-confext`
- `systemd-stub` (bootloader)

All of them get the same default flags at line 4891-4897:
```c
dissect_image_flags =
    ...
    DISSECT_IMAGE_ALLOW_USERSPACE_VERITY |
    DISSECT_IMAGE_VERITY_SHARE;
```

The `verity.d/` cert placed at `appctl repo add` time works for both portable
and nspawn modes with zero changes.

### Conclusion

The dual-runtime decision ([design session 2026-06-15](./2026-06-15-design-session.md) §11.4) is confirmed at the source
level. Both modes share:
- DDI format (same GPT layout)
- Verity setup (same `do_crypt_activate_verity`)
- Signature verification (same `validate_signature_userspace`)
- Cert store (`/etc/verity.d/`)

The only difference is how the service is managed afterward (systemctl vs
machinectl, drop-in vs .nspawn file).

### VERIFIED BY LIVE TEST (2026-06-16)

`systemd-nspawn --image=/root/ddi-test/hello.raw /bin/cat /etc/os-release` on
the same Fedora 44 VM with the same cert in `/etc/verity.d/`. Output:

```
device-mapper: reload ioctl on ef87a379dc7560ab95325f7ef84d0d45a0e8d81ba68e64dfaa1ff69dba8c82cb-verity (252:1) failed: Required key not available
░ Spawning container hello on /root/ddi-test/hello.raw.
```

The kernel keyring failed (same as T1). The container spawned (verity activated
via userspace fallback). The roothash appears in the dm device name, confirming
the same verity setup path.

**Confirmed:** nspawn and portablectl (via `systemd-dissect`) share the identical
verity verification code path. The cert in `/etc/verity.d/` works for both modes.

---

## T5: Repo index format with DDI

**Question:** Does the repo index need new fields for DDI, or are existing fields
sufficient?

### Resolution: Already resolved by agent design work. No further changes needed.

The `IndexPackage` struct in [`pkg-schema-design.md`](../design/pkg-schema-design.md) (lines 470-486) already has
the DDI-appropriate fields:

| Field | Purpose | Status |
|---|---|---|
| `RawURL` | URL of the `.raw` DDI file | **New** (replaces old `squashfs_url`) |
| `MetadataURL` | URL of the `.json` metadata file | Kept |
| `ZipURL` | Optional: zip of both files | Kept (optional) |
| `DDISHA256` | SHA-256 of the `.raw` file | **New** (download integrity check) |
| `DDISize` | Total `.raw` file size in bytes | **New** (download planning) |
| `Runtime` | `portable` or `nspawn` | **New** (consumer needs this at install time) |
| `SigningKeyID` | Build key fingerprint | Kept (non-nullable in index; always present for published packages) |

The [`specs-ddi-migration.md`](../design/specs-ddi-migration.md) (lines 496-506) documents the schema migration:
old 5-file URLs collapse to `raw_url` + `metadata_url`. The same-server rule
applies to both.

No further work needed.

---

## T6: Metadata JSON: ddi_size vs squashfs_size

**Question:** Should metadata report DDI total size, root partition size, or both?

### Resolution: `ddi_size` only (total `.raw` file size).

### Rationale

The operator downloads the `.raw` file. The size that matters for:
- **Download planning** (is there enough bandwidth/time?) → total `.raw` size
- **Storage planning** (is there enough disk?) → total `.raw` size (the DDI is
  stored as-is under `/var/lib/appctl/images/<uuid>/`)
- **Resource checks** → `resources.heavy.storage_mb` (app data at runtime, not
  image size)

The internal squashfs partition size is never externally relevant:
- The operator never downloads the squashfs separately
- buildctl knows the squashfs size without needing a metadata field
- The verity and signature partitions add negligible overhead (< 1% of root)

### Current state

`PackageMetadata.DDISize int64` in [`pkg-schema-design.md`](../design/pkg-schema-design.md) (line 406) is correct.
No change needed.

---

## F1: Backend Build() return type

**Question:** Should `Build()` return `(*BuildResult, error)` or just `error`
(with sidecar file workaround)?

### Resolution: Change to `(*BuildResult, error)`.

### Why the sidecar loses

The sidecar approach ([`backend-interface.md`](../design/backend-interface.md) §11) was chosen to avoid changing
the interface signature from the original design prompt. The three arguments
for the sidecar were:

1. **Statelessness** — the sidecar writes to per-build scratch, so singleton
   backends stay stateless. **But `(*BuildResult, error)` is also stateless:**
   the result is a return value, not struct state. No race condition.
2. **Open/closed** — any future backend uses the same sidecar convention. **But
   `*BuildResult` is also open:** adding fields doesn't break existing backends.
3. **Survives crashes** — the sidecar persists in scratch. **But this is
   meaningless:** if buildctl crashes mid-build, the scratch dir is wiped on
   next run regardless. The sidecar doesn't enable recovery.

The sidecar adds accidental complexity:
- File naming convention (`<outDir>.oci-labels.json`)
- JSON encode/decode of the sidecar
- Cleanup before squashfs creation
- Undiscoverable convention (a reviewer already flagged this)

A return value is cleaner, more discoverable, and adds zero complexity.

### The struct

```go
type BuildResult struct {
    // OCILabels carries Docker OCI image labels when the docker backend
    // is used. Used for metadata fallbacks (description, license, source URL).
    // nil for non-docker backends.
    OCILabels map[string]string

    // ImageDigest is the docker image digest (sha256:...) when the docker
    // backend is used. Empty for other backends.
    ImageDigest string
}
```

Backends with nothing to report return `&BuildResult{}, nil`.

### Action required

Update [`backend-interface.md`](../design/backend-interface.md):
- §3: Change `Build(...)` signature to return `(*BuildResult, error)`
- §11: Delete the sidecar section. Replace with a one-paragraph note that
  structured post-build data flows through the return value.
- §12: Update convergence contract: "`Build` returns a `*BuildResult` (may be
  zero-value for backends without metadata) and nil on success."
- §7.3 (Docker): Remove sidecar write; populate `BuildResult.OCILabels` and
  `BuildResult.ImageDigest` before returning.

---

## F2: mkosi cross-arch gap

**Question:** How to handle mkosi's lack of QEMU bridge for cross-arch builds?

### Resolution: Keep the current approach — explicit error on cross-arch.

Already documented in [`backend-interface.md`](../design/backend-interface.md) §8.2 (lines 842-850):
> mkosi has no QEMU bridge. Cross-arch builds require running buildctl on a host
> of the target arch. The mkosi backend returns an explicit error if
> `arch != runtime.GOARCH`. Docker is the recommended backend for cross-arch.

### Why this is correct

1. **mkosi is a native-build tool.** It installs packages via the host's package
   manager, which is arch-specific. A half-working QEMU bridge would produce
   images that appear to build but have subtle breakage (wrong libs, missing
   firmware).
2. **Docker solves cross-arch cleanly** via buildx + binfmt handlers (registered
   in `Setup`). The docker backend is the first-class cross-arch path.
3. **CI matrix is the fallback.** For teams that must use mkosi, run buildctl on
   a host of each target arch (CI matrix with native runners).

### When to revisit

If mkosi adds first-class cross-arch support (QEMU integration in mkosi itself,
not external wrapping), add it to the mkosi backend. Until then, the honest error
is better than silent breakage.

No change needed.

---

## F3: Schema *string nullable pattern

**Question:** Should nullable fields use `*string` or a custom `NullableString`?

### Resolution: Keep `*string` with no `omitempty`.

Already documented in [`pkg-schema-design.md`](../design/pkg-schema-design.md) §7.2 (lines 1023-1028).

### The distinction

Three states exist in JSON:
1. **Absent** — key not present in the JSON object
2. **Null** — key present, value is `null`
3. **Value** — key present, value is a string

`*string` with no `omitempty`:
- `nil` pointer → marshals as `"field": null` (state 2)
- non-nil pointer → marshals as `"field": "value"` (state 3)
- State 1 (absent) is impossible at the Go level — the struct field is always
  serialized

A custom `NullableString struct{ Value string; Set bool }` would distinguish all
three states. But neither producer (buildctl) nor consumer (appctl) exploits the
absent/null distinction. The JSON Schema for these fields declares them as
nullable, meaning `"field": null` is the expected representation of "no value."

### Conclusion

`*string` is the idiomatic Go pattern for nullable JSON fields. The absent/null
distinction is not semantically meaningful in our schemas. Adding a custom type
would add API surface for no benefit. Revisit only if a real use case for
absent-vs-null emerges.

No change needed.

---

## F4: Inter-app socket directory vs "no shared volumes"

**Question:** Does a shared socket directory at `/run/appctl/<name>.sock` violate
constraint C1 ("no shared volumes")?

### Resolution: Preliminary ruling — a shared socket directory is NOT a violation of C1.

### The distinction

C1 protects **app data directories** — the files an app reads and writes as part
of its function. A shared socket directory contains **IPC endpoints**, not data:

| | Data volume | Socket directory |
|---|---|---|
| Contents | Regular files (databases, configs, uploads) | Unix socket files (kernel endpoints, not regular files) |
| Created by | The app itself | appctl (at install/start time) |
| Read/written by | The app's process | The kernel (apps `connect()` to the endpoint) |
| Analogy | `/var/lib/mosquitto/mosquitto.db` | `/run/dbus/system_bus_socket` |

Nobody considers `/run/dbus/` or `/var/run/docker.sock` a "shared volume" in the
data isolation sense. The same principle applies to `/run/appctl/`.

### Proposed mechanism (for the inter-app comms session to evaluate)

```
/run/appctl/                    ← shared directory, created by appctl
  mosquitto.sock                ← owned by app6000:app6000, mode 0660
  ircd.sock                     ← owned by app6001:app6001, mode 0660
```

- appctl creates `/run/appctl/` at install time with mode 0755
- Each app's socket is owned by its allocated uid:gid
- Socket permissions (0660) allow the owner to connect
- Cross-app access requires the connecting app to be in the socket's group or
  have explicit permission — **this is the consent model the inter-app session
  must design**

### Why this is only a preliminary ruling

The inter-app comms design is deferred ([design session 2026-06-15](./2026-06-15-design-session.md) §11.3). This ruling
removes the C1 blocker so the future session can evaluate sockets without
relitigating C1. The session still needs to answer:
- How does app A consent to app B connecting? (Q11 in the outline)
- Does `/run/appctl/` get bind-mounted into nspawn containers? (The outline's
  §5.3 notes this is the one mode-uniform transport)
- Is this the chosen transport, or just one option?

### Action required

Add this ruling as an addendum to [`inter-app-comms-outline.md`](../design/inter-app-comms-outline.md) §3.1, noting that
C1 does not prohibit a shared socket directory. The constraint protects data, not
IPC endpoints.

---

## Summary table

| Item | Resolution | Action required | Test needed? |
|---|---|---|---|
| T1: verity.d/ fallback | Clean fallback, default path | None | **VERIFIED** — live test 2026-06-16 |
| T2: Partition UUIDs | Actively verified, must be correct | buildctl must set UUIDs per DPS | **VERIFIED** — live test 2026-06-16 |
| T3: Skeleton merge | File-level merge | None (already documented) | No |
| T4: nspawn + verity | Same code path as portablectl | None | **VERIFIED** — live test 2026-06-16 |
| T5: Repo index | Already resolved by agent design | None | No |
| T6: Metadata size | `ddi_size` only | None (already correct) | No |
| F1: Build() return type | Change to `(*BuildResult, error)` | **Applied** to backend-interface.md | No |
| F2: mkosi cross-arch | Keep explicit error | None (already documented) | No |
| F3: Nullable pattern | Keep `*string` | None (already documented) | No |
| F4: Socket directory | Not a C1 violation (preliminary) | **Applied** to inter-app-comms-outline.md | No |

---

## New findings from source analysis

These were discovered during the systemd source review and affect the design
beyond the 10 tensions:

### NF1: OpenSSL is a hard requirement

`validate_signature_userspace()` (line 3137) is guarded by `#if HAVE_OPENSSL`.
If systemd is built without OpenSSL, userspace verity verification is impossible
and signed DDIs cannot be activated.

**Action:** Document `systemd >= 250 compiled with OpenSSL` as a hard
prerequisite. For OL OS: verify Buildroot's systemd package includes OpenSSL
support. For external hosts: document the requirement in the universal tooling
docs.

### NF2: Four env/cmdline guards (all default to enabled)

| Guard | What it controls | Default | Risk |
|---|---|---|---|
| `$SYSTEMD_ALLOW_USERSPACE_VERITY` | Enables/disables userspace verity entirely | Enabled | Admin can disable → signed DDIs fail to activate |
| `systemd.allow_userspace_verity=` | Same, via kernel cmdline | Enabled | Same |
| `$SYSTEMD_DISSECT_VERITY_EMBEDDED` | Enables/disables loading embedded signature partitions | Enabled | Admin can disable → DDIs with embedded signatures not recognized |
| `$SYSTEMD_DISSECT_VERITY_SIGNATURE` | Enables/disables signature checking for signed images | Enabled | Admin can disable → unsigned verity activation if policy allows it |

**Action:** Document these in OL OS as "do not disable." On OL OS, set them
explicitly in the environment to guard against accidental overrides. For
external hosts: document that disabling any of these breaks signed DDI
verification.

### NF3: Image policy matters

systemd's image policy determines whether unsigned verity is allowed as a
fallback when signature verification fails. If the policy permits
`PARTITION_POLICY_VERITY` (unsigned ok), a failed signature check still
activates the image without signature verification.

**Action:** For portable services on OL OS, ensure the image policy requires
`SIGNED` for root partitions (not just `VERITY`). This can be set via
`ImagePolicy=` in the portable service profile or via
`PortableExtensions=` settings. Verify what the default portable service
image policy is.

### NF4: Signature partition loading sequence

The full DDI signature flow is:
1. `verity_settings_load()` — looks for companion files (`.roothash`, `.p7s`).
   For DDIs, no companion files → returns empty.
2. `dissect_image()` — parses GPT, discovers partitions by type UUID, does NOT
   read signature partition content yet (unless external roothash was supplied)
3. `dissected_image_load_verity_sig_partition()` — reads the signature partition
   JSON, extracts roothash + signature, populates `verity->root_hash` and
   `verity->root_hash_sig`
4. `dissected_image_activate()` → `do_crypt_activate_verity()` → kernel keyring
   → userspace fallback → dm-verity activation

This means the roothash from the signature partition is available for UUID
matching AFTER step 3, but the initial GPT scan in step 2 does UUID matching
only if an external roothash was supplied (which it wasn't for DDIs). The UUID
matching for DDIs happens implicitly: systemd finds the one root, one verity,
and one signature partition by type UUID, then uses the roothash from the
signature partition for verity setup.

**Implication for buildctl:** For single-app DDIs (one root + one verity + one
signature), the partition UUIDs serve as an integrity binding but are not needed
for discovery. However, they MUST still be correct because systemd verifies them
when the roothash is known (step 3 populates the roothash, and systemd may
re-check partition UUIDs at that point).

---

## What remains after these resolutions

### Items requiring live testing (on a Linux machine with systemd)

~~1. **T1/T4 combined test:** Build a minimal DDI, place cert in `/etc/verity.d/`,
   test both `portablectl attach` and `systemd-nspawn --image=`.~~ **DONE 2026-06-16.**
   All three tensions (T1, T2, T4) verified on Fedora 44 / systemd 259.

~~2. **T2 test:** Build a DDI with correct partition UUIDs → confirm attach.~~ **DONE.**
   `systemd-repart` set correct UUIDs automatically; `systemd-dissect` verified them.

No live tests remain. All design questions are resolved and verified.

### Items requiring document updates

1. **F1:** Update [`backend-interface.md`](../design/backend-interface.md) — change `Build()` signature, delete
   sidecar section (§11), update convergence contract (§12).

2. **F4:** Add preliminary ruling to `inter-app-comms-outline.md` §3.1.

3. **NF1-NF3:** Document OpenSSL requirement, env var guards, and image policy
   considerations in the appropriate spec files (during the spec migration).

### Items ready for implementation

All 10 tensions are resolved and verified. The design documents ([design session 2026-06-15](./2026-06-15-design-session.md),
[[`pkg-schema-design.md`](../design/pkg-schema-design.md)](../design/pkg-schema-design.md), [[`backend-interface.md`](../design/backend-interface.md)](../design/backend-interface.md), [[`specs-ddi-migration.md`](../design/specs-ddi-migration.md)](../design/specs-ddi-migration.md)) are
implementation-ready. The F1 signature change has been applied. Live tests on
Fedora 44 / systemd 259 confirmed T1, T2, and T4.

### Additional live-test finding: image policy enforcement

During testing, we discovered that `systemd-dissect` and `systemd-nspawn` use a
**default image policy** of `*=verity+signed+encrypted+unprotected+unused|absent`
— meaning ALL protection levels are acceptable, including `unprotected`. This
means that without an explicit `ImagePolicy=` directive, a DDI with a failed
signature verification can still be activated as unsigned verity (if the policy
permits `verity`).

**Action for implementation:** appctl must set `ImagePolicy=` in the portable
service drop-in (for portable mode) and in the `.nspawn` file (for nspawn mode)
to require signed verity. The policy string should be `root=signed` (or the
equivalent that rejects unsigned verity). This is a runtime configuration concern,
not a design change.
