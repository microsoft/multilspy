"""
Unit tests for PathClassifier and external package coordinate extraction.
"""

from multilspy.path_classifier import PathClassifier, PathClassification
from multilspy.multilspy_utils import PathClassifier as UtilsPathClassifier


def test_elixir_hex_classification():
    # Workspace deps
    path = "/Users/rob/projects/my_phoenix_app/deps/phoenix/lib/phoenix/endpoint.ex"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "phoenix"
    assert result.package_relative_path == "lib/phoenix/endpoint.ex"
    assert result.ecosystem == "HEX"

    # Tuple unpacking test
    is_ext, pkg, rel = result
    assert is_ext is True
    assert pkg == "phoenix"
    assert rel == "lib/phoenix/endpoint.ex"

    # Jason dep in deps
    path = "deps/jason/lib/jason.ex"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "jason"
    assert result.package_relative_path == "lib/jason.ex"
    assert result.ecosystem == "HEX"

    # Build cache
    path = "/app/_build/dev/lib/ecto/ebin/ecto.beam"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "ecto"
    assert result.ecosystem == "HEX"


def test_swift_spm_and_sdk_classification():
    # SPM checkout
    path = "/Users/rob/projects/App/.build/checkouts/swift-algorithms/Sources/Algorithms/Chain.swift"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "swift-algorithms"
    assert result.package_relative_path == "Sources/Algorithms/Chain.swift"
    assert result.ecosystem == "SWIFT"

    # SwiftyJSON SPM checkout
    path = "/repo/.build/checkouts/SwiftyJSON/Source/SwiftyJSON/SwiftyJSON.swift"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "SwiftyJSON"
    assert result.package_relative_path == "Source/SwiftyJSON/SwiftyJSON.swift"
    assert result.ecosystem == "SWIFT"

    # Apple framework
    path = "/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk/System/Library/Frameworks/Foundation.framework/Headers/NSString.h"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "Foundation"
    assert result.ecosystem == "SWIFT"

    # Swift stdlib interface
    path = "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk/usr/lib/swift/Swift.swiftinterface"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "apple/swift"
    assert result.ecosystem == "SWIFT"


def test_scala_coursier_and_maven_classification():
    # Coursier cache with Scala binary suffix
    path = "/Users/rob/.cache/coursier/v1/https/repo1.maven.org/maven2/org/typelevel/cats-core_2.13/2.9.0/cats-core_2.13-2.9.0-sources.jar!/cats/Functor.scala"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "org.typelevel:cats-core"
    assert result.version == "2.9.0"
    assert result.package_relative_path == "cats/Functor.scala"
    assert result.ecosystem == "MAVEN"

    # Scala 3 library via Coursier
    path = "/home/user/.cache/coursier/v1/https/repo1.maven.org/maven2/org/scala-lang/scala3-library_3/3.3.1/scala3-library_3-3.3.1-sources.jar!/scala/Option.scala"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "org.scala-lang:scala3-library"
    assert result.version == "3.3.1"
    assert result.package_relative_path == "scala/Option.scala"
    assert result.ecosystem == "MAVEN"

    # Local Maven repository (.m2)
    path = "/home/user/.m2/repository/org/apache/jena/jena-core/4.9.0/jena-core-4.9.0.jar!/org/apache/jena/rdf/model/Model.class"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "org.apache.jena:jena-core"
    assert result.version == "4.9.0"
    assert result.ecosystem == "MAVEN"

    # JDK stdlib
    path = "/java.base/java.lang/System.class"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "java.base:java.lang"
    assert result.ecosystem == "JDK_STDLIB"


def test_php_composer_classification():
    # Vendor path
    path = "/var/www/html/vendor/symfony/console/Command/Command.php"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "symfony/console"
    assert result.package_relative_path == "Command/Command.php"
    assert result.ecosystem == "PACKAGIST"

    # Monolog vendor path
    path = "vendor/monolog/monolog/src/Monolog/Logger.php"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "monolog/monolog"
    assert result.package_relative_path == "src/Monolog/Logger.php"
    assert result.ecosystem == "PACKAGIST"


def test_python_pypi_classification():
    path = "/Users/rob/repos/app/.venv/lib/python3.11/site-packages/pydantic/main.py"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "pydantic"
    assert result.package_relative_path == "main.py"
    assert result.ecosystem == "PYPI"


def test_js_ts_npm_classification():
    # Standard package
    path = "/app/node_modules/lodash/map.js"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "lodash"
    assert result.package_relative_path == "map.js"
    assert result.ecosystem == "NPM"

    # Scoped package
    path = "/app/node_modules/@types/node/fs.d.ts"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "@types/node"
    assert result.package_relative_path == "fs.d.ts"
    assert result.ecosystem == "NPM"


def test_rust_cargo_classification():
    path = "/home/user/.cargo/registry/src/index.crates.io-6f17d22bba15001f/serde-1.0.200/src/lib.rs"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "serde"
    assert result.version == "1.0.200"
    assert result.package_relative_path == "src/lib.rs"
    assert result.ecosystem == "CARGO"


def test_go_classification():
    path = "/home/user/go/pkg/mod/github.com/gin-gonic/gin@v1.9.1/context.go"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "github.com/gin-gonic/gin"
    assert result.version == "1.9.1"
    assert result.package_relative_path == "context.go"
    assert result.ecosystem == "GO"


def test_intra_repository_classification():
    repo_root = "/Users/rob/repos/my-project"

    # File inside repo
    path = "/Users/rob/repos/my-project/src/models/user.py"
    result = PathClassifier.classify(path, repository_root_path=repo_root)
    assert result.is_external is False
    assert result.package_name is None
    assert result.package_relative_path == "src/models/user.py"

    # External dependency inside repo workspace (e.g. deps/ or node_modules/)
    # should STILL be recognized as external!
    path = "/Users/rob/repos/my-project/deps/phoenix/lib/phoenix.ex"
    result = PathClassifier.classify(path, repository_root_path=repo_root)
    assert result.is_external is True
    assert result.package_name == "phoenix"
    assert result.ecosystem == "HEX"

    # Swift checkout inside repo workspace
    path = "/Users/rob/repos/my-project/.build/checkouts/SwiftyJSON/Source/SwiftyJSON/SwiftyJSON.swift"
    result = PathClassifier.classify(path, repository_root_path=repo_root)
    assert result.is_external is True
    assert result.package_name == "SwiftyJSON"
    assert result.ecosystem == "SWIFT"


def test_reexport_via_multilspy_utils():
    # Verify that importing from multilspy_utils behaves identically
    path = "deps/ecto/lib/ecto.ex"
    result = UtilsPathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "ecto"
    assert result.ecosystem == "HEX"


def test_lua_luarocks_classification():
    # Versioned rocks tree
    path = "/Users/rob/.luarocks/lib/luarocks/rocks-5.1/inspect/3.1.3-1/lua/inspect.lua"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "inspect"
    assert result.version == "3.1.3-1"
    assert result.package_relative_path == "lua/inspect.lua"
    assert result.ecosystem == "LUAROCKS"

    # User tree single file
    path = "/Users/rob/.luarocks/share/lua/5.1/inspect.lua"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "inspect"
    assert result.package_relative_path == "inspect.lua"
    assert result.ecosystem == "LUAROCKS"

    # Workspace lua_modules
    path = "/repo/lua_modules/share/lua/5.4/cjson/util.lua"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "cjson"
    assert result.package_relative_path == "util.lua"
    assert result.ecosystem == "LUAROCKS"

    # System share/lua
    path = "/usr/local/share/lua/5.3/pl/stringx.lua"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "pl"
    assert result.package_relative_path == "stringx.lua"
    assert result.ecosystem == "LUAROCKS"


def test_bash_classification():
    # Basher package
    path = "/Users/rob/.basher/cellar/packages/bats-core/bats-core/bin/bats"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "bats-core/bats-core"
    assert result.package_relative_path == "bin/bats"
    assert result.ecosystem == "BASH"

    # Bats test library
    path = "/usr/lib/bats-assert/load.bash"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "bats-assert"
    assert result.package_relative_path == "load.bash"
    assert result.ecosystem == "BASH"

    # Bash completion
    path = "/usr/share/bash-completion/completions/git"
    result = PathClassifier.classify(path)
    assert result.is_external is True
    assert result.package_name == "bash-completion"
    assert result.package_relative_path == "git"
    assert result.ecosystem == "BASH"

