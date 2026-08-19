"""config 模块单测"""

import pytest

from micodeagent.config import ConfigError, ProviderConfig, effective_context_window, load


def _write_config(tmp_path, text: str) -> str:
    """写入临时配置文件，返回路径"""
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


class TestLoad:
    def test_load_single_provider(self, tmp_path):
        cfg = load(
            _write_config(
                tmp_path,
                """
providers:
  - name: "claude"
    protocol: "anthropic"
    model: "claude-3-5-sonnet"
    api_key: "sk-xxx"
""",
            )
        )
        assert len(cfg.providers) == 1
        p = cfg.providers[0]
        assert p.name == "claude"
        assert p.protocol == "anthropic"
        assert p.model == "claude-3-5-sonnet"
        assert p.base_url is None
        assert p.thinking is False

    def test_load_multiple_providers(self, tmp_path):
        cfg = load(
            _write_config(
                tmp_path,
                """
providers:
  - name: "claude"
    protocol: "anthropic"
    model: "claude"
    api_key: "a"
  - name: "gpt"
    protocol: "openai"
    model: "gpt-4o"
    api_key: "b"
""",
            )
        )
        assert len(cfg.providers) == 2
        assert cfg.providers[1].protocol == "openai"

    def test_optional_fields(self, tmp_path):
        cfg = load(
            _write_config(
                tmp_path,
                """
providers:
  - name: "claude"
    protocol: "anthropic"
    model: "claude"
    api_key: "a"
    base_url: "https://example.com"
    thinking: true
""",
            )
        )
        p = cfg.providers[0]
        assert p.base_url == "https://example.com"
        assert p.thinking is True

    def test_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="不存在"):
            load(str(tmp_path / "nope.yaml"))

    def test_missing_providers(self, tmp_path):
        with pytest.raises(ConfigError, match="providers"):
            load(_write_config(tmp_path, "other: 1\n"))

    def test_empty_providers(self, tmp_path):
        with pytest.raises(ConfigError, match="不能为空"):
            load(_write_config(tmp_path, "providers: []\n"))

    def test_missing_required_field(self, tmp_path):
        with pytest.raises(ConfigError, match="api_key"):
            load(
                _write_config(
                    tmp_path,
                    """
providers:
  - name: "claude"
    protocol: "anthropic"
    model: "claude"
""",
                )
            )

    def test_invalid_protocol(self, tmp_path):
        with pytest.raises(ConfigError, match="protocol"):
            load(
                _write_config(
                    tmp_path,
                    """
providers:
  - name: "x"
    protocol: "gemini"
    model: "m"
    api_key: "k"
""",
                )
            )

    def test_bad_yaml(self, tmp_path):
        with pytest.raises(ConfigError):
            load(_write_config(tmp_path, "providers: [unclosed\n"))


class TestContextWindow:
    def test_effective_unconfigured_anthropic(self):
        p = ProviderConfig(name="x", protocol="anthropic", api_key="k", model="m")
        assert effective_context_window(p) == 200000

    def test_effective_zero_openai(self):
        p = ProviderConfig(name="x", protocol="openai", api_key="k", model="m", context_window=0)
        assert effective_context_window(p) == 128000

    def test_effective_positive(self):
        p = ProviderConfig(
            name="x", protocol="anthropic", api_key="k", model="m", context_window=80000
        )
        assert effective_context_window(p) == 80000

    def test_load_context_window(self, tmp_path):
        cfg = load(
            _write_config(
                tmp_path,
                """
providers:
  - name: "claude"
    protocol: "anthropic"
    model: "claude"
    api_key: "a"
    context_window: 100000
""",
            )
        )
        assert cfg.providers[0].context_window == 100000
