"""
This file contains tests for running the Kotlin Language Server: kotlin-language-server
using the synchronous API
"""

from pathlib import PurePath
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context

def test_multilspy_kotlin_sync_document_symbols() -> None:
    """
    Test document symbols functionality using the sync API
    """
    params = {
        "code_language": Language.KOTLIN,
        "repo_url": "https://github.com/fwcd/kotlin-language-server/",
        "repo_commit": "8418fb560a4013c3e02c942797e9c877affa0a51"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("server/src/test/resources/symbols/DocumentSymbols.kt"))

        with lsp.start_server():
            with lsp.open_file(test_file):
                result = lsp.request_document_symbols(test_file)
                
                symbols = result[0]
                assert len(symbols) == 5, "Should find exactly 5 document symbols"
                
                # Verify class symbol
                class_symbol = next((s for s in symbols if s["name"] == "DocumentSymbols" and s["kind"] == 5), None)
                assert class_symbol is not None, "DocumentSymbols class should be present"
                assert class_symbol["range"]["start"]["line"] == 0
                
                # Verify property symbol
                property_symbol = next((s for s in symbols if s["name"] == "aProperty"), None)
                assert property_symbol is not None, "aProperty should be present in symbols"
                assert property_symbol["kind"] == 7, "aProperty should have kind=7 (Property)"
                
                # Verify function symbol
                function_symbol = next((s for s in symbols if s["name"] == "aFunction"), None)
                assert function_symbol is not None, "aFunction should be present in symbols"
                assert function_symbol["kind"] == 12, "aFunction should have kind=12 (Function)"
                
                # Verify companion objects
                companion_symbols = [s for s in symbols if s["name"] == "DocumentSymbols" and s["kind"] == 9]
                assert len(companion_symbols) == 2, "Should find exactly 2 companion object symbols"

def test_multilspy_kotlin_sync_definition() -> None:
    """
    Test definition lookup functionality using the sync API
    """
    params = {
        "code_language": Language.KOTLIN,
        "repo_url": "https://github.com/fwcd/kotlin-language-server/",
        "repo_commit": "8418fb560a4013c3e02c942797e9c877affa0a51"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("server/src/test/resources/definition/GoFrom.kt"))
        
        with lsp.start_server():
            with lsp.open_file(test_file):
                definition_result = lsp.request_definition(test_file, 2, 24)
                
                assert definition_result is not None, "Definition result should not be None"
                assert len(definition_result) == 1, "Should find exactly one definition"
                
                # Verify definition location
                definition = definition_result[0]
                assert definition["relativePath"].endswith("GoFrom.kt")
                assert definition["range"]["start"]["line"] == 6
                assert definition["range"]["start"]["character"] == 8
                assert definition["range"]["end"]["character"] == 24

def test_multilspy_kotlin_sync_references() -> None:
    """
    Test references lookup functionality using the sync API
    """
    params = {
        "code_language": Language.KOTLIN,
        "repo_url": "https://github.com/fwcd/kotlin-language-server/",
        "repo_commit": "8418fb560a4013c3e02c942797e9c877affa0a51"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("server/src/test/resources/references/ReferenceTo.kt"))
        
        with lsp.start_server():
            with lsp.open_file(test_file):
                references = lsp.request_references(test_file, 1, 8)
                
                assert references is not None, "References should not be None"
                assert len(references) == 2, "Should find exactly two references to foo()"
                
                # Verify references across files
                reference_paths = [ref["relativePath"] for ref in references]
                assert any("ReferenceTo.kt" in path for path in reference_paths)
                assert any("ReferenceFrom.kt" in path for path in reference_paths)
                
                # Verify reference positions
                ref_from = next((ref for ref in references if "ReferenceFrom.kt" in ref["relativePath"]), None)
                assert ref_from["range"]["start"]["line"] == 2
                assert ref_from["range"]["start"]["character"] == 20
                
                ref_to = next((ref for ref in references if "ReferenceTo.kt" in ref["relativePath"]), None)
                assert ref_to["range"]["start"]["line"] == 8
                assert ref_to["range"]["start"]["character"] == 20

def test_multilspy_kotlin_sync_hover() -> None:
    """
    Test hover information functionality using the sync API
    """
    params = {
        "code_language": Language.KOTLIN,
        "repo_url": "https://github.com/fwcd/kotlin-language-server/",
        "repo_commit": "8418fb560a4013c3e02c942797e9c877affa0a51"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("server/src/test/resources/hover/Literals.kt"))

        with lsp.start_server():
            with lsp.open_file(test_file):
                hover_result = lsp.request_hover(test_file, 2, 19)

                assert hover_result is not None, "Hover result should not be None"
                assert "contents" in hover_result, "Hover result should contain contents"
                assert "kind" in hover_result["contents"], "Hover contents should include kind"
                assert "value" in hover_result["contents"], "Hover contents should include value"

                # Verify hover content format and values
                assert hover_result["contents"]["kind"] == "markdown"
                assert "```kotlin" in hover_result["contents"]["value"]
                assert "val stringLiteral: String" in hover_result["contents"]["value"]

def test_multilspy_kotlin_sync_completions() -> None:
    """
    Test code completion functionality using the sync API
    """
    params = {
        "code_language": Language.KOTLIN,
        "repo_url": "https://github.com/fwcd/kotlin-language-server/",
        "repo_commit": "8418fb560a4013c3e02c942797e9c877affa0a51"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        # Use a file specifically designed for testing completions
        test_file = str(PurePath("server/src/test/resources/completions/InstanceMember.kt"))
        
        with lsp.start_server():
            with lsp.open_file(test_file):
                # Position after "instance." where completions should be available
                completions = lsp.request_completions(test_file, 2, 13)
                
                assert completions is not None, "Completions result should not be None"
                assert len(completions) > 0, "Should find at least one completion item"
                
                # Verify completion items have required properties
                for item in completions:
                    assert "completionText" in item, "Completion item should have completionText"
                    assert "kind" in item, "Completion item should have kind"
                
                # Verify expected completion items specific to this test file
                completion_texts = [c["completionText"] for c in completions]
                
                # Based on the test file, we expect to see "instanceFoo", "fooVar" and other members
                expected_completions = ["instanceFoo", "fooVar", "extensionFoo"]
                found_expected = any(expected in completion_texts for expected in expected_completions)
                
                assert found_expected, f"Should find expected completions from {expected_completions}, but found: {completion_texts[:5]}"
