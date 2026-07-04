# Rejected Approaches

Design approaches that were considered and rejected, with the reason. Preserved to
prevent re-litigating settled questions.

Each record states: what was proposed, why it was considered, and why it was rejected.

| Record | Approach rejected | Replaced by |
|---|---|---|
| [kernel-keyring.md](kernel-keyring.md) | Kernel keyring for signing verification | systemd-native userspace PKCS7 via `/etc/verity.d/` |
| [systemd-homed.md](systemd-homed.md) | systemd-homed for per-app home dirs | sysusers + mkdir + chown |
| [shared-uid.md](shared-uid.md) | Single uid 6000 shared across all apps | Per-app dynamic uid allocation |
| [monolithic-cli.md](monolithic-cli.md) | Single `offline-lab` CLI binary | Three separate tools (boxctl, appctl, buildctl) |
| [portablectl-verity.md](portablectl-verity.md) | Belief portablectl handles verity natively | DDI format so systemd verifies natively (not appctl) |
| [index-sign-cmd.md](index-sign-cmd.md) | `buildctl index sign` as standalone command | Signing integrated into `index update` / `index generate` |
| [early-db-schema.md](early-db-schema.md) | Early 2-table DB schema | File-per-record JSON state (ADR-0026) |
| [verity-in-metadata.md](verity-in-metadata.md) | Verity root hash embedded in metadata JSON | Roothash + signature in the DDI signature partition |
| [iptables-refs.md](iptables-refs.md) | iptables references in schemas/docs | nftables (`offlinelab-firewall` package) |
