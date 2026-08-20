# Policy Reference

`.skillops/policy.yml` supports these keys:

| Key | Type | Default behavior |
|---|---|---|
| `schema_version` | integer | Must be `1` |
| `require_approval_for_all_updates` | boolean | Every changed candidate needs approval |
| `block_approval_weakening` | boolean | Critical finding when approval language weakens |
| `block_destructive_instructions` | boolean | Critical finding for destructive instruction evidence |
| `denied_commands` | glob list | Critical on matching extracted commands |
| `denied_domains` | glob list | Critical on matching external domains |
| `denied_paths` | glob list | Critical on matching sensitive path evidence |

Patterns are case-insensitive shell-style globs. Findings are conservative evidence from Markdown and
frontmatter, not a proof of runtime behavior.

Decisions:

- `pass`: no changed content requiring approval and no critical findings.
- `review`: changed content requires an exact-hash approval.
- `blocked`: a critical finding requires an approval created with `--override-policy`.

An override is recorded with approver, candidate hash, time, expiry, and the original findings.
