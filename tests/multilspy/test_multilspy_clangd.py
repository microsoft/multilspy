"""
This file contains tests for running the C/CPP Language Server: clangd
"""

import pytest
import os

from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)

def create_compile_commands_file(source_directory_path):
    """
    clangd requires compile_commands.json file to resolve dependencies in project.
    This file contains information such as how the source files are compiled.
    This file can be generated using different tools. CMake is used here to generate
    this file. For other options check: https://clangd.llvm.org/installation.html#project-setup
    """
    # get current working directory
    cwd = os.getcwd()
    # switch to repo directory
    os.chdir(source_directory_path)
    # set cmake to export compile commands
    os.system('cmake -DCMAKE_EXPORT_COMPILE_COMMANDS=1 -S . -B build')
    # generate build
    os.system('cmake --build build')
    # create sym link to compile commands at the top level
    os.system('ln -s build/compile_commands.json .')
    # return back to prev working dir
    os.chdir(cwd)

@pytest.mark.asyncio
async def test_multilspy_clang():
    """
    Test the working of multilspy with cpp repository - https://github.com/tomorrowCoder/yaml-cpp
    """
    code_language = Language.CPP
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/jbeder/yaml-cpp/",
        "repo_commit": "39f737443b05e4135e697cb91c2b7b18095acd53"
    }
    with create_test_context(params) as context:
        # create compile commands file before starting language server
        create_compile_commands_file(context.source_directory)
        # create language server
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        async with lsp.start_server():
            # get definition for create_node
            result = await lsp.request_definition(str(PurePath("src/node_data.cpp")), 241, 26)
            assert isinstance(result, list)
            assert len(result) > 0
            assert result[0]["relativePath"] == str(PurePath("include/yaml-cpp/node/detail/memory.h"))

            # find references for WriteCodePoint
            result = await lsp.request_references(str(PurePath("src/emitterutils.cpp")), 134, 6)
            assert isinstance(result, list)
            assert len(result) == 5

            # get hover information for strFormat variable
            result = await lsp.request_hover(str(PurePath("src/emitterutils.cpp")), 274, 11)
            assert result is not None
                                    
            # get document symbols for binary.cpp
            result = await lsp.request_document_symbols(str(PurePath("src/binary.cpp")))
            assert isinstance(result, tuple)
