# ADR-0022 — Firewall: nftables (inet family)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-06-16 |
| **Deciders** | Offline Lab core team |
| **Supersedes** | None |

## Context

The OS needs a host firewall. Linux has two incumbent packet-filtering
frameworks: the legacy `iptables` and its successor `nftables`. `nftables`
provides a unified `inet` family ruleset covering both IPv4 and IPv6, and is
the modern default across current distributions. Any specification or schema
in this project that still mentions "iptables" is stale.

## Decision

The OS uses **nftables** with an `inet` family ruleset.

Whether appctl manages per-app nftables rules at install time is not yet
decided.

## Consequences

- Documentation and tooling must standardize on nftables; references to
  "iptables" are documentation errors to be corrected.
- IPv4 and IPv6 rules are unified under one `inet` ruleset.
- Per-app firewall management by appctl remains an open question.

## Alternatives considered

### iptables

Rejected. Legacy; superseded by nftables. Modern distributions default to
nftables, and the `inet` family avoids maintaining separate v4/v6 rulesets.

## References

- Original discussion: internal (not published).
