"""
Configuration parameters for Multilspy.
"""

from enum import Enum
from dataclasses import dataclass, field


def update_config(old, new):
    """
    Update the old config with the new config.
    """
    for key, value in new.items():
        if key in old and isinstance(old[key], dict) and isinstance(value, dict):
            update_config(old[key], value)
        else:
            old[key] = value

class Language(str, Enum):
    """
    Possible languages with Multilspy.
    """

    CSHARP = "csharp"
    PYTHON = "python"
    RUST = "rust"
    JAVA = "java"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"

    def __str__(self) -> str:
        return self.value

@dataclass
class MultilspyConfig:
    """
    Configuration parameters
    """
    code_language: Language
    trace_lsp_communication: bool = False
    initialize_params: dict = field(default_factory=dict)
    runtime_dependencies: dict = field(default_factory=dict)

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