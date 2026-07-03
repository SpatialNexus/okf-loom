# Security Policy

okf-loom v1.0 is an Apache-2.0 open-source repository for local OKF bundle authoring, serving, and viewing.

## Reporting a vulnerability

Please report suspected security issues privately to the repository maintainers before opening a public issue.
Include the affected commit, commands used, expected impact, and whether the issue requires a malicious bundle, a network-exposed studio, or local filesystem access.

## Supported scope

The v1.0 baseline supports the current `develop` checkout.
The primary runtime path is repo-local execution with `scripts/okf-loom`; PyPI or package publishing is not part of the supported release process.

## Live studio exposure boundary

`scripts/okf-loom serve` binds to `127.0.0.1` by default.
Using `--public`, a non-loopback `--host`, or `--tunnel` changes the exposure boundary.

- Anyone with a reachable studio URL can read public GET surfaces for the served bundle.
- Mutating POST routes require the per-session `X-OKF-Token` and Origin/Host allow-list checks.
- `--tunnel` starts a Cloudflare quick tunnel and adds the tunnel hostname to the runtime allow-list so comments and edits work through the link.
- Use `--no-edit` for a read-only studio when sharing a URL for review.
- Treat `<bundle>/.okf-loom/session/.token` as secret; session state is intended to stay out of commits.

Active viewer override/plugin code is disabled unless both the bundle declares `viewer.allow_active_code: true` and the operator consents with `--allow-active-code` or `OKF_LOOM_ALLOW_ACTIVE_CODE`.

## License boundary

okf-loom is licensed under Apache-2.0.
Do not submit code, documentation, or assets that cannot be distributed under Apache-2.0 unless the maintainers explicitly approve a separate license notice.
