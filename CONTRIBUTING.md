# Contributing

Thank you for helping make AI skill updates safer and more reproducible.

## Before opening a change

Use an issue for substantial behavior or policy changes. Security findings belong in private
vulnerability reporting. By contributing, you agree that your contribution is licensed under
Apache-2.0.

## Development workflow

1. Install Python 3.11+ and `uv`.
2. Run `uv sync --extra dev`.
3. Add tests for success, failure, and security-sensitive paths.
4. Run `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src`, and `uv run pytest`.
5. Keep policy decisions deterministic and attach concrete evidence to findings.

Do not add candidate execution to acquisition or analysis. New executable fixture backends require a
documented threat model and must fail closed.
