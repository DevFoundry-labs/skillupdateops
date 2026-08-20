# Fixture Reference

Fixture files are YAML mappings with a `tests` list. Each test supports:

- `name`: display name.
- `contains`: strings that must appear in combined Markdown.
- `not_contains`: strings that must not appear.
- `command`: optional argument list executed inside the fixed `python:3.12-alpine` Docker image.
- `timeout_seconds`: 1–300, default 30.
- `expect_exit`: expected container exit code, default 0.
- `stdout_contains`: optional output marker.

Example:

```yaml
tests:
  - name: approval remains mandatory
    contains: ["ask for approval"]
    not_contains: ["skip approval"]
  - name: file remains readable
    command: ["python", "-c", "print(open('/skill/SKILL.md').read()[:7])"]
    stdout_contains: "---"
```

Commands receive `/skill` read-only and `/work` writable. The container has no network, a read-only
root, no Linux capabilities, no privilege escalation, bounded processes, memory, CPU, and runtime.
Docker itself remains a privileged host service; use a hardened runner for hostile workloads.
