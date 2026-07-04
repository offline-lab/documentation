# Publish to a repository

A repository is a static directory served over HTTP, HTTPS, or `file://`. buildctl maintains the canonical package layout, the per-arch indexes, the root index, and the index signatures. The repo can live on the same machine as buildctl, or on a remote host reached by rsync/SSH; buildctl only needs a filesystem path.

For the on-device consumption model and how appctl verifies repo indexes, see the [Offline Lab repository specification](https://offline-lab.com/docs/specs/repository/).

## Repository layout

```
<repo>/
  index.json                    ← root index: repo name, base URL, signing keys, arch listing
  index.json.p7s                ← detached PKCS7 over index.json (signed with the index key)
  keys/
    signing-<key-id>.crt        ← build certificates, named by their SHA-256 fingerprint
  packages/
    <arch>/
      index.json                ← per-arch index: latest version of every package for this arch
      index.json.p7s
      <name>/<version>/
        <name>_<version>_<arch>.raw
        <name>_<version>_<arch>.json
```

`<key-id>` is the lowercase hex SHA-256 of the DER-encoded certificate. This matches `certificateFingerprint` in the DDI signature partition and `signing_key_id` in the metadata.

## Set up the repo host

On the machine that will host the repo, generate an index keypair. The index key signs every `index.json` after each publish. It is lower trust than a build key: a compromised index key can hide or reorder packages but cannot forge package signatures, because systemd always verifies the DDI signature partition at install time.

```bash
buildctl key generate --name myrepo-index --index --out ./keys
```

Copy the matching `.crt` to the build machine if you want buildctl to sign indexes during publish. Otherwise signing is a separate step on the repo host.

## Add a package to the repo

From a `dist/` directory produced by `buildctl build`:

```bash
buildctl index add <repo-path> \
  --from ./dist \
  --sign-key ./keys/myrepo-index.key
```

buildctl:

1. Loads the metadata JSON from `--from`, derives the canonical package path (`packages/<arch>/<name>/<version>/`), and copies the `.raw` and `.json` files there.
2. Rebuilds the per-arch index by scanning every package directory and picking the latest version per name (semver comparison).
3. Rebuilds the root index (arch listing, signing keys discovered in `keys/`).
4. Signs every `index.json` (root + per-arch) with the index key and writes `index.json.p7s` alongside each.

The build key's public certificate should already be in `<repo>/keys/` so devices can verify DDI signatures. buildctl does not move it there automatically; copy it once when bootstrapping the repo:

```bash
cp ./keys/mykey.crt <repo>/keys/signing-<fingerprint>.crt
```

## Rebuild all indexes from scratch

After bootstrapping a repo, after rotating the build key, or after manually adding or removing packages outside `index add`, regenerate every index:

```bash
buildctl index generate <repo-path> \
  --name "My repo" \
  --base-url https://packages.example.com \
  --sign-key ./keys/myrepo-index.key
```

This walks `packages/<arch>/` for every arch present, writes a fresh `index.json` for each, and writes the root index. Pass `--name` and `--base-url` to populate the corresponding fields in the root index; both are informational and consumed by clients for display and relative-URL resolution.

## Incremental vs. full

`index add` is incremental: it scans one arch (the one named in the metadata you are adding) plus the root. It does not require all packages to be present locally. Use it for the normal publish workflow.

`index generate` is full: it scans every arch. Use it when bootstrapping, after out-of-band changes, or when the root index is corrupt.

