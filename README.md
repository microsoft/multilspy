[![PyPI - Version](https://img.shields.io/pypi/v/multilspy)](https://pypi.org/project/multilspy/)
# Multilspy: LSP client library in Python to build applications around language servers

## Introduction
This repository hosts `multilspy`, a library developed as part of research conducted for NeruIPS 2023 paper titled ["Monitor-Guided Decoding of Code LMs with Static Analysis of Repository Context"](https://neurips.cc/virtual/2023/poster/70362) (["Guiding Language Models of Code with Global Context using Monitors"](https://arxiv.org/abs/2306.10763) on Arxiv). The paper introduces Monitor-Guided Decoding (MGD) for code generation using Language Models, where a monitor uses static analysis to guide the decoding, ensuring that the generated code follows various correctness properties, like absence of hallucinated symbol names, valid order of method calls, etc. For further details about Monitor-Guided Decoding, please refer to the paper and GitHub repository [microsoft/monitors4codegen](https://github.com/microsoft/monitors4codegen).

`multilspy` is a cross-platform library designed to simplify the process of creating language server clients to query and obtain results of various static analyses from a wide variety of language servers that communicate over the [Language Server Protocol](https://microsoft.github.io/language-server-protocol/). It is easily extensible to support any [language that has a Language Server](https://microsoft.github.io/language-server-protocol/implementors/servers/) and currently supports Java, Rust, C# and Python. We aim to continuously add support for more language servers and languages.

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
It is ideal to create a new virtual environment with `python>=3.10`. To create a virtual environment using conda and activate it:
```
conda create -n multilspy_env python=3.10
conda activate multilspy_env
```
Further details and instructions on creation of Python virtual environments can be found in the [official documentation](https://docs.python.org/3/library/venv.html). Further, we also refer users to [Miniconda](https://docs.conda.io/en/latest/miniconda.html), as an alternative to the above steps for creation of the virtual environment.

To install `multilspy` using pip, execute the following command:
```
pip install multilspy
```

## Usage
Example usage:
```python
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
...
config = MultilspyConfig.from_dict({"code_language": "java"}) # Also supports "python", "rust", "csharp"
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
