"""
This file contains tests for running the Lua (LuaLS) Language Server.
"""

import pytest
import tempfile
from pathlib import Path
from multilspy import LanguageServer
from multilspy.multilspy_config import MultilspyConfig, Language
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_servers.lua_language_server import LuaLanguageServer

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_multilspy_lua_instantiation():
    """
    Test that LanguageServer.create instantiates LuaLanguageServer for Language.LUA.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MultilspyConfig(code_language=Language.LUA)
        logger = MultilspyLogger()
        lsp = LanguageServer.create(config, logger, tmpdir)
        assert isinstance(lsp, LuaLanguageServer)
        assert lsp.language_id == "lua"


@pytest.mark.asyncio
async def test_multilspy_lua_symbols_and_definition():
    """
    Test document symbols, definition resolution, hover, and references in a Lua workspace.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        lua_file = Path(tmpdir) / "math_utils.lua"
        lua_file.write_text("""local function add(a, b)
    return a + b
end

local function multiply(x, y)
    return x * y
end

local result = add(5, 10)
print(result)
""")
        config = MultilspyConfig(code_language=Language.LUA)
        logger = MultilspyLogger()
        lsp = LanguageServer.create(config, logger, tmpdir)

        async with lsp.start_server():
            # 1. Document Symbols
            syms, _ = await lsp.request_document_symbols("math_utils.lua")
            sym_names = [s["name"] for s in syms]
            assert "add" in sym_names
            assert "multiply" in sym_names

            # 2. Definition
            defn = await lsp.request_definition("math_utils.lua", 8, 16)
            assert len(defn) == 1
            assert defn[0]["relativePath"] == "math_utils.lua"
            assert defn[0]["range"]["start"]["line"] == 0

            # 3. References
            refs = await lsp.request_references("math_utils.lua", 0, 16)
            assert len(refs) >= 1
            assert any(r["relativePath"] == "math_utils.lua" and r["range"]["start"]["line"] == 8 for r in refs)

            # 4. Hover
            hover = await lsp.request_hover("math_utils.lua", 8, 16)
            assert hover is not None
            assert "add" in str(hover)


def test_sync_multilspy_lua():
    """
    Test synchronous SyncLanguageServer with Lua.
    """
    from multilspy import SyncLanguageServer

    with tempfile.TemporaryDirectory() as tmpdir:
        lua_file = Path(tmpdir) / "math_utils.lua"
        lua_file.write_text("""local function add(a, b)
    return a + b
end

local result = add(5, 10)
print(result)
""")
        config = MultilspyConfig(code_language=Language.LUA)
        logger = MultilspyLogger()
        lsp = SyncLanguageServer.create(config, logger, tmpdir)

        with lsp.start_server():
            defn = lsp.request_definition("math_utils.lua", 4, 16)
            assert len(defn) == 1
            assert defn[0]["relativePath"] == "math_utils.lua"
            assert defn[0]["range"]["start"]["line"] == 0

