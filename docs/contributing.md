# Contributing

Offline Lab is an open-source community project under AGPL v3. Contributions are welcome.

## Getting started

The best place to start is the [operating-system](https://github.com/offline-lab/operating-system) repository, which contains the OS image builder, the framework, and all on-device tooling. Read the [Development guide](development.md) for build setup and coding conventions.

If you have something specific in mind, open an issue first. Discussing the approach before writing code saves everyone time, especially for larger changes.

## Submitting a pull request

### 1. Fork and branch

Use `feature/<short-description>` for new features, `fix/<short-description>` for bug fixes.

```bash
git clone git@github.com:<your-username>/<repo>.git
cd <repo>
git checkout -b my-change
```

### 2. Make your change

Keep changes small and focused: one concern per PR. Match the existing code style. Don't include unrelated cleanups or formatting. Test locally before submitting.

### 3. Commit

Write a clear message that says what changed and why:

```
Add WiFi credential loading from /boot/firmware

Reads wpa_supplicant configuration from the boot partition
so users can configure WiFi without a serial console.
```

### 4. Push and open a PR

```bash
git push origin my-change
```

Open a pull request against `main` on the upstream repository. In the description, summarize the change, how you tested it, and link related issues.

### 5. Review

A maintainer will review your PR. Changes may need revision before merging.

## Reporting issues

Open an issue in the relevant repository. Include what you expected, what happened, and steps to reproduce.

## Code of conduct

Be respectful and constructive. We build tools for communities. The project should reflect that.
