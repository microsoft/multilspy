"""
Configuration parameters for Multilspy.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional

class Language(str, Enum):
    """
    Possible languages with Multilspy.
    """

    CSHARP = "csharp"
    PYTHON = "python"
    RUST = "rust"
    JAVA = "java"
    KOTLIN = "kotlin"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    RUBY = "ruby"
    DART = "dart"
    CPP = "cpp"

    def __str__(self) -> str:
        return self.value

@dataclass
class MultilspyConfig:
    """
    Configuration parameters
    """
    code_language: Language
    trace_lsp_communication: bool = False
    start_independent_lsp_process: bool = True

    # Optional path to a custom LSP binary/executable to use instead of the default.
    # 
    # For most language servers, this simply replaces the executable path. However, there
    # are some exceptions:
    # 
    # - Java (EclipseJDTLS): Replaces only the launcher jar path. All Java/JVM arguments,
    #   runtime setup, and configuration are preserved. The custom binary should be a path
    #   to a JDTLS launcher jar file.
    # 
    # - Kotlin: Replaces only the Kotlin LSP executable path. All Java setup (JAVA_HOME, etc.)
    #   is still performed and preserved, as it's required for Kotlin to function.
    # 
    # - C# (OmniSharp): Replaces only the OmniSharp executable path. All setup including
    #   RazorOmnisharp DLL download is still performed, and the DLL path is still available
    #   if needed by the custom binary.
    # 
    # For all other language servers (Rust, Python, Go, Ruby, C++), the custom binary
    # path directly replaces the default executable with no other modifications.
    custom_lsp_binary: Optional[str] = None

    @classmethod
    def from_dict(cls, env: dict):
        """
        Create a MultilspyConfig instance from a dictionary
        """
        import inspect
        return cls(**{
            k: v for k, v in env.items() 
            if k in inspect.signature(cls).parameters
        })
