# Architecture

SkillUpdateOps is a local-first state machine rather than an agent runtime.

## Trust boundaries

1. Repository-owned configuration, policy, and fixtures are trusted operator input.
2. Candidate sources are untrusted content and are never imported or executed during inspection.
3. Content-addressed snapshots bind analysis, approval, installation, and rollback to identical bytes.
4. Docker is the only supported boundary for opt-in executable fixtures.

## State transitions

```text
UNTRACKED → CHECKED → REVIEW_REQUIRED → APPROVED → INSTALLED
                 ↘ BLOCKED ↗                     ↘ DRIFTED
                                                   ↘ ROLLED_BACK
```

Every material transition appends an event to a hash-chained audit log. An approval contains the
candidate hash and expiry; changing the candidate invalidates it. Apply re-hashes the snapshot,
copies it to a sibling staging directory, verifies the staging tree, then replaces the target.

## Persistence

`skills.lock` is portable approved state. Runtime snapshots and approvals remain local. JSON is used
for canonical persistence and YAML only for human-authored config, policy, and fixtures.

## Failure recovery

Acquisition occurs in an OS temporary directory. Snapshot creation is idempotent. Installation keeps
the previous target as a backup until the verified staging rename succeeds. Metadata history points
to immutable snapshots, allowing exact rollback without network access.
