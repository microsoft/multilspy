"""
This file contains tests for running the Bash (bash-language-server) Language Server.
"""

import pytest
import tempfile
from pathlib import Path
from multilspy import LanguageServer
from multilspy.multilspy_config import MultilspyConfig, Language
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_servers.bash_language_server import BashLanguageServer

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_multilspy_bash_instantiation():
    """
    Test that LanguageServer.create instantiates BashLanguageServer for Language.BASH.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        config = MultilspyConfig(code_language=Language.BASH)
        logger = MultilspyLogger()
        lsp = LanguageServer.create(config, logger, tmpdir)
        assert isinstance(lsp, BashLanguageServer)
        assert lsp.language_id == "shellscript"


@pytest.mark.asyncio
async def test_multilspy_bash_symbols_and_definition():
    """
    Test document symbols, definition resolution, hover, and references in a Bash workspace.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        sh_file = Path(tmpdir) / "deploy.sh"
        sh_file.write_text("""#!/usr/bin/env bash

build_project() {
    echo "Building..."
}

deploy_project() {
    build_project
    echo "Deploying..."
}

deploy_project
""")
        config = MultilspyConfig(code_language=Language.BASH)
        logger = MultilspyLogger()
        lsp = LanguageServer.create(config, logger, tmpdir)

        async with lsp.start_server():
            # 1. Document Symbols
            syms, _ = await lsp.request_document_symbols("deploy.sh")
            sym_names = [s["name"] for s in syms]
            assert "build_project" in sym_names
            assert "deploy_project" in sym_names

            # 2. Definition
            defn = await lsp.request_definition("deploy.sh", 7, 5)
            assert len(defn) == 1
            assert defn[0]["relativePath"] == "deploy.sh"
            assert defn[0]["range"]["start"]["line"] == 2

            # 3. References
            refs = await lsp.request_references("deploy.sh", 2, 2)
            assert len(refs) >= 1
            assert any(r["relativePath"] == "deploy.sh" and r["range"]["start"]["line"] == 7 for r in refs)

            # 4. Hover
            hover = await lsp.request_hover("deploy.sh", 7, 5)
            assert hover is not None
            assert "build_project" in str(hover)


def test_sync_multilspy_bash():
    """
    Test synchronous SyncLanguageServer with Bash.
    """
    from multilspy import SyncLanguageServer

    with tempfile.TemporaryDirectory() as tmpdir:
        sh_file = Path(tmpdir) / "deploy.sh"
        sh_file.write_text("""#!/usr/bin/env bash

build_project() {
    echo "Building..."
}

deploy_project() {
    build_project
}
""")
        config = MultilspyConfig(code_language=Language.BASH)
        logger = MultilspyLogger()
        lsp = SyncLanguageServer.create(config, logger, tmpdir)

        with lsp.start_server():
            defn = lsp.request_definition("deploy.sh", 7, 5)
            assert len(defn) == 1
            assert defn[0]["relativePath"] == "deploy.sh"
            assert defn[0]["range"]["start"]["line"] == 2

