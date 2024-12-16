"""
This file contains tests for running the C# Language Server: OmniSharp
"""

import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from multilspy.multilspy_types import Position, CompletionItemKind
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_multilspy_csharp_ryujinx():
    """
    Test the working of multilspy with C# repository - Ryujinx
    """
    code_language = Language.CSHARP
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/Ryujinx/",
        "repo_commit": "e768a54f17b390c3ac10904c7909e3bef020edbd"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            result = await lsp.request_definition(str(PurePath("src/Ryujinx.Audio/Input/AudioInputManager.cs")), 176, 44)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert item["relativePath"] == str(PurePath("src/Ryujinx.Audio/Constants.cs"))
            assert item["range"] == {
                "start": {"line": 15, "character": 28},
                "end": {"line": 15, "character": 50},
            }

            result = await lsp.request_references(str(PurePath("src/Ryujinx.Audio/Constants.cs")), 15, 40)

            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {
                    "relativePath": str(PurePath("src/Ryujinx.Audio/Input/AudioInputManager.cs")),
                    "range": {
                        "start": {"line": 176, "character": 37},
                        "end": {"line": 176, "character": 59},
                    },
                },
                {
                    "relativePath": str(PurePath("src/Ryujinx.Audio/Input/AudioInputSystem.cs")),
                    "range": {
                        "start": {"line": 77, "character": 29},
                        "end": {"line": 77, "character": 51},
                    },
                },
            ]

            completions_filepath = "src/ARMeilleure/CodeGen/Arm64/CodeGenerator.cs"
            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=1352, character=21),
                    Position(line=1385, character=8)
                )
                assert deleted_text == """AccessSize.Byte:
                    context.Assembler.Ldaxrb(actual, address);
                    break;
                case AccessSize.Hword:
                    context.Assembler.Ldaxrh(actual, address);
                    break;
                default:
                    context.Assembler.Ldaxr(actual, address);
                    break;
            }

            context.Assembler.Cmp(actual, expected);

            context.JumpToNear(ArmCondition.Ne);

            switch (accessSize)
            {
                case AccessSize.Byte:
                    context.Assembler.Stlxrb(desired, address, result);
                    break;
                case AccessSize.Hword:
                    context.Assembler.Stlxrh(desired, address, result);
                    break;
                default:
                    context.Assembler.Stlxr(desired, address, result);
                    break;
            }

            context.Assembler.Cbnz(result, startOffset - context.StreamOffset); // Retry if store failed.

            context.JumpHere();

            context.Assembler.Clrex();
        """
                completions = await lsp.request_completions(completions_filepath, 1352, 21)
                completions = [completion["completionText"] for completion in completions if completion["kind"] == CompletionItemKind.EnumMember]
                assert set(completions) == set(['AccessSize.Byte', 'AccessSize.Hword', 'AccessSize.Auto'])
            
            completions_filepath = "src/ARMeilleure/CodeGen/X86/CodeGenerator.cs"
            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=226, character=79),
                    Position(line=243, character=28)
                )
                assert deleted_text == """Below);
                                    break;

                                case Intrinsic.X86Comisseq:
                                    context.Assembler.Comiss(src1, src2);
                                    context.Assembler.Setcc(dest, X86Condition.Equal);
                                    break;

                                case Intrinsic.X86Comissge:
                                    context.Assembler.Comiss(src1, src2);
                                    context.Assembler.Setcc(dest, X86Condition.AboveOrEqual);
                                    break;

                                case Intrinsic.X86Comisslt:
                                    context.Assembler.Comiss(src1, src2);
                                    context.Assembler.Setcc(dest, X86Condition.Below);
                                    break;
                            """
                completions = await lsp.request_completions(completions_filepath, 226, 79, allow_incomplete=True)
                completions = [completion["completionText"] for completion in completions if completion["kind"] != CompletionItemKind.Keyword]
                assert set(completions) == set(['NotSign', 'ParityOdd', 'NotOverflow', 'Less', 'AboveOrEqual', 'LessOrEqual', 'Overflow', 'Greater', 'ParityEven', 'Sign', 'BelowOrEqual', 'Equal', 'GreaterOrEqual', 'Below', 'Above', 'NotEqual'])