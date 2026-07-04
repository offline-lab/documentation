# Cross-compile for a different architecture

Pass `--arch <arch>` to build for a target that doesn't match the host. Supported values: `arm64`, `amd64`, `armv7`, `armv6`, `i386`, `riscv64`, `ppc64le`, `s390x`.

## Docker backend

The Docker backend builds through `docker buildx` and supports cross-arch transparently. On macOS, Docker Desktop provides binfmt emulation already. On Linux, register the handlers once:

```bash
buildctl init
# or manually:
# docker run --privileged --rm tonistiigi/binfmt --install all
```

Then build normally:

```bash
buildctl build . --key ./keys/mykey.key --arch arm64
```

For Dockerfiles that compile native code, QEMU emulation is slow; a native target machine is faster.

## Other backends

shell and make do not cross-compile natively. They receive `BUILDCTL_ARCH`; your script or Makefile is responsible for invoking whatever cross-toolchain you provide.

mkosi rejects mismatched arches with an error. Use Docker for cross-arch builds with distribution packages.

## DPS partition type UUIDs

Each arch maps to fixed DPS partition type UUIDs in the produced DDI. See [DDI output and metadata](../reference/ddi-output.md#architecture-uuids).
