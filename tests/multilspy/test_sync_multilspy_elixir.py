"""
This file contains tests for running the Elixir Language Server: ElixirLS using sync interface
"""

import os
import tempfile
import contextlib
from pathlib import PurePath
from typing import Iterator

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from tests.multilspy.multilspy_context import MultilspyContext


@contextlib.contextmanager
def create_elixir_test_project() -> Iterator[str]:
    """
    Create a self-contained Elixir test project with multiple modules and functions.
    Returns the path to the project directory.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        project_dir = os.path.join(temp_dir, "test_elixir_project")
        os.makedirs(project_dir)

        # Create mix.exs
        mix_exs_content = '''defmodule TestElixirProject.MixProject do
  use Mix.Project

  def project do
    [
      app: :test_elixir_project,
      version: "0.1.0",
      elixir: "~> 1.14",
      start_permanent: Mix.env() == :prod,
      deps: deps()
    ]
  end

  def application do
    [
      extra_applications: [:logger]
    ]
  end

  defp deps do
    []
  end
end
'''
        with open(os.path.join(project_dir, "mix.exs"), "w") as f:
            f.write(mix_exs_content)

        # Create lib directory
        lib_dir = os.path.join(project_dir, "lib")
        os.makedirs(lib_dir)

        # Create main module
        main_module_content = '''defmodule TestElixirProject do
  @moduledoc """
  Documentation for `TestElixirProject`.
  """

  @doc """
  Hello world function.
  """
  def hello do
    :world
  end

  @doc """
  Adds two numbers together.
  """
  def add(a, b) do
    a + b
  end

  def greet(name) do
    "Hello, #{name}!"
  end

  defp private_helper do
    "This is a private function"
  end
end
'''
        with open(os.path.join(lib_dir, "test_elixir_project.ex"), "w") as f:
            f.write(main_module_content)

        # Create a math utility module
        math_module_content = '''defmodule TestElixirProject.Math do
  @moduledoc """
  Math utilities for the test project.
  """

  @doc """
  Multiplies two numbers.
  """
  def multiply(a, b) do
    a * b
  end

  @doc """
  Calculates the square of a number.
  """
  def square(n) do
    multiply(n, n)
  end

  @doc """
  Divides two numbers, returns {:ok, result} or {:error, reason}.
  """
  def divide(a, b) when b != 0 do
    {:ok, a / b}
  end

  def divide(_a, 0) do
    {:error, "Cannot divide by zero"}
  end
end
'''
        with open(os.path.join(lib_dir, "math.ex"), "w") as f:
            f.write(math_module_content)

        # Create a server module that calls other functions
        server_module_content = '''defmodule TestElixirProject.Server do
  @moduledoc """
  A simple server module that demonstrates function calls.
  """

  alias TestElixirProject.Math

  @doc """
  Starts the server.
  """
  def start do
    {:ok, :started}
  end

  @doc """
  Processes a calculation request.
  """
  def calculate(:add, a, b) do
    TestElixirProject.add(a, b)
  end

  def calculate(:multiply, a, b) do
    Math.multiply(a, b)
  end

  def calculate(:square, n) do
    Math.square(n)
  end

  def process_greeting(name) do
    TestElixirProject.greet(name)
  end

  defp log_operation(op, result) do
    "Operation #{op} completed with result: #{result}"
  end
end
'''
        with open(os.path.join(lib_dir, "server.ex"), "w") as f:
            f.write(server_module_content)

        # Create test directory and files
        test_dir = os.path.join(project_dir, "test")
        os.makedirs(test_dir)

        test_helper_content = '''ExUnit.start()
'''
        with open(os.path.join(test_dir, "test_helper.exs"), "w") as f:
            f.write(test_helper_content)

        test_module_content = '''defmodule TestElixirProjectTest do
  use ExUnit.Case
  doctest TestElixirProject

  test "greets the world" do
    assert TestElixirProject.hello() == :world
  end

  test "adds two numbers" do
    assert TestElixirProject.add(2, 3) == 5
  end

  test "math operations" do
    assert TestElixirProject.Math.multiply(4, 5) == 20
    assert TestElixirProject.Math.square(3) == 9
  end
end
'''
        with open(os.path.join(test_dir, "test_elixir_project_test.exs"), "w") as f:
            f.write(test_module_content)

        # Create .formatter.exs
        formatter_content = '''[
  inputs: ["{mix,.formatter}.exs", "{config,lib,test}/**/*.{ex,exs}"]
]
'''
        with open(os.path.join(project_dir, ".formatter.exs"), "w") as f:
            f.write(formatter_content)

        yield project_dir


@contextlib.contextmanager
def create_elixir_test_context() -> Iterator[MultilspyContext]:
    """
    Creates a test context with a local Elixir project.
    """
    with create_elixir_test_project() as project_dir:
        config = MultilspyConfig.from_dict({
            "code_language": Language.ELIXIR,
            "request_timeout": 30,
            "completions_timeout": 30
        })
        logger = MultilspyLogger()
        yield MultilspyContext(config, logger, project_dir)


def test_multilspy_elixir_basic_functionality_sync() -> None:
    """
    Test basic ElixirLS functionality with sync interface
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test 1: Document symbols - should find modules and functions
            result = lsp.request_document_symbols(str(PurePath("lib/test_elixir_project.ex")))
            assert isinstance(result, tuple)
            assert len(result) == 2  # (symbols, errors)

            if result[0]:  # If we have symbols
                symbol_names = [symbol["name"] for symbol in result[0]]
                # Should find the main module and its functions
                assert "TestElixirProject" in symbol_names
                assert any("hello" in name for name in symbol_names)

            # Test 2: Document symbols for math module
            result = lsp.request_document_symbols(str(PurePath("lib/math.ex")))
            assert isinstance(result, tuple)
            assert len(result) == 2

            if result[0]:
                symbol_names = [symbol["name"] for symbol in result[0]]
                assert "TestElixirProject.Math" in symbol_names


def test_multilspy_elixir_definitions_sync() -> None:
    """
    Test definition requests with sync interface
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test definition for Math.multiply call in server.ex
            result = lsp.request_definition(str(PurePath("lib/server.ex")), 27, 10)
            assert isinstance(result, list)

            # Test definition for TestElixirProject.add call
            result = lsp.request_definition(str(PurePath("lib/server.ex")), 23, 20)
            assert isinstance(result, list)


def test_multilspy_elixir_hover_sync() -> None:
    """
    Test hover functionality with sync interface
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test hover on 'defmodule' keyword - should return hover info
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 0, 8)
            assert isinstance(result, dict), "Should return hover info for defmodule keyword"

            # Test hover on module name "TestElixirProject" in defmodule declaration
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 0, 20)
            assert isinstance(result, dict), "Should return hover info for module name"

            # Test hover on :world atom - should return hover info
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 8, 4)
            assert isinstance(result, dict), "Should return hover info for atom"


def test_multilspy_elixir_hover_none_cases_sync() -> None:
    """
    Test hover positions that should specifically return None with sync interface
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test hover on function name in definition - should return None (you're already looking at the definition)
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 7, 6)
            assert result is None, "Should return None for function name in its own definition"

            # Test hover on parameter name - should return None
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 14, 4)
            assert result is None, "Should return None for parameter name"

            # Test hover on whitespace - should return None
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 1, 0)
            assert result is None, "Should return None for whitespace position"


def test_multilspy_elixir_workspace_symbols_sync() -> None:
    """
    Test workspace symbols with sync interface
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test searching for modules
            result = lsp.request_workspace_symbol("TestElixirProject")
            assert isinstance(result, list)

            # Test searching for functions
            result = lsp.request_workspace_symbol("multiply")
            assert isinstance(result, list)


def test_multilspy_elixir_references_sync() -> None:
    """
    Test references functionality with sync interface
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test references for Math.multiply function
            result = lsp.request_references(str(PurePath("lib/math.ex")), 6, 6)
            assert isinstance(result, list)

            # Clean up references results for comparison
            for item in result:
                if "uri" in item:
                    del item["uri"]
                if "absolutePath" in item:
                    del item["absolutePath"]


def test_multilspy_elixir_multiple_files_sync() -> None:
    """
    Test sync interface across multiple files
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test symbols across multiple files
            files_to_test = [
                "lib/test_elixir_project.ex",
                "lib/math.ex",
                "lib/server.ex"
            ]

            all_symbols = []
            for file_path in files_to_test:
                result = lsp.request_document_symbols(str(PurePath(file_path)))
                assert isinstance(result, tuple)
                assert len(result) == 2

                if result[0]:
                    all_symbols.extend([symbol["name"] for symbol in result[0]])

            # Verify we found symbols from multiple modules
            assert len(all_symbols) > 0
            assert any("TestElixirProject" in symbol for symbol in all_symbols)
            assert any("Math" in symbol for symbol in all_symbols)


def test_multilspy_elixir_error_handling_sync() -> None:
    """
    Test error handling with sync interface
    """
    with create_elixir_test_context() as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        with lsp.start_server():
            # Test definition request on non-existent file should handle gracefully
            try:
                result = lsp.request_definition("lib/nonexistent.ex", 1, 1)
                # Should return empty list or handle gracefully
                assert isinstance(result, list)
            except Exception:
                # It's acceptable for this to raise an exception
                pass

            # Test out-of-bounds position should handle gracefully
            result = lsp.request_definition(str(PurePath("lib/test_elixir_project.ex")), 99999, 99999)
            assert isinstance(result, list)

            # Test hover on edge case position - should return None
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 99999, 99999)
            assert result is None, "Should return None for out-of-bounds position"

            # Test hover on whitespace - should return None
            result = lsp.request_hover(str(PurePath("lib/test_elixir_project.ex")), 1, 0)
            assert result is None, "Should return None for whitespace position"