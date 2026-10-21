"""Regression tests for UTF-16 LSP positions in in-memory file buffers.

Other language servers share this code, so use both Python adapters with a
mocked transport and no external binary or network access.
"""

from unittest.mock import Mock

import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_utils import TextUtils


@pytest.mark.parametrize("backend", ["jedi", "pyright"])
def test_utf16_insert_and_delete_do_not_desynchronize_file_buffer(tmp_path, backend):
    source = "value = '🐍'; target = 1\n"
    filename = tmp_path / "example.py"
    filename.write_text(source, encoding="utf-8")
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON, python_server=backend),
        MultilspyLogger(), str(tmp_path.resolve())
    )
    server.server = Mock()
    server.server_started = True
    before_target = source.index("target")
    column = TextUtils._utf16_length(source[:before_target])
    assert column == before_target + 1  # Python index excludes surrogate pair length.

    with server.open_file("example.py"):
        position = server.insert_text_at_position("example.py", 0, column, "🦊_")
        assert position == {"line": 0, "character": column + 3}
        assert server.get_open_file_text("example.py") == "value = '🐍'; 🦊_target = 1\n"
        assert server.delete_text_between_positions(
            "example.py", {"line": 0, "character": column},
            {"line": 0, "character": column + 3},
        ) == "🦊_"
        assert server.get_open_file_text("example.py") == source
    changes = [call.args[0] for call in server.server.notify.did_change_text_document.call_args_list]
    assert [event["textDocument"]["version"] for event in changes] == [1, 2]
    assert [event["contentChanges"][0]["range"]["start"]["character"] for event in changes] == [column, column]
    assert filename.read_text(encoding="utf-8") == source
    assert not server.open_file_buffers


def test_utf16_positions_round_trip_and_reject_half_surrogate():
    text = "a🐍b\n🦊x\n"
    for idx in range(len(text) + 1):
        line, col = TextUtils.get_line_col_from_index(text, idx)
        assert TextUtils.get_index_from_line_col(text, line, col) == idx
    with pytest.raises(ValueError, match="surrogate"):
        TextUtils.get_index_from_line_col(text, 0, 2)
    with pytest.raises(ValueError, match="outside the line"):
        TextUtils.get_index_from_line_col(text, 0, 8)
    with pytest.raises(ValueError, match="non-negative"):
        TextUtils.get_index_from_line_col(text, -1, 0)
    assert TextUtils.get_updated_position_from_line_and_column_and_edit(0, 0, "🐍") == (0, 2)
    assert TextUtils.get_updated_position_from_line_and_column_and_edit(0, 9, "🐍\n🦊x") == (1, 3)
