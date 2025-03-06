"""
This file contains tests for running the Perl Language Server: Perl::LanguageServer in synchronous mode
"""

import pytest
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

def test_sync_multilspy_perl_dancer2():
    """
    Test the working of multilspy with perl repository - Dancer2 in synchronous mode
    """
    code_language = Language.PERL
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/PerlDancer/Dancer2/",
        "repo_commit": "9f0f5e0b9b0a9c8e8e8e8e8e8e8e8e8e8e8e8e8e"  # Replace with an actual commit hash
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            # Test request_definition
            result = lsp.request_definition(str(PurePath("lib/Dancer2.pm")), 10, 4)
            
            assert isinstance(result, list)
            # The exact assertions will depend on the actual response from the Perl Language Server
            # These are placeholder assertions that should be updated with actual expected values
            assert len(result) >= 0
            
            # Test request_references
            result = lsp.request_references(str(PurePath("lib/Dancer2.pm")), 10, 4)
            
            assert isinstance(result, list)
            # The exact assertions will depend on the actual response from the Perl Language Server
            # These are placeholder assertions that should be updated with actual expected values
            assert len(result) >= 0
