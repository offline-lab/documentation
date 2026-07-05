# Schemas

Machine-readable schemas for all Offline Lab data formats. Implementors of appctl,
buildctl, or compatible tooling should validate against these.

---

## The manifest (DDI metadata)

| Schema | Format | Description |
|---|---|---|
| [package-yaml.schema.json](schemas/package-yaml.schema.json) | JSON Schema | `package.yaml` — the manifest, embedded in every image (ADR-0017/0038); the **only** package metadata (the pre-pivot standalone metadata JSON is gone). Fields pending T101 (`expose`/`devices`/`resources` etc.) are deliberately absent. |

Field semantics: [App contract](specs/app-contract.md); wire format:
[Package Format](specs/package-format.md).

---

## Index formats

| Schema | Format | Description |
|---|---|---|
| [index-manifest.schema.json](schemas/index-manifest.schema.json) | JSON Schema | The signed root manifest of an index: identity key, classes, distributed certs, `version`/`published_at` anti-rollback pair. |
| [index-catalog.schema.json](schemas/index-catalog.schema.json) | JSON Schema | Per-class per-arch catalog: latest-only entries projected from verified embedded manifests at `index add`. |

See the [Index contract](specs/index-contract.md) for the directory layout, signing model, and client flow.

---

## On-device state

| Schema | Format | Description |
|---|---|---|
| [on-device-state.md](schemas/on-device-state.md) | Markdown + JSON examples | File-per-record JSON layout under `/var/lib/appctl/state/` (repos, packages, bases, images, locks). Replaces the earlier SQLite design. |

---

## Host resource baseline

| Schema | Format | Description |
|---|---|---|
| [resources.schema.json](schemas/resources.schema.json) | JSON Schema | `/var/lib/appctl/resources.json`: host resource baseline written at boot by `offlinelab-resources.service` |

See [Resource Tracking](specs/resource-tracking.md) for how appctl uses this file for pre-install capacity checks.
