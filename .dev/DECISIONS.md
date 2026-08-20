# Architecture Decisions

## ADR-001 — Python standard-library-first CLI

### Context

The utility must install quickly on Windows, macOS, Linux, and CI runners and remain auditable.

### Decision

Use Python 3.11+, `argparse`, dataclasses, and JSON persistence. PyYAML is the sole runtime dependency for readable policy and fixture files.

### Consequences

Installation and review remain simple. Rich terminal UI is intentionally secondary to stable text and JSON output.

## ADR-002 — Content-addressed snapshots

### Context

Mutable Git refs and copied directories cannot provide reproducible approval or rollback.

### Decision

Normalize paths and line endings, hash the complete selected tree, store immutable snapshots by SHA-256, and bind approvals to candidate hashes.

### Consequences

Rollback and audit are deterministic. Binary files retain exact bytes; text normalization is limited to hashing.

## ADR-003 — Deterministic analysis is authoritative

### Context

An LLM-generated risk summary is nondeterministic and can itself be influenced by malicious instructions.

### Decision

Use frontmatter plus explainable pattern evidence and policy rules. No model is required or trusted for decisions.

### Consequences

Reports are reproducible and inspectable, though conservative patterns can require human review.

## ADR-004 — Docker is the executable sandbox boundary

### Context

Portable subprocess restrictions alone do not provide a credible security boundary.

### Decision

Static fixtures run natively; executable fixtures run only inside Docker with networking disabled, a read-only root, dropped Linux capabilities, bounded resources, and a disposable writable workspace.

### Consequences

Executable tests fail closed without Docker. Candidate inspection and core update checks never require execution.
