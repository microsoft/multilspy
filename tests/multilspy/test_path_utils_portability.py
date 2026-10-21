"""Cross-platform URI and Windows drive casing regressions.

Exercise Windows semantics on Linux/macOS too, independent of running a
Windows interpreter; native Windows CI separately exercises real Pyright.
"""

import ntpath
from pathlib import PureWindowsPath
from types import SimpleNamespace

from multilspy.multilspy_utils import PathUtils
import multilspy.multilspy_utils as utils


def test_case_insensitive_windows_drives_are_same_drive(monkeypatch):
    monkeypatch.setattr(utils, "PurePath", PureWindowsPath)
    monkeypatch.setattr(utils, "os", SimpleNamespace(path=ntpath))
    # Pyright uses lowercase drive URI, pathlib workspace might uppercase it.
    assert PathUtils.get_relative_path(
        r"c:\Repo\src\module.py", r"C:\Repo"
    ) == r"src\module.py"
    assert PathUtils.get_relative_path(
        r"D:\Repo\src\module.py", r"C:\Repo"
    ) is None
    # A differently cased but otherwise identical workspace is same location.
    assert PathUtils.get_relative_path(
        r"c:\REPO\module.py", r"C:\repo"
    ) == "module.py"
