# Threat Model

## Protected assets

- Host files, credentials, network identity, and processes
- Integrity of installed skills and approvals
- Provenance and audit history
- CI credentials and repository contents

## Adversaries and inputs

An upstream maintainer, compromised repository, malicious contributor, mutable ref, or crafted skill
may attempt traversal, symlink escape, oversized input denial of service, hidden command requests,
credential access, network exfiltration, approval bypass, or execution during inspection.

## Controls

- GitHub HTTPS allowlist; credential-bearing URLs and local Git protocol are rejected.
- Git hooks disabled and no candidate dependency/install commands executed.
- Resolved commit and normalized content hash are both recorded.
- Traversal containment, symlink rejection, file count, per-file, and total-byte limits.
- Exact-hash expiring approvals; critical exceptions require a separate explicit flag.
- Snapshot and staging re-verification immediately before install.
- Atomic replacement with recovery backup and offline rollback.
- Hash-chained audit events reveal modification or deletion within the retained chain.
- Docker-only executable fixtures with restrictive flags.

## Residual risks

Natural-language analysis can miss malicious meaning or flag benign wording. Unicode confusables,
tool semantics, indirect external content, and runtime agent behavior cannot be completely inferred
from static text. GitHub account compromise and malicious repository-owned policy/fixtures are outside
the candidate boundary. Docker is not a formal sandbox and depends on host configuration.

SkillUpdateOps reduces update risk and improves evidence; it does not certify safety.
