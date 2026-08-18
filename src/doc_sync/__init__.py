"""Map changed source files to documentation review targets."""

from doc_sync.config import Config, ConfigError, load_config
from doc_sync.engine import evaluate
from doc_sync.model import Evaluation, Impact, Rule, Status

__all__ = [
    "Config",
    "ConfigError",
    "Evaluation",
    "Impact",
    "Rule",
    "Status",
    "evaluate",
    "load_config",
]
