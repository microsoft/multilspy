"""
Standardized package coordinate and external path classification for multilspy and Repolex.

Classifies resolved symbol and definition file paths across all supported language ecosystems:
- Elixir: Hex/Mix dependencies in deps/<package>/lib/... and _build/...
- Swift: Swift Package Manager checkouts in .build/checkouts/<package>/... and Apple SDK frameworks
- Scala/Java: Coursier cache, Maven local repo (~/.m2), Ivy cache, Metals readonly jars
- PHP: Composer dependencies in vendor/<vendor>/<package>/...
- Python: site-packages, dist-packages, stdlib
- JS/TS: node_modules/<package>/... and @scope packages
- Rust: Cargo registry (~/.cargo/registry/src/...) and git checkouts
- Go: go/pkg/mod/... and vendor/...
- Ruby: gems/... and vendor/bundle/...
- C#: NuGet packages in ~/.nuget/packages/...
- Dart: Pub cache in ~/.pub-cache/hosted/pub.dev/...
- Lua: LuaRocks packages in ~/.luarocks/... and lua_modules/...
- Bash: Basher packages, Bats libraries, and bash-completion
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import PurePath
from typing import Optional, Union, Tuple, Iterator, Dict, Any


@dataclass(frozen=True)
class PathClassification:
    """
    Standardized classification of a file path.

    Supports tuple unpacking:
        is_external, package_name, package_relative_path = classification
    """
    is_external: bool
    package_name: Optional[str] = None
    package_relative_path: Optional[str] = None
    ecosystem: Optional[str] = None
    version: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def __iter__(self) -> Iterator[Union[bool, Optional[str]]]:
        """Allows unpacking as (is_external, package_name, package_relative_path)."""
        yield self.is_external
        yield self.package_name
        yield self.package_relative_path

    def as_tuple(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """Returns (is_external, package_name, package_relative_path)."""
        return self.is_external, self.package_name, self.package_relative_path


class PathClassifier:
    """
    Inspects resolved file paths to identify external library dependencies and
    extract canonical package coordinates.
    """

    @staticmethod
    def normalize_path(path: str) -> str:
        """Standardize separators and strip URI schemes or jar delimiters."""
        if path.startswith("file://"):
            path = path[7:]
        elif path.startswith("jar:file:"):
            path = path[9:]
        return path.replace("\\", "/")

    @classmethod
    def classify(
        cls,
        path: str,
        repository_root_path: Optional[str] = None,
        language: Optional[str] = None,
    ) -> PathClassification:
        """
        Classifies a file path into internal vs. external package coordinate.

        :param path: Absolute or relative file path returned by language server.
        :param repository_root_path: Optional root directory of the repository being indexed.
        :param language: Optional language hint (e.g. 'elixir', 'swift', 'scala', 'php').
        :return: PathClassification object with is_external, package_name, package_relative_path, ecosystem, version.
        """
        norm_path = cls.normalize_path(path)

        # -------------------------------------------------------------------------
        # 1. Elixir (Hex / Mix)
        # -------------------------------------------------------------------------
        # Workspace dependency: deps/<package>/...
        m = re.search(r"(?:^|/)deps/([a-zA-Z0-9_]+)/(.*)$", norm_path)
        if m:
            pkg = m.group(1)
            rel = m.group(2)
            return PathClassification(
                is_external=True,
                package_name=pkg,
                package_relative_path=rel,
                ecosystem="HEX",
            )

        # Build directory: _build/<env>/lib/<package>/...
        m = re.search(r"(?:^|/)_build/[^/]+/lib/([a-zA-Z0-9_]+)/(.*)$", norm_path)
        if m:
            pkg = m.group(1)
            rel = m.group(2)
            return PathClassification(
                is_external=True,
                package_name=pkg,
                package_relative_path=rel,
                ecosystem="HEX",
            )

        # System Elixir / Erlang lib
        m = re.search(r"/(?:lib|opt)/(?:elixir|erlang)/lib/([a-zA-Z0-9_]+)(?:-[\d.]+)?/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(2),
                ecosystem="HEX",
            )

        # -------------------------------------------------------------------------
        # 2. Swift (Swift Package Manager & Apple SDKs)
        # -------------------------------------------------------------------------
        # SPM checkouts: .build/checkouts/<package>/...
        m = re.search(r"(?:^|/)\.build/checkouts/([a-zA-Z0-9_.-]+)/(.*)$", norm_path)
        if m:
            pkg = m.group(1)
            rel = m.group(2)
            return PathClassification(
                is_external=True,
                package_name=pkg,
                package_relative_path=rel,
                ecosystem="SWIFT",
            )

        # SPM repositories cache
        m = re.search(r"(?:^|/)\.build/repositories/([a-zA-Z0-9_.-]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(2),
                ecosystem="SWIFT",
            )

        # Apple SDK frameworks: /.../System/Library/Frameworks/<Framework>.framework/...
        m = re.search(r"/System/Library/Frameworks/([a-zA-Z0-9_]+)\.framework/(.*)$", norm_path)
        if m:
            framework = m.group(1)
            rel = m.group(2)
            return PathClassification(
                is_external=True,
                package_name=framework,
                package_relative_path=rel,
                ecosystem="SWIFT",
            )

        # Swift toolchain stdlib: /usr/lib/swift/... or /Developer/.../usr/lib/swift/...
        m = re.search(r"/usr/lib/swift/(?:.*\/)?([a-zA-Z0-9_.-]+\.swiftinterface)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name="apple/swift",
                package_relative_path=m.group(1),
                ecosystem="SWIFT",
            )

        # -------------------------------------------------------------------------
        # 3. Scala / Java (Coursier, Maven .m2, Ivy, Metals)
        # -------------------------------------------------------------------------
        # Coursier cache: .../coursier/.../maven2/{group}/{artifact}/{version}/{artifact}-{version}-sources.jar!/...
        m = re.search(
            r"maven2/(.+?)/([^/]+)/([\d][^/]*)/(?:[^/]+\.jar!/|[^/]+\.jar)?(.*)$",
            norm_path,
        )
        if m:
            group = m.group(1).replace("/", ".")
            raw_artifact = m.group(2)
            version = m.group(3)
            rel = m.group(4) if m.group(4) else None
            # Strip Scala binary version suffix (_2.13, _3, _2.12)
            artifact = re.sub(r"_(?:2\.1[0-3]|3)$", "", raw_artifact)
            pkg_name = f"{group}:{artifact}"
            return PathClassification(
                is_external=True,
                package_name=pkg_name,
                package_relative_path=rel,
                ecosystem="MAVEN",
                version=version,
            )

        # Maven local repo: .../.m2/repository/{group}/{artifact}/{version}/...
        m = re.search(
            r"/repository/(.+?)/([^/]+)/([\d][^/]*)/(?:[^/]+\.jar!/|[^/]+\.jar)?(.*)$",
            norm_path,
        )
        if m:
            group = m.group(1).replace("/", ".")
            raw_artifact = m.group(2)
            version = m.group(3)
            rel = m.group(4) if m.group(4) else None
            artifact = re.sub(r"_(?:2\.1[0-3]|3)$", "", raw_artifact)
            pkg_name = f"{group}:{artifact}"
            return PathClassification(
                is_external=True,
                package_name=pkg_name,
                package_relative_path=rel,
                ecosystem="MAVEN",
                version=version,
            )

        # Ivy cache: .../.ivy2/cache/{org}/{artifact}/...
        m = re.search(
            r"\.ivy2/cache/(.+?)/([^/]+)/(?:srcs|jars)/[^/]+\.jar(?:!/(.*))?$",
            norm_path,
        )
        if m:
            group = m.group(1).replace("/", ".")
            artifact = re.sub(r"_(?:2\.1[0-3]|3)$", "", m.group(2))
            rel = m.group(3) if m.group(3) else None
            return PathClassification(
                is_external=True,
                package_name=f"{group}:{artifact}",
                package_relative_path=rel,
                ecosystem="MAVEN",
            )

        # Metals readonly jar dependencies: .metals/readonly/dependencies/{artifact}-{version}-sources.jar!/...
        m = re.search(
            r"\.metals/readonly/dependencies/(?:[^/]+\.jar!/)?(.*)$",
            norm_path,
        )
        if m:
            return PathClassification(
                is_external=True,
                package_name="metals:dependency",
                package_relative_path=m.group(1),
                ecosystem="MAVEN",
            )

        # JDK stdlib module: /java.base/java.lang/System.class
        m = re.search(r"/(java\.[a-z.]+)/([a-z][a-z0-9_.]+)/(.*)$", norm_path)
        if m:
            jdk_module = m.group(1)
            java_pkg = m.group(2)
            rel = m.group(3)
            return PathClassification(
                is_external=True,
                package_name=f"{jdk_module}:{java_pkg}",
                package_relative_path=rel,
                ecosystem="JDK_STDLIB",
            )

        # -------------------------------------------------------------------------
        # 4. PHP (Composer / Packagist)
        # -------------------------------------------------------------------------
        m = re.search(r"(?:^|/)vendor/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)/(.*)$", norm_path)
        if m:
            vendor_name = m.group(1)
            pkg_name = m.group(2)
            # Skip bin or composer internal directories
            if vendor_name.lower() not in ("bin", "composer"):
                canonical_name = f"{vendor_name}/{pkg_name}"
                rel = m.group(3)
                return PathClassification(
                    is_external=True,
                    package_name=canonical_name,
                    package_relative_path=rel,
                    ecosystem="PACKAGIST",
                )

        # -------------------------------------------------------------------------
        # 5. JavaScript / TypeScript (NPM)
        # -------------------------------------------------------------------------
        m = re.search(
            r"(?:^|/)node_modules/(@[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+|[a-zA-Z0-9_.-]+)/(.*)$",
            norm_path,
        )
        if m:
            pkg = m.group(1)
            rel = m.group(2)
            return PathClassification(
                is_external=True,
                package_name=pkg,
                package_relative_path=rel,
                ecosystem="NPM",
            )

        # -------------------------------------------------------------------------
        # 6. Python (PyPI)
        # -------------------------------------------------------------------------
        m = re.search(
            r"(?:^|/)(?:site-packages|dist-packages)/([a-zA-Z0-9_.-]+)/(.*)$",
            norm_path,
        )
        if m:
            pkg = m.group(1)
            rel = m.group(2)
            version = None
            # Extract version from sibling or parent .dist-info if in path
            dist_match = re.search(r"([a-zA-Z0-9_.-]+)-([\d.]+)\.dist-info", norm_path)
            if dist_match:
                version = dist_match.group(2)
            return PathClassification(
                is_external=True,
                package_name=pkg,
                package_relative_path=rel,
                ecosystem="PYPI",
                version=version,
            )

        # -------------------------------------------------------------------------
        # 7. Rust (Cargo)
        # -------------------------------------------------------------------------
        # Registry cache: .cargo/registry/src/.../{pkg}-{version}/...
        m = re.search(r"\.cargo/registry/src/[^/]+/([^/]+)/(.*)$", norm_path)
        if m:
            pkg_with_version = m.group(1)
            rel = m.group(2)
            parts = pkg_with_version.rsplit("-", 1)
            if len(parts) == 2 and re.match(r"^[\d.]+", parts[1]):
                pkg = parts[0]
                version = parts[1]
            else:
                pkg = pkg_with_version
                version = None
            return PathClassification(
                is_external=True,
                package_name=pkg,
                package_relative_path=rel,
                ecosystem="CARGO",
                version=version,
            )

        # Git checkouts: .cargo/git/checkouts/{repo}/...
        m = re.search(r"\.cargo/git/checkouts/([^/]+)/[^/]+/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(2),
                ecosystem="CARGO",
            )

        # -------------------------------------------------------------------------
        # 8. Go (Go Modules / Vendor)
        # -------------------------------------------------------------------------
        m = re.search(r"/go/pkg/mod/(.+?)@v?([^/]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(3),
                ecosystem="GO",
                version=m.group(2),
            )

        # Go vendor: vendor/{module}/...
        if language == "go" or "/go/" in norm_path:
            m = re.search(r"(?:^|/)vendor/(.+)$", norm_path)
            if m:
                return PathClassification(
                    is_external=True,
                    package_name=m.group(1).split("/")[0],
                    package_relative_path=m.group(1),
                    ecosystem="GO",
                )

        # -------------------------------------------------------------------------
        # 9. Ruby (RubyGems / Bundler)
        # -------------------------------------------------------------------------
        m = re.search(r"(?:^|/)gems/([a-zA-Z0-9_-]+)-([\d.]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(3),
                ecosystem="RUBYGEMS",
                version=m.group(2),
            )

        # -------------------------------------------------------------------------
        # 10. C# (NuGet)
        # -------------------------------------------------------------------------
        m = re.search(r"\.nuget/packages/([^/]+)/([^/]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(3),
                ecosystem="NUGET",
                version=m.group(2),
            )

        # -------------------------------------------------------------------------
        # 11. Dart (Pub)
        # -------------------------------------------------------------------------
        m = re.search(r"\.pub-cache/hosted/pub\.dev/([a-zA-Z0-9_-]+)-([\d.]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(3),
                ecosystem="PUB",
                version=m.group(2),
            )

        # -------------------------------------------------------------------------
        # 12. Lua (LuaRocks / Modules)
        # -------------------------------------------------------------------------
        # Versioned rocks tree: rocks-5.x/<package>/<version>/...
        m = re.search(r"(?:^|/)rocks-5\.[0-9]+/([a-zA-Z0-9_.-]+)/([^/]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(3),
                ecosystem="LUAROCKS",
                version=m.group(2),
            )

        # Module trees: ~/.luarocks/share/lua/5.x/..., lua_modules/share/lua/5.x/..., share/lua/5.x/...
        m = re.search(r"(?:^|/)(?:\.luarocks|lua_modules|share|lib)/.*?lua/5\.[0-9]+/([a-zA-Z0-9_.-]+?)(?:/(.*)|\.lua)$", norm_path)
        if m:
            pkg = m.group(1)
            rel = m.group(2) if m.group(2) else f"{pkg}.lua"
            return PathClassification(
                is_external=True,
                package_name=pkg,
                package_relative_path=rel,
                ecosystem="LUAROCKS",
            )

        # -------------------------------------------------------------------------
        # 13. Bash / Shell (Basher, Bats, Completions)
        # -------------------------------------------------------------------------
        # Basher packages: ~/.basher/cellar/packages/<author>/<pkg>/...
        m = re.search(r"\.basher/cellar/packages/([^/]+)/([^/]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=f"{m.group(1)}/{m.group(2)}",
                package_relative_path=m.group(3),
                ecosystem="BASH",
            )

        # Bats test libraries: bats-<lib>/...
        m = re.search(r"(?:^|/)(bats-[a-zA-Z0-9_-]+)/(.*)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name=m.group(1),
                package_relative_path=m.group(2),
                ecosystem="BASH",
            )

        # Bash completion files: bash-completion/completions/<name> or bash_completion.d/<name>
        m = re.search(r"(?:^|/)(?:bash-completion/completions|bash_completion\.d)/([^/]+)$", norm_path)
        if m:
            return PathClassification(
                is_external=True,
                package_name="bash-completion",
                package_relative_path=m.group(1),
                ecosystem="BASH",
            )

        # -------------------------------------------------------------------------
        # 14. Intra-Repository vs Unclassified External Check
        # -------------------------------------------------------------------------
        if repository_root_path:
            norm_repo = cls.normalize_path(repository_root_path).rstrip("/")
            if norm_path.startswith(norm_repo + "/") or norm_path == norm_repo:
                rel = norm_path[len(norm_repo) + 1:]
                return PathClassification(
                    is_external=False,
                    package_name=None,
                    package_relative_path=rel,
                    ecosystem=None,
                )
            else:
                # Path is outside repository root
                return PathClassification(
                    is_external=True,
                    package_name=None,
                    package_relative_path=norm_path,
                    ecosystem=None,
                )

        # If no repository root provided and no external markers found:
        return PathClassification(
            is_external=False,
            package_name=None,
            package_relative_path=norm_path,
            ecosystem=None,
        )
