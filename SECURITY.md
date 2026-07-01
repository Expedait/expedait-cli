# Security Policy

## Supported versions

`expedait-cli` is distributed on [PyPI](https://pypi.org/project/expedait-cli/).
Security fixes are released against the latest published version. Please upgrade
to the newest release before reporting an issue:

```bash
uvx expedait-cli --version
uv tool upgrade expedait-cli   # or: pip install --upgrade expedait-cli
```

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Instead, report privately via one of:

- GitHub's [private vulnerability reporting](https://github.com/Expedait/expedait-cli/security/advisories/new)
  (Security → Report a vulnerability), or
- email **security@expedait.org**.

Please include:

- a description of the issue and its impact,
- steps to reproduce (a proof of concept if possible),
- affected version(s), and
- any suggested remediation.

## What to expect

- We aim to acknowledge reports within **3 business days**.
- We will keep you informed as we investigate and work on a fix.
- Once a fix is released, we are happy to credit you in the release notes
  unless you prefer to remain anonymous.

## Scope

This policy covers the `expedait-cli` client. Vulnerabilities in the hosted
Expedait API or web application should also be reported to
**security@expedait.org**.
