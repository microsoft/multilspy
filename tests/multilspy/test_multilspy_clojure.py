"""
Basic integration tests for the clojure-lsp language server.
"""

import pathlib

import pytest
import pytest_asyncio

from multilspy.language_server import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_types import Position

pytest_plugins = ("pytest_asyncio",)


@pytest_asyncio.fixture(scope="function")
async def clojure_lsp():
    """
    FIXME: this should be a module-scoped fixture that creates and initializes a Clojure LSP server,
      but pytest-asyncio's event loop does not support module-scoped fixtures.
    """
    config = MultilspyConfig(code_language=Language.CLOJURE)
    logger = MultilspyLogger()
    source_directory_path = str(pathlib.Path(__file__).parent / "clojure_test_repo")
    lsp = LanguageServer.create(config, logger, source_directory_path)
    
    async with lsp.start_server():
        yield lsp


@pytest.mark.asyncio
async def test_clojure_lsp_basic_definition(clojure_lsp):
    """
    Test the working of multilspy with Clojure - basic definition lookup
    """
    # Test finding definition of 'greet' function call in core.clj
    filepath = "src/test_app/core.clj"
    result = await clojure_lsp.request_definition(filepath, 20, 12)  # Position of 'greet' in (greet "World")

    assert isinstance(result, list)
    assert len(result) >= 1
    
    # Should find the definition of greet function
    definition = result[0]
    assert definition["relativePath"] == "src/test_app/core.clj"
    assert definition["range"]["start"]["line"] == 2  # greet function definition line


@pytest.mark.asyncio
async def test_clojure_lsp_cross_file_references(clojure_lsp):
    """
    Test finding references across files in Clojure
    """
    # Test finding references to 'multiply' function from core.clj
    filepath = "src/test_app/core.clj"
    result = await clojure_lsp.request_references(filepath, 12, 6)  # Position of 'multiply' function definition

    assert isinstance(result, list)
    assert len(result) >= 2  # Should find definition + usage in utils.clj

    # Should find usage in utils.clj calculate-area function
    usage_found = any(
        item["relativePath"] == "src/test_app/utils.clj" and 
        item["range"]["start"]["line"] == 6  # multiply usage in calculate-area
        for item in result
    )
    assert usage_found, "Should find multiply usage in utils.clj"


@pytest.mark.asyncio
async def test_clojure_lsp_completions(clojure_lsp):
    """
    Test code completions in Clojure
    """
    # Open a file and test completions
    filepath = "src/test_app/utils.clj"
    with clojure_lsp.open_file(filepath):
        # Test completions for core/ namespace
        result = await clojure_lsp.request_completions(filepath, 6, 8)  # After "core/" in calculate-area

        assert isinstance(result, list)
        assert len(result) > 0

        # Should find multiply and other core functions
        completion_texts = [item["completionText"] for item in result]
        assert any("multiply" in text for text in completion_texts)


@pytest.mark.asyncio 
async def test_clojure_lsp_document_symbols(clojure_lsp):
    """
    Test document symbols extraction in Clojure
    """
    filepath = "src/test_app/core.clj"
    symbols, tree_repr = await clojure_lsp.request_document_symbols(filepath)

    assert isinstance(symbols, list)
    assert len(symbols) >= 4  # greet, add, multiply, -main functions

    # Check that we find the expected function symbols
    symbol_names = [symbol["name"] for symbol in symbols]
    expected_functions = ["greet", "add", "multiply", "-main"]
    
    for func_name in expected_functions:
        assert func_name in symbol_names, f"Should find {func_name} function in symbols"


@pytest.mark.asyncio
async def test_clojure_lsp_hover(clojure_lsp):
    """
    Test hover information in Clojure
    """
    # Test hover on greet function
    filepath = "src/test_app/core.clj" 
    result = await clojure_lsp.request_hover(filepath, 2, 7)  # Position on 'greet' function name

    if result is not None:
        assert "contents" in result
        # Should contain function signature or documentation
        contents = result["contents"]
        if isinstance(contents, str):
            assert "greet" in contents.lower()
        elif isinstance(contents, dict) and "value" in contents:
            assert "greet" in contents["value"].lower()


@pytest.mark.asyncio
async def test_clojure_lsp_workspace_symbols(clojure_lsp):
    """
    Test workspace symbol search in Clojure
    """
    # Search for functions containing "add"
    result = await clojure_lsp.request_workspace_symbol("add")

    if result is not None:
        assert isinstance(result, list)
        
        # Should find the 'add' function
        symbol_names = [symbol["name"] for symbol in result]
        assert any("add" in name.lower() for name in symbol_names)


@pytest.mark.asyncio
async def test_clojure_lsp_file_operations(clojure_lsp):
    """
    Test file manipulation operations with Clojure LSP
    """
    filepath = "src/test_app/core.clj"
    
    with clojure_lsp.open_file(filepath):
        original_text = clojure_lsp.get_open_file_text(filepath)
        assert "greet" in original_text
        
        # Test inserting text
        new_position = clojure_lsp.insert_text_at_position(filepath, 23, 0, "\n;; Test comment\n")
        assert new_position["line"] == 25  # After insertion
        
        modified_text = clojure_lsp.get_open_file_text(filepath)
        assert ";; Test comment" in modified_text
        
        # Test deleting text
        start_pos = Position(line=23, character=0)
        end_pos = Position(line=25, character=0)
        deleted_text = clojure_lsp.delete_text_between_positions(filepath, start_pos, end_pos)
        assert ";; Test comment" in deleted_text
        
        final_text = clojure_lsp.get_open_file_text(filepath)
        assert final_text == original_text


@pytest.mark.asyncio
async def test_clojure_lsp_namespace_functions(clojure_lsp):
    """
    Test LSP functionality with namespaced functions
    """
    # Test definition lookup for core/greet usage in utils.clj
    filepath = "src/test_app/utils.clj"
    result = await clojure_lsp.request_definition(filepath, 11, 25)  # Position of 'greet' in core/greet call

    assert isinstance(result, list)
    assert len(result) >= 1
    
    # Should find the definition in core.clj
    definition = result[0]
    assert definition["relativePath"] == "src/test_app/core.clj"


