# Rejected: iptables References in Schemas and Docs

**Status:** Documentation errors — the OS uses nftables
**Replaced by:** nftables (`offlinelab-firewall` package, `inet` family ruleset)

---

## What was written

In an early Q&A round:

> "Firewall: iptables is fine."

This early statement was reflected in schema descriptions. The package-yaml and
package-metadata JSON schemas describe the `expose` field as enabling an "iptables accept
rule" for the port.

---

## What was decided

The OS switched to nftables. The `offlinelab-firewall` Buildroot package implements an
`inet` family nftables ruleset. The framework Bash library module `fw.sh` provides
nftables rule management helpers.

User confirmation: "We use nftables now on the OS, but I'm not sure if our tool should
create firewall rules yet — let's find out when we get there."

---

## Correct statement

All documentation references to "iptables" should be treated as errors. The correct
statement is: "when `expose: true`, an nftables accept rule is applied for this port
during `appctl install`, and removed during `appctl remove`."

---

## Outstanding question

Whether appctl MANAGES per-app nftables rules directly is still TBD. The OS uses
nftables, but whether appctl should call `fw.sh` (shell exec into the framework Bash
module) or replicate nftables rule generation in Go is an open design question.
