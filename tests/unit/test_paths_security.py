import pytest

from app.utils.paths import UnsafePathError, is_safe_id, require_safe_id, safe_join, sanitize_filename
from app.utils.security import host_allowed, origin_allowed, tokens_match


@pytest.mark.parametrize("raw,expected", [
    ("photo.jpg", "photo.jpg"),
    ("../../etc/passwd", "passwd"),
    ("..\\..\\windows\\system32\\cmd.exe", "cmd.exe"),
    ("my photo (1).png", "my photo _1_.png"),
    ("", "file"),
    ("..", "file"),
    ("CON.txt", "_CON.txt"),
    ("naïve café.jpg", "naive cafe.jpg"),
    ("a" * 300 + ".png", "a" * 116 + ".png"),
    ("\x00evil\n.png", "evil_.png"),
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_safe_join_blocks_traversal(tmp_path):
    assert safe_join(tmp_path, "a", "b.txt") == (tmp_path / "a" / "b.txt").resolve()
    for bad in ("../x", "a/../../x", "/etc/passwd"):
        with pytest.raises(UnsafePathError):
            safe_join(tmp_path, bad)


def test_safe_join_blocks_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside_target"
    outside.mkdir(exist_ok=True)
    (tmp_path / "link").symlink_to(outside)
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, "link", "file")


@pytest.mark.parametrize("value,ok", [("pr_abc123", True), ("ph_0f", True), ("../x", False), ("a/b", False), ("", False), ("x" * 65, False)])
def test_ids(value, ok):
    assert is_safe_id(value) is ok
    if not ok:
        with pytest.raises(UnsafePathError):
            require_safe_id(value)


def test_host_and_origin_checks():
    allowed = {"127.0.0.1", "localhost", "[::1]"}
    assert host_allowed("127.0.0.1:5173", allowed)
    assert host_allowed("localhost", allowed)
    assert host_allowed("[::1]:5173", allowed)
    assert not host_allowed("evil.example:5173", allowed)
    assert not host_allowed(None, allowed)
    assert origin_allowed(None, allowed)
    assert origin_allowed("http://127.0.0.1:5173", allowed)
    assert not origin_allowed("https://evil.example", allowed)
    assert not origin_allowed("null", allowed)


def test_tokens_match():
    assert tokens_match("abc", "abc")
    assert not tokens_match("abc", "abd")
    assert not tokens_match("abc", None)
