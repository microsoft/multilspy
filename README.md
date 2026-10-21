[![PyPI - Version](https://img.shields.io/pypi/v/multilspy)](https://pypi.org/project/multilspy/)
# Multilspy: LSP client library in Python to build applications around language servers

## Introduction
This repository hosts `multilspy`, a library developed as part of research conducted for NeruIPS 2023 paper titled ["Monitor-Guided Decoding of Code LMs with Static Analysis of Repository Context"](https://neurips.cc/virtual/2023/poster/70362) (["Guiding Language Models of Code with Global Context using Monitors"](https://arxiv.org/abs/2306.10763) on Arxiv). The paper introduces Monitor-Guided Decoding (MGD) for code generation using Language Models, where a monitor uses static analysis to guide the decoding, ensuring that the generated code follows various correctness properties, like absence of hallucinated symbol names, valid order of method calls, etc. For further details about Monitor-Guided Decoding, please refer to the paper and GitHub repository [microsoft/monitors4codegen](https://github.com/microsoft/monitors4codegen).

`multilspy` is a cross-platform library designed to simplify the process of creating language server clients to query and obtain results of various static analyses from a wide variety of language servers that communicate over the [Language Server Protocol](https://microsoft.github.io/language-server-protocol/). It is easily extensible to support any [language that has a Language Server](https://microsoft.github.io/language-server-protocol/implementors/servers/) and we aim to continuously add support for more language servers and languages.

[Language servers]((https://microsoft.github.io/language-server-protocol/overviews/lsp/overview/)) are tools that perform a variety of static analyses on code repositories and provide useful information such as type-directed code completion suggestions, symbol definition locations, symbol references, etc., over the [Language Server Protocol (LSP)](https://microsoft.github.io/language-server-protocol/overviews/lsp/overview/). Since LSP is language-agnostic, `multilspy` can provide the results for static analyses of code in different languages over a common interface.

`multilspy` intends to ease the process of using language servers, by handling various steps in using a language server:
* Automatically handling the download of platform-specific server binaries, and setup/teardown of language servers
* Handling JSON-RPC based communication between the client and the server
* Maintaining and passing hand-tuned server and language specific configuration parameters
* Providing a simple API to the user, while executing all steps of server-specific protocol steps to execute the query/request.

Some of the analysis results that `multilspy` can provide are:
- Finding the definition of a function or a class ([textDocument/definition](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_definition))
- Finding the callers of a function or the instantiations of a class ([textDocument/references](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_references))
- Providing type-based dereference completions ([textDocument/completion](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_completion))
- Getting information displayed when hovering over symbols, like method signature ([textDocument/hover](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_hover))
- Getting list/tree of all symbols defined in a given file, along with symbol type like class, method, etc. ([textDocument/documentSymbol](https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#textDocument_documentSymbol))
- Please create an issue/PR to add any other LSP request not listed above

## Installation
Multilspy requires Python 3.10 or newer. We recommend creating a new virtual environment. To create a virtual environment using conda and activate it:
```
conda create -n multilspy_env python=3.10
conda activate multilspy_env
```
Further details and instructions on creation of Python virtual environments can be found in the [official documentation](https://docs.python.org/3/library/venv.html). Further, we also refer users to [Miniconda](https://docs.conda.io/en/latest/miniconda.html), as an alternative to the above steps for creation of the virtual environment.

To install `multilspy` using pip, execute the following command:
```
pip install multilspy
```

## Supported Languages
`multilspy` currently supports the following languages:
| Code Language | Language Server |
| --- | --- | 
| java | Eclipse JDTLS |
| python | jedi-language-server (default) or Pyright |
| rust | Rust Analyzer |
| csharp | OmniSharp / RazorSharp |
| typescript | TypeScriptLanguageServer |
| javascript | TypeScriptLanguageServer |
| go | gopls |
| dart | Dart |
| ruby | Solargraph |
| kotlin | KotlinLanguageServer |
| php | Intelephense |
| cpp | clangd |


For Python, Jedi remains the default language server. To use Pyright instead,
install [Pyright](https://github.com/microsoft/pyright) and explicitly select
the optional backend:

```python
from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

config = MultilspyConfig(
    code_language=Language.PYTHON,
    python_server="pyright",
    server_binary="/absolute/path/to/pyright-langserver",
)
lsp = LanguageServer.create(config, MultilspyLogger(), "/path/to/python/project")
async with lsp.start_server():
    definitions = await lsp.request_definition("module.py", 10, 4)
```

The server binary must already be installed; the adapter adds the --stdio
argument and does not download/install Pyright. If server_binary is
omitted, it uses pyright-langserver from PATH. The existing
MultilspyConfig(code_language=Language.PYTHON) continues using Jedi.

Positions follow LSP: line and column are zero-based and the column counts
UTF-16 code units, so a non-BMP character such as an emoji occupies two columns.
Type checking is configured by the project (pyrightconfig.json or pyproject.toml);
the adapter does not override `typeCheckingMode`.

The adapter was validated against Pyright 1.1.413 (`pyright-langserver --stdio`).
The table lists what that release advertises to multilspy's read-only client
and how multilspy exposes it:

| Pyright capability | multilspy access | Coverage |
| --- | --- | --- |
| definition, references, hover, document symbols, workspace symbols | `request_definition`, `request_references`, `request_hover`, `request_document_symbols`, `request_workspace_symbol` | tested against Pyright |
| completion (`isIncomplete` retries), completionItem/resolve | `request_completions`; resolve through `server.send.resolve_completion_item` | tested against Pyright |
| declaration, typeDefinition, documentHighlight, signatureHelp, call hierarchy (incoming and outgoing) | `server.send.*` low-level requests | tested against Pyright |
| prepareRename, rename | `server.send.*`; the response is a WorkspaceEdit proposal, multilspy never applies it | proposal shape tested |
| codeAction (quickfix, source.organizeImports) | `server.send.code_action`; available fixes depend on project diagnostics and may propose file edits, including type-stub generation or renames; organize imports uses a command | empty-response fixture tested; no writable quick-fix corpus |
| publishDiagnostics (typeCheckingMode off/basic/standard/strict) | asynchronous `PyrightServer.next_diagnostics()` bounded queue (not exposed by `SyncLanguageServer`) | tested against Pyright |
| workspace/configuration, workspace/applyEdit, client/registerCapability | answered by the adapter: fixed read-only settings, edits refused, registration acknowledged and ignored | tested with fixtures and against Pyright |
| executeCommand | advertised with an empty command list; `pyright.organizeimports` is disabled by the adapter settings, `pyright.createtypestub` writes files and is not supported | refusal of the server's applyEdit tested |
| implementation, pull diagnostics, semantic tokens, inlay hints, folding, selection ranges, document links, formatting, code lens | not advertised to the current client capability profile by Pyright 1.1.413; requests fail with MethodNotFound | unsupported in this profile |

Real Pyright integration tests require a preinstalled language server. Set
MULTILSPY_PYRIGHT_TEST_BINARY to its absolute executable path before running
pytest on tests/multilspy/test_multilspy_pyright.py. Without this variable
the real-server tests skip; if it is set to a missing/non-executable binary,
the tests fail. The GitHub Actions test workflow installs pinned Pyright
1.1.413 and exercises the real provider on every Python test matrix entry.
Other local unit/fixture tests still run without installing Pyright.
Exact-protocol fixtures and capabilities are version-pinned; when upgrading
Pyright, update and revalidate the expected responses rather than silently
skipping mismatched versions. For third-party import resolution, configure the
project through `pyrightconfig.json` or `[tool.pyright]` in `pyproject.toml`.

By default, Pyright's `workspace/applyEdit` requests are refused and organize
imports is disabled. To support editor-controlled writes, the embedding client
can register an **async** handler before starting the server:

```python
# `lsp` is a PyrightServer returned by LanguageServer.create(...).
async def apply_workspace_edit(params):
    # Validate affected URIs, ranges, document versions and user permission.
    # Handle BOTH `changes` and `documentChanges` (including file operations)
    # and apply the edit atomically in YOUR editor/workspace layer.
    return {"applied": False, "failureReason": "Not approved"}

lsp.set_workspace_edit_handler(apply_workspace_edit, timeout_seconds=60)
```

When a handler is installed, the adapter advertises workspace `applyEdit`
support and enables Pyright organize-imports commands. The handler's LSP
response reports whether **the client actually applied the edit**. A successful
rename request by itself returns an edit *proposal*; multilspy does not apply
that proposal. It is the caller's responsibility to preview, approve, and
apply the WorkspaceEdit, including document versions and file operations.
If documents are already open, update both the editor's in-memory buffers
and the language server's `didChange` state; writing the disk copy alone leaves
the LSP document snapshot stale. Handler exceptions and timeouts are reported
as unsuccessful edits and never treated as authorization to write.

**Security boundary:** this opt-in callback is NOT a subprocess sandbox.
In Pyright 1.1.413, `pyright.createtypestub` directly writes `.pyi` files on
the language-server side without calling `workspace/applyEdit`. Other raw
`server.send.execute_command` calls may have similar side effects. Never expose
arbitrary commands to untrusted callers; use OS-level filesystem restrictions
and isolated workspaces for untrusted projects. An embedding application must enforce its own workspace authorization and
process confinement independently of multilspy's generic LSP integration.

## Usage
Example usage:
```python
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
...
config = MultilspyConfig.from_dict({"code_language": "java"}) # Also supports "python", "rust", "csharp", "typescript", "javascript", "go", "dart", "ruby", "kotlin", "php"
logger = MultilspyLogger()
lsp = SyncLanguageServer.create(config, logger, "/abs/path/to/project/root/")
with lsp.start_server():
    result = lsp.request_definition(
        "relative/path/to/code_file.java", # Filename of location where request is being made
        163, # line number of symbol for which request is being made
        4 # column number of symbol for which request is being made
    )
    result2 = lsp.request_completions(
        ...
    )
    result3 = lsp.request_references(
        ...
    )
    result4 = lsp.request_document_symbols(
        ...
    )
    result5 = lsp.request_hover(
        ...
    )
    ...
```

`multilspy` also provides an asyncio based API which can be used in async contexts. Example usage (asyncio):
```python
from multilspy import LanguageServer
...
lsp = LanguageServer.create(...)
async with lsp.start_server():
    result = await lsp.request_definition(
        ...
    )
    ...
```

The file [src/multilspy/language_server.py](src/multilspy/language_server.py) provides the `multilspy` API. Several tests for `multilspy` present under [tests/multilspy/](tests/multilspy/) provide detailed usage examples for `multilspy`. The tests can be executed by running:
```bash
pytest tests/multilspy
```

## Use of `multilspy` in AI4Code Scenarios like Monitor-Guided Decoding
`multilspy` provides all the features that language-server-protocol provides to IDEs like VSCode. It is useful to develop toolsets that can interface with AI systems like Large Language Models (LLM). 
### [Monitor-Guided Decoding](https://github.com/microsoft/monitors4codegen)
One such usecase is Monitor-Guided Decoding, where `multilspy` is used to find results of static analyses like type-directed completions, to guide the token-by-token generation of code using an LLM, ensuring that all generated identifier/method names are valid in the context of the repository, significantly boosting the compilability of generated code. MGD also demonstrates use of `multilspy` to create monitors that ensure all function calls in LLM generated code receive correct number of arguments, and that functions of an object are called in the right order following a protocol (like not calling "read" before "open" on a file object).

### Multilspy in other usecases
* ["Fix the Tests: Augmenting LLMs to Repair Test Cases with Static Collector and Neural Reranker," in 2024 IEEE 35th International Symposium on Software Reliability Engineering (ISSRE)](https://github.com/SQUARE-RG/SynTeR)
* [Tutorial on obtaining python completions with multilspy](https://medium.com/@techhara/python-obtain-completions-3db4d2479b82)
* Gathering and utilizing repository-wide context for repository-level coding agents

## Frequently Asked Questions (FAQ)
### ```asyncio``` related Runtime error when executing the tests for MGD
If you get the following error:
```
RuntimeError: Task <Task pending name='Task-2' coro=<_AsyncGeneratorContextManager.__aenter__() running at
    python3.8/contextlib.py:171> cb=[_chain_future.<locals>._call_set_state() at
    python3.8/asyncio/futures.py:367]> got Future <Future pending> attached to a different loop python3.8/asyncio/locks.py:309: RuntimeError
```

Please ensure that you create a new environment with Python ```>=3.10```. For further details, please have a look at the [StackOverflow Discussion](https://stackoverflow.com/questions/73599594/asyncio-works-in-python-3-10-but-not-in-python-3-8).

## Citing Multilspy
If you're using Multilspy in your research or applications, please cite using this BibTeX:
```
@inproceedings{NEURIPS2023_662b1774,
 author = {Agrawal, Lakshya A and Kanade, Aditya and Goyal, Navin and Lahiri, Shuvendu and Rajamani, Sriram},
 booktitle = {Advances in Neural Information Processing Systems},
 editor = {A. Oh and T. Naumann and A. Globerson and K. Saenko and M. Hardt and S. Levine},
 pages = {32270--32298},
 publisher = {Curran Associates, Inc.},
 title = {Monitor-Guided Decoding of Code LMs with Static Analysis of Repository Context},
 url = {https://proceedings.neurips.cc/paper_files/paper/2023/file/662b1774ba8845fc1fa3d1fc0177ceeb-Paper-Conference.pdf},
 volume = {36},
 year = {2023}
}
```

## Contributing

This project welcomes contributions and suggestions.  Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit https://cla.opensource.microsoft.com.

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft 
trademarks or logos is subject to and must follow 
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/en-us/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
