# Customize the rootfs

The build backend produces the base rootfs; buildctl applies a fixed set of post-build transforms before packing the squashfs. Two of those transforms are project-controlled: the `rootfs/` skeleton overlay and the `.buildignore` exclusion list.

Both run after the backend produces its output and before buildctl generates the required `os-release` and service unit. Order matters: skeleton first, then exclusions, then generation, then validation.

## Skeleton overlay (`rootfs/`)

A `rootfs/` directory in the project is merged into the backend output, file by file. Skeleton entries override backend output. This lets you ship custom configs, drop-in unit files, or anything else that should take precedence over what the backend produced, uniformly across all backends.

```
myapp/
  Dockerfile
  package.yaml
  rootfs/                  ← merged over backend output
    etc/
      mosquitto/
        mosquitto.conf
```

Conventions:

- **Regular files** overwrite the matching path in the backend output, preserving the skeleton file's mode.
- **Directories** are created if missing.
- **Symlinks** are recreated in the destination. Absolute symlink targets are rejected because DDIs mount at unpredictable paths and absolute links would point outside the image. Use relative symlinks.
- The `rootfs/` directory itself is not included in the final image; only its contents.

Skeleton files do not skip the validation step. If your skeleton contains a service unit, it still must not set `User=` or `Group=`.

## `.buildignore`

A `.buildignore` file at the project root lists paths to strip from the rootfs before squashfs packing. The syntax is identical to [`.dockerignore`](https://docs.docker.com/build/concepts/context/#dockerignore-ignore-build-context-files) (buildctl uses the same `moby/patternmatcher` library):

- One pattern per line.
- Blank lines and lines starting with `#` are ignored.
- `!` at the start of a pattern re-includes a previously excluded path.
- Standard globs: `*` matches within a path segment, `**` matches across segments.

Example:

```gitignore
# Strip backend debug data
usr/share/doc
usr/share/man
usr/lib/debug

# Strip a dev-only binary but keep its sibling files
usr/bin/*-test
!usr/bin/real-test
```

`.buildignore` affects the squashfs contents only. It does not affect what the backend sees during its own build; for Docker, use `.dockerignore` for that.

## When to use which

| Goal | Mechanism |
|---|---|
| Override a file the backend produced | `rootfs/` skeleton |
| Add a new file the backend did not produce | `rootfs/` skeleton |
| Provide the service unit | `rootfs/usr/lib/systemd/system/<name>.service` (or let buildctl generate one from `command:`) |
| Provide a default config to be seeded into the writable volume at install time | `rootfs/etc/<app>/<config>` |
| Remove files the backend produced that should not ship | `.buildignore` |
| Reduce image size (docs, manpages, debug symbols) | `.buildignore` |

After skeleton and `.buildignore` run, buildctl generates missing required files (`os-release`, the service unit if `command:` is set, and an embedded copy of `package.yaml`). See [Architecture and build pipeline](../explanation/architecture.md#post-build-pipeline) for the full sequence.
