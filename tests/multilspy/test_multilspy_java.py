"""
This file contains tests for running the Java Language Server: Eclipse JDT.LS
"""

import pytest
from pathlib import PurePath
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from multilspy.multilspy_types import Position, CompletionItemKind
from tests.test_utils import create_test_context

pytest_plugins = ("pytest_asyncio",)

@pytest.mark.asyncio
async def test_multilspy_java_clickhouse_highlevel_sinker():
    """
    Test the working of multilspy with Java repository - clickhouse-highlevel-sinker
    """
    code_language = Language.JAVA
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/Index103000/clickhouse-highlevel-sinker/",
        "repo_commit": "ee31d278918fe5e64669a6840c4d8fb53889e573"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            filepath = str(PurePath("src/main/java/com/xlvchao/clickhouse/component/ClickHouseSinkManager.java"))
            result = await lsp.request_definition(filepath, 44, 59)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert item["relativePath"] == str(
                PurePath("src/main/java/com/xlvchao/clickhouse/component/ScheduledCheckerAndCleaner.java")
            )
            assert item["range"] == {
                "start": {"line": 22, "character": 11},
                "end": {"line": 22, "character": 37},
            }

            # TODO: The following test is running flaky on Windows. Investigate and fix.
            # On Windows, it returns the correct result sometimes and sometimes it returns the following:
            # incorrect_output = [
            #     {
            #         "range": {"end": {"character": 86, "line": 24}, "start": {"character": 65, "line": 24}},
            #         "relativePath": "src\\main\\java\\com\\xlvchao\\clickhouse\\component\\ClickHouseSinkManager.java",
            #     },
            #     {
            #         "range": {"end": {"character": 61, "line": 2}, "start": {"character": 7, "line": 2}},
            #         "relativePath": "src\\test\\java\\com\\xlvchao\\clickhouse\\SpringbootDemo.java",
            #     },
            #     {
            #         "range": {"end": {"character": 29, "line": 28}, "start": {"character": 8, "line": 28}},
            #         "relativePath": "src\\test\\java\\com\\xlvchao\\clickhouse\\SpringbootDemo.java",
            #     },
            #     {
            #         "range": {"end": {"character": 69, "line": 28}, "start": {"character": 48, "line": 28}},
            #         "relativePath": "src\\test\\java\\com\\xlvchao\\clickhouse\\SpringbootDemo.java",
            #     },
            # ]

            result = await lsp.request_references(filepath, 82, 27)

            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {
                    "relativePath": str(
                        PurePath("src/main/java/com/xlvchao/clickhouse/component/ClickHouseSinkManager.java")
                    ),
                    "range": {
                        "start": {"line": 75, "character": 66},
                        "end": {"line": 75, "character": 85},
                    },
                },
                {
                    "relativePath": str(
                        PurePath("src/main/java/com/xlvchao/clickhouse/component/ClickHouseSinkManager.java")
                    ),
                    "range": {
                        "start": {"line": 71, "character": 12},
                        "end": {"line": 71, "character": 31},
                    },
                },
            ]

            completions_filepath = "src/main/java/com/xlvchao/clickhouse/datasource/ClickHouseDataSource.java"
            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=74, character=17),
                    Position(line=78, character=4)
                )
                assert deleted_text == """newServerNode()
                .withIp(arr[0])
                .withPort(Integer.parseInt(arr[1]))
                .build();
    """
                completions = await lsp.request_completions(completions_filepath, 74, 17)
                completions = [completion["completionText"] for completion in completions]
                assert set(completions) == set(['class', 'newServerNode'])
            
            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=75, character=17),
                    Position(line=78, character=4)
                )
                assert deleted_text == """withIp(arr[0])
                .withPort(Integer.parseInt(arr[1]))
                .build();
    """
                completions = await lsp.request_completions(completions_filepath, 75, 17)
                completions = [completion["completionText"] for completion in completions]
                assert set(completions) == set(['build', 'equals', 'getClass', 'hashCode', 'toString', 'withIp', 'withPort', 'notify', 'notifyAll', 'wait', 'wait', 'wait', 'newServerNode'])
            
            completions_filepath = "src/main/java/com/xlvchao/clickhouse/component/ClickHouseSinkBuffer.java"
            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=136, character=23),
                    Position(line=143, character=8)
                )
                assert deleted_text == """ClickHouseSinkBuffer(
                    this.writer,
                    this.writeTimeout,
                    this.batchSize,
                    this.clazz,
                    this.futures
            );
        """
                completions = await lsp.request_completions(completions_filepath, 136, 23)
                completions = [completion["completionText"] for completion in completions if completion["kind"] == CompletionItemKind.Constructor]
                assert completions == ['ClickHouseSinkBuffer']

@pytest.mark.asyncio
async def test_multilspy_java_clickhouse_highlevel_sinker_modified():
    """
    Test the working of multilspy with Java repository - clickhouse-highlevel-sinker
    """
    code_language = Language.JAVA
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/clickhouse-highlevel-sinker/",
        "repo_commit": "5775fd7a67e7b60998e1614cf44a8a1fc3190ab0"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            completions_filepath = "src/main/java/com/xlvchao/clickhouse/datasource/ClickHouseDataSource.java"
            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=74, character=17),
                    Position(line=77, character=4)
                )
                assert deleted_text == """newServerNode()
                .withIpPort(arr[0], Integer.parseInt(arr[1]))
                .build();
    """
                completions = await lsp.request_completions(completions_filepath, 74, 17)
                completions = [completion["completionText"] for completion in completions]
                assert set(completions) == set(['class', 'newServerNode'])

            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=75, character=17),
                    Position(line=77, character=4)
                )
                assert deleted_text == """withIpPort(arr[0], Integer.parseInt(arr[1]))
                .build();
    """
                completions = await lsp.request_completions(completions_filepath, 75, 17)
                completions = [completion["completionText"] for completion in completions]
                assert set(completions) == set(['build', 'equals', 'getClass', 'hashCode', 'toString', 'withIpPort', 'notify', 'notifyAll', 'wait', 'wait', 'wait', 'newServerNode'])

            completions_filepath = "src/main/java/com/xlvchao/clickhouse/component/ClickHouseSinkBuffer.java"
            with lsp.open_file(completions_filepath):
                deleted_text = lsp.delete_text_between_positions(
                    completions_filepath,
                    Position(line=136, character=23),
                    Position(line=143, character=8)
                )
                assert deleted_text == """ClickHouseSinkBuffer(
                    this.writer,
                    this.writeTimeout,
                    this.batchSize,
                    this.clazz,
                    this.futures
            );
        """
                completions = await lsp.request_completions(completions_filepath, 136, 23)
                completions = [completion["completionText"] for completion in completions if completion["kind"] == CompletionItemKind.Constructor]
                assert completions == ['ClickHouseSinkBuffer']

@pytest.mark.asyncio
async def test_multilspy_java_example_repo_document_symbols() -> None:
    """
    Test the working of multilspy with Java repository - clickhouse-highlevel-sinker
    """
    code_language = Language.JAVA
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/ExampleRepo/",
        "repo_commit": "f3762fd55a457ff9c6b0bf3b266de2b203a766ab",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        async with lsp.start_server():
            filepath = str(PurePath("Person.java"))
            result = await lsp.request_document_symbols(filepath)

            assert result == (
                [
                    {
                        "name": "Person",
                        "kind": 5,
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 14, "character": 1},
                        },
                        "selectionRange": {
                            "start": {"line": 1, "character": 22},
                            "end": {"line": 1, "character": 28},
                        },
                        "detail": "",
                    },
                    {
                        "name": "name",
                        "kind": 8,
                        "range": {
                            "start": {"line": 2, "character": 4},
                            "end": {"line": 3, "character": 24},
                        },
                        "selectionRange": {
                            "start": {"line": 3, "character": 19},
                            "end": {"line": 3, "character": 23},
                        },
                        "detail": "",
                    },
                    {
                        "name": "Person(String)",
                        "kind": 9,
                        "range": {
                            "start": {"line": 5, "character": 4},
                            "end": {"line": 8, "character": 5},
                        },
                        "selectionRange": {
                            "start": {"line": 6, "character": 11},
                            "end": {"line": 6, "character": 17},
                        },
                        "detail": "",
                    },
                    {
                        "name": "getName()",
                        "kind": 6,
                        "range": {
                            "start": {"line": 10, "character": 4},
                            "end": {"line": 13, "character": 5},
                        },
                        "selectionRange": {
                            "start": {"line": 11, "character": 18},
                            "end": {"line": 11, "character": 25},
                        },
                        "detail": " : String",
                    },
                ],
                None,
            )

            filepath = str(PurePath("Student.java"))
            result = await lsp.request_document_symbols(filepath)

            assert result == (
                [
                    {
                        "name": "Student",
                        "kind": 5,
                        "range": {
                            "start": {"line": 0, "character": 0},
                            "end": {"line": 16, "character": 1},
                        },
                        "selectionRange": {
                            "start": {"line": 1, "character": 13},
                            "end": {"line": 1, "character": 20},
                        },
                        "detail": "",
                    },
                    {
                        "name": "id",
                        "kind": 8,
                        "range": {
                            "start": {"line": 2, "character": 4},
                            "end": {"line": 3, "character": 19},
                        },
                        "selectionRange": {
                            "start": {"line": 3, "character": 16},
                            "end": {"line": 3, "character": 18},
                        },
                        "detail": "",
                    },
                    {
                        "name": "Student(String, int)",
                        "kind": 9,
                        "range": {
                            "start": {"line": 5, "character": 4},
                            "end": {"line": 10, "character": 5},
                        },
                        "selectionRange": {
                            "start": {"line": 6, "character": 11},
                            "end": {"line": 6, "character": 18},
                        },
                        "detail": "",
                    },
                    {
                        "name": "getId()",
                        "kind": 6,
                        "range": {
                            "start": {"line": 12, "character": 4},
                            "end": {"line": 15, "character": 5},
                        },
                        "selectionRange": {
                            "start": {"line": 13, "character": 15},
                            "end": {"line": 13, "character": 20},
                        },
                        "detail": " : int",
                    },
                ],
                None,
            )

@pytest.mark.asyncio
async def test_multilspy_java_clickhouse_highlevel_sinker_modified_hover():
    """
    Test the working of textDocument/hover with Java repository - clickhouse-highlevel-sinker modified
    """
    code_language = Language.JAVA
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/clickhouse-highlevel-sinker/",
        "repo_commit": "5775fd7a67e7b60998e1614cf44a8a1fc3190ab0"
    }

    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            filepath = "src/main/java/com/xlvchao/clickhouse/datasource/ClickHouseDataSource.java"
            with lsp.open_file(filepath):
                deleted_text = lsp.delete_text_between_positions(
                    filepath,
                    Position(line=75, character=28),
                    Position(line=77, character=4)
                )
                assert deleted_text == """arr[0], Integer.parseInt(arr[1]))
                .build();
    """

                lsp.insert_text_at_position(filepath, 75, 28, ")")
                
                result = await lsp.request_hover(filepath, 75, 27)

                assert result == {
                    "contents": {
                        "language": "java",
                        "value": "Builder com.xlvchao.clickhouse.datasource.ServerNode.Builder.withIpPort(String ip, Integer port)",
                    }
                }

@pytest.mark.asyncio
async def test_multilspy_java_clickhouse_highlevel_sinker_modified_completion_method_signature():
    """
    Test the working of textDocument/hover with Java repository - clickhouse-highlevel-sinker modified
    """
    code_language = Language.JAVA
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/clickhouse-highlevel-sinker/",
        "repo_commit": "5775fd7a67e7b60998e1614cf44a8a1fc3190ab0"
    }

    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            filepath = "src/main/java/com/xlvchao/clickhouse/datasource/ClickHouseDataSource.java"
            with lsp.open_file(filepath):
                deleted_text = lsp.delete_text_between_positions(
                    filepath,
                    Position(line=75, character=27),
                    Position(line=77, character=4)
                )
                assert deleted_text == """(arr[0], Integer.parseInt(arr[1]))
                .build();
    """
                
                result = await lsp.request_completions(filepath, 75, 27)

                assert result == [
                    {
                        "completionText": "withIpPort",
                        "detail": "Builder.withIpPort(String ip, Integer port) : Builder",
                        "kind": 2,
                    }
                ]

@pytest.mark.asyncio
async def test_multilspy_java_example_repo_prepare_and_incoming_call_hierarchy() -> None:
    """
    Test the working of textDocument/callHierarchy with Java repository - clickhouse-highlevel-sinker
    """
    code_language = Language.JAVA
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/clickhouse-highlevel-sinker/",
        "repo_commit": "5775fd7a67e7b60998e1614cf44a8a1fc3190ab0"
    }

    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            filepath = str(PurePath("src/main/java/com/xlvchao/clickhouse/model/ClickHouseSinkRequest.java"))

            # prepare call hierarchy by resolve request method position to CallHierarchyItem
            result = await lsp.request_prepare_call_hierarchy(filepath, 22, 16)

            assert len(result) == 1
            # method package and class name
            assert result[0]['detail'] == 'com.xlvchao.clickhouse.model.ClickHouseSinkRequest'
            # method signature
            assert result[0]['name'] == 'incrementCounter() : void'
            # method file uri
            assert result[0]['uri'].endswith('src/main/java/com/xlvchao/clickhouse/model/ClickHouseSinkRequest.java')
            # range of the method definition includes method signature and body
            assert result[0]['range'] == {
                'start': {'line': 22, 'character': 4},
                'end': {'line': 24, 'character': 5}
            }
            # selection range includes the method name
            assert result[0]['selectionRange'] == {
                'start': {'line': 22, 'character': 16},
                'end': {'line': 22, 'character': 32}
            }

            # get incoming call hierarchy for the resolved method(only one depth)
            incoming_call_dep_one = await lsp.request_incoming_calls(result[0])

            assert len(incoming_call_dep_one) == 1
            # caller method is defined in nested class WriterTask inside ClickHouseWriter thus ClickHouseWriter$WriterTask
            assert incoming_call_dep_one[0]['detail'] == 'com.xlvchao.clickhouse.component.ClickHouseWriter$WriterTask'
            # caller method signature
            assert incoming_call_dep_one[0]['name'] == 'handleUnsuccessfulResponse(ClickHouseSinkRequest, CompletableFuture<Boolean>) : void'
            # caller method file uri
            assert incoming_call_dep_one[0]['uri'].endswith('src/main/java/com/xlvchao/clickhouse/component/ClickHouseWriter.java')
            # range of the caller method definition includes method signature and body
            assert incoming_call_dep_one[0]['range'] == {
                'start': {'line': 240, 'character': 8},
                'end': {'line': 264, 'character': 9}
            }
            # selection range where the requested method being called within this caller method.
            assert incoming_call_dep_one[0]['selectionRange'] == {
                'start': {'line': 249, 'character': 32},
                'end': {'line': 249, 'character': 50}
            }

            # recursively get one more depth in incoming call hierarchy
            incoming_call_dep_two = await lsp.request_incoming_calls(incoming_call_dep_one[0])
            print(incoming_call_dep_two)
            assert len(incoming_call_dep_two) == 1
            assert incoming_call_dep_two[0]['name'] == 'flushToClickHouse(ClickHouseSinkRequest, CompletableFuture<Boolean>) : void'
