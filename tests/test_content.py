from pathlib import Path

import pytest

from skillupdateops.content import ensure_within, tree_manifest
from skillupdateops.errors import SecurityError


def test_hash_is_order_and_line_ending_stable(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "b.md").write_bytes(b"two\r\n")
    (first / "a.md").write_bytes(b"one\r\n")
    (second / "a.md").write_bytes(b"one\n")
    (second / "b.md").write_bytes(b"two\n")
    assert tree_manifest(first)[0] == tree_manifest(second)[0]


def test_rejects_escape(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="escapes"):
        ensure_within(tmp_path / "allowed", tmp_path / "elsewhere")


def test_rejects_empty_tree(tmp_path: Path) -> None:
    with pytest.raises(SecurityError, match="no files"):
        tree_manifest(tmp_path)
