# Style guide

Coding conventions for the Offline Lab OS codebase.

## Shell scripts

POSIX sh where possible, bash only when needed. No unofficial bash-isms.

## Systemd units

Use explicit `After=`, `Requires=`, `WantedBy=`. Don't rely on implicit ordering.

## Config files

Match the style of the file you're editing.

## No binaries in git

Everything is fetched at build time. No pre-built images, binaries, or third-party source code in the repository.

## Framework scripts

Follow the conventions in `framework/.claude/CLAUDE.md`:

- `namespace::function_name` naming
- `log::trace` as first line of every function
- Return codes 0/1/2 only

Use the framework library for common operations (logging, config reads, network checks, privilege escalation) rather than reimplementing them in package scripts.

Run `bin/test-framework --lint` before submitting changes to framework code.

## Busybox compatibility

The rootfs uses Busybox applets, not GNU coreutils. Use compatible invocations:

- `grep -E` not `grep -P`
- `date -u` not `date --universal`
- `mktemp -t prefix-XXXX` not `mktemp --suffix`
- No gawk-specific features
