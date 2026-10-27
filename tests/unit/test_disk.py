import pytest

from app.utils import disk


def test_disk_space_check(tmp_path, monkeypatch):
    disk.ensure_free_space(tmp_path, minimum=0)

    class Usage:
        free = 10

    monkeypatch.setattr(disk.shutil, "disk_usage", lambda p: Usage())
    with pytest.raises(disk.DiskSpaceError, match="Not enough free disk space"):
        disk.ensure_free_space(tmp_path)
