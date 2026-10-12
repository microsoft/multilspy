"""Runtime setup must preserve permissions when making binaries executable."""

import inspect
import json
import os
from pathlib import Path
import shutil
import stat

import pytest

from multilspy.language_servers.clangd_language_server.clangd_language_server import ClangdLanguageServer
from multilspy.language_servers.dart_language_server.dart_language_server import DartLanguageServer
from multilspy.language_servers.eclipse_jdtls.eclipse_jdtls import EclipseJDTLS
from multilspy.language_servers.omnisharp.omnisharp import OmniSharp
from multilspy.language_servers.rust_analyzer.rust_analyzer import RustAnalyzer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_utils import DotnetVersion, FileUtils, PlatformId, PlatformUtils


@pytest.mark.skipif(os.name == "nt", reason="Requires POSIX permission bits")
@pytest.mark.parametrize("mode", [0o600, 0o644, 0o755])
@pytest.mark.parametrize("server_class, language", [
    (ClangdLanguageServer, Language.CPP),
    (DartLanguageServer, Language.DART),
    (EclipseJDTLS, Language.JAVA),
    (OmniSharp, Language.CSHARP),
    (RustAnalyzer, Language.RUST),
])
def test_runtime_setup_preserves_binary_permissions(tmp_path, monkeypatch, server_class, language, mode):
    monkeypatch.setattr(PlatformUtils, "get_platform_id", lambda: PlatformId.LINUX_x64)
    monkeypatch.setattr(PlatformUtils, "get_dotnet_version", lambda: DotnetVersion.V6)

    def unexpected_download(*args, **kwargs):
        pytest.fail("All runtime dependencies should already exist")

    monkeypatch.setattr(FileUtils, "download_and_extract_archive", unexpected_download)
    manifest_path = Path(inspect.getfile(server_class)).with_name("runtime_dependencies.json")
    dependencies = json.loads(manifest_path.read_text())
    install_dir = tmp_path / "runtime"

    def create_file(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"runtime dependency\n")
        return path

    if server_class is EclipseJDTLS:
        version = dependencies["gradle"]["platform-agnostic"]["version"]
        (install_dir / f"gradle-{version}").mkdir(parents=True)
        java = dependencies["vscode-java"]["linux-x64"]
        java_dir = install_dir / java["relative_extraction_path"]
        (java_dir / java["jre_home_path"]).mkdir(parents=True)
        (java_dir / java["jdtls_readonly_config_path"]).mkdir(parents=True)
        for key in ("jre_path", "lombok_jar_path", "jdtls_launcher_jar_path"):
            create_file(java_dir / java[key])
        binary = java_dir / java["jre_path"]
        intellicode = dependencies["intellicode"]["platform-agnostic"]
        for key in ("intellicode_jar_path", "intellisense_members_path"):
            create_file(install_dir / intellicode["relative_extraction_path"] / intellicode[key])
    else:
        for dependency in dependencies["runtimeDependencies"]:
            if dependency["platformId"] != "linux-x64":
                continue
            if dependency.get("dotnet_version", DotnetVersion.V6.value) != DotnetVersion.V6.value:
                continue
            if server_class is OmniSharp:
                path = install_dir / dependency["id"]
                if dependency["id"] == "RazorOmnisharp":
                    create_file(path / dependency["dll_path"])
                    continue
            elif server_class is ClangdLanguageServer:
                path = install_dir / "clangd_19.1.2" / "bin"
            else:
                path = install_dir
            binary = create_file(path / dependency["binaryName"])

    binary.chmod(mode)
    config = MultilspyConfig(code_language=language, server_install_dir=str(install_dir))
    server = server_class.__new__(server_class)
    if server_class in (EclipseJDTLS, OmniSharp):
        setup = server.setupRuntimeDependencies
    else:
        setup = server.setup_runtime_dependencies

    # Repeated setup should also preserve the permissions of cached runtimes.
    for _ in range(2):
        setup(MultilspyLogger(), config)
        assert stat.S_IMODE(binary.stat().st_mode) == mode | stat.S_IXUSR
        copied_binary = tmp_path / "copied-binary"
        shutil.copy2(binary, copied_binary)
        assert copied_binary.read_bytes() == b"runtime dependency\n"
