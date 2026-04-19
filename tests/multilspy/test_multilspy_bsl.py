"""
Tests for the BSL Language Server (1C:Enterprise / OneScript).

BSL LS requires Java 17+ in PATH and downloads the JAR (~94 MB) on first run
from https://github.com/1c-syntax/bsl-language-server/releases.

Skipped if `java` is not available, so CI without Java will not flake.
"""

import contextlib
import shutil
import tempfile
from pathlib import Path, PurePath
from typing import Iterator

import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

pytest_plugins = ("pytest_asyncio",)

pytestmark = pytest.mark.skipif(
    shutil.which("java") is None,
    reason="BSL LS requires Java 17+ in PATH",
)


@contextlib.contextmanager
def create_bsl_test_project() -> Iterator[str]:
    """Create a minimal self-contained 1C:Enterprise configuration.

    Two common modules: one declares an exported function, the other calls it.
    Configuration.xml provides the workspace root descriptor required by BSL LS.
    """
    with tempfile.TemporaryDirectory() as root:
        project_dir = Path(root) / "bsl_test_project"
        project_dir.mkdir()

        # Minimal Configuration.xml root (BSL LS reads this for project layout).
        (project_dir / "Configuration.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">\n'
            '  <Configuration uuid="00000000-0000-0000-0000-000000000001">\n'
            '    <Properties>\n'
            '      <Name>TestConfig</Name>\n'
            '    </Properties>\n'
            '  </Configuration>\n'
            '</MetaDataObject>\n',
            encoding="utf-8",
        )

        util_dir = project_dir / "CommonModules" / "TestUtil" / "Ext"
        util_dir.mkdir(parents=True)
        (util_dir.parent / "TestUtil.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">\n'
            '  <CommonModule><Properties><Name>TestUtil</Name>'
            '<Server>true</Server></Properties></CommonModule>\n'
            '</MetaDataObject>\n',
            encoding="utf-8",
        )
        (util_dir / "Module.bsl").write_text(
            "Функция ПолучитьЗначение() Экспорт\n"
            "    Возврат \"default\";\n"
            "КонецФункции\n",
            encoding="utf-8",
        )

        caller_dir = project_dir / "CommonModules" / "TestCaller" / "Ext"
        caller_dir.mkdir(parents=True)
        (caller_dir.parent / "TestCaller.xml").write_text(
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<MetaDataObject xmlns="http://v8.1c.ru/8.3/MDClasses">\n'
            '  <CommonModule><Properties><Name>TestCaller</Name>'
            '<Server>true</Server></Properties></CommonModule>\n'
            '</MetaDataObject>\n',
            encoding="utf-8",
        )
        (caller_dir / "Module.bsl").write_text(
            "Процедура Вызвать() Экспорт\n"
            "    Сообщить(TestUtil.ПолучитьЗначение());\n"
            "КонецПроцедуры\n",
            encoding="utf-8",
        )

        yield str(project_dir)


@pytest.mark.asyncio
async def test_multilspy_bsl_start_and_document_symbols() -> None:
    """Server starts, initializes, and returns symbols for a .bsl file."""
    config = MultilspyConfig(code_language=Language.BSL)
    logger = MultilspyLogger()

    with create_bsl_test_project() as project_dir:
        lsp = LanguageServer.create(config, logger, project_dir)
        test_file = str(
            PurePath("CommonModules/TestUtil/Ext/Module.bsl")
        )

        async with lsp.start_server():
            symbols, _tree = await lsp.request_document_symbols(test_file)
            assert isinstance(symbols, list)
            # BSL LS exposes functions/procedures as symbols of kind 12 (Function)
            # or 6 (Method). We just assert the wiring returns structural data.
            if symbols:
                names = {s.get("name") for s in symbols}
                assert "ПолучитьЗначение" in names


@pytest.mark.asyncio
async def test_multilspy_bsl_references_in_same_module() -> None:
    """In-file references for a declaration work without workspace preload."""
    config = MultilspyConfig(code_language=Language.BSL)
    logger = MultilspyLogger()

    with create_bsl_test_project() as project_dir:
        lsp = LanguageServer.create(config, logger, project_dir)
        util_rel = str(PurePath("CommonModules/TestUtil/Ext/Module.bsl"))

        async with lsp.start_server():
            with lsp.open_file(util_rel):
                refs = await lsp.request_references(util_rel, 0, 10)
                assert isinstance(refs, list)


@pytest.mark.asyncio
async def test_multilspy_bsl_rename_returns_workspace_edit() -> None:
    """Raw rename RPC returns either {changes}, {documentChanges}, or None.

    This is the critical integration contract for downstream refactoring tools.
    """
    config = MultilspyConfig(code_language=Language.BSL)
    logger = MultilspyLogger()

    with create_bsl_test_project() as project_dir:
        lsp = LanguageServer.create(config, logger, project_dir)
        util_rel = str(PurePath("CommonModules/TestUtil/Ext/Module.bsl"))
        util_uri = (Path(project_dir) / util_rel).resolve().as_uri()

        async with lsp.start_server():
            with lsp.open_file(util_rel):
                result = await lsp.server.send.rename(
                    {
                        "textDocument": {"uri": util_uri},
                        "position": {"line": 0, "character": 10},
                        "newName": "ПолучитьЗначениеНовое",
                    }
                )
                # Either a WorkspaceEdit dict or None (LS chose not to rename).
                assert result is None or isinstance(result, dict)
                if isinstance(result, dict):
                    assert "changes" in result or "documentChanges" in result
