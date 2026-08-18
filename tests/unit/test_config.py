from __future__ import annotations

import unittest

from doc_sync.config import ConfigError, load_config, validate_repository_config
from tests.support import temporary_repository, temporary_root, write_config


class LoadConfigTest(unittest.TestCase):
    def test_loads_named_rules(self) -> None:
        with temporary_root() as root:
            config = load_config(write_config(root))

            assert config.config_version == 1
            assert config.rules[0].id == "application"

    def test_rejects_unknown_root_key(self) -> None:
        with temporary_root() as root:
            path = write_config(root)
            path.write_text(
                path.read_text().replace(
                    "config_version = 1\n",
                    "config_version = 1\nunknown = true\n",
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "unknown key"):
                load_config(path)

    def test_rejects_unknown_rule_key(self) -> None:
        with temporary_root() as root:
            path = root / "doc-sync.toml"
            path.write_text(
                """config_version = 1
[[rules]]
id = "application"
sources = ["src/"]
document = ["README.md"]
""",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ConfigError, "`document`"):
                load_config(path)

    def test_rejects_duplicate_normalized_paths(self) -> None:
        with temporary_root() as root:
            path = write_config(root)
            content = path.read_text().replace(
                'sources = ["src/"]', 'sources = ["src/", "./src/"]'
            )
            path.write_text(content, encoding="utf-8")

            with self.assertRaisesRegex(ConfigError, "duplicate path"):
                load_config(path)

    def test_repository_validation_checks_paths(self) -> None:
        with temporary_repository() as root:
            config_path = root / "doc-sync.toml"

            config = validate_repository_config(root=root, config_path=config_path)

            assert config.rules[0].sources == ("src/",)
