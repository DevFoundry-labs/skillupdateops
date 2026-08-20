# Security Policy

## Supported versions

Security fixes are provided for the latest major release.

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for this repository. Do not open a public issue
for a suspected vulnerability. Include affected version, platform, reproduction steps, impact, and
any proposed mitigation. You should receive an acknowledgment within five business days.

## Operational guidance

- Treat candidate skills and repositories as hostile input.
- Do not weaken GitHub HTTPS source restrictions without a compensating trust policy.
- Keep `.skillops/store`, approvals, history, and audit data outside source control.
- Review critical findings; `--override-policy` is an explicit exception, not a safety verdict.
- Run executable fixtures only on hosts where Docker is an acceptable isolation boundary.
- Pin this Action to a full commit SHA in high-assurance environments.

The complete boundary and known limitations are documented in [docs/threat-model.md](docs/threat-model.md).
