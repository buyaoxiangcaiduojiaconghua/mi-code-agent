"""配置模块

读取并校验 `.micodeagent/config.yaml`，解析出 providers 列表。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

# 支持的协议类型
SUPPORTED_PROTOCOLS = {"anthropic", "openai"}

# 协议默认上下文窗口（token）
DEFAULT_ANTHROPIC_CONTEXT_WINDOW = 200000
DEFAULT_OPENAI_CONTEXT_WINDOW = 128000


class ConfigError(Exception):
    """配置加载或校验错误"""

    pass


@dataclass
class ProviderConfig:
    """单个 LLM 供应商配置"""

    name: str  # 供应商标识名（状态栏左侧显示）
    protocol: Literal["anthropic", "openai"]  # 协议类型
    api_key: str  # 认证密钥
    model: str  # 模型名（状态栏右侧显示）
    base_url: str | None = None  # 自定义端点地址；None 则用 SDK 默认
    thinking: bool = False  # 是否启用扩展思考（仅 anthropic 生效）
    context_window: int = 0  # 上下文窗口 token 数；0 表示走协议默认


def effective_context_window(p: ProviderConfig) -> int:
    """返回 provider 的有效上下文窗口。"""
    if p.context_window > 0:
        return p.context_window
    if p.protocol == "anthropic":
        return DEFAULT_ANTHROPIC_CONTEXT_WINDOW
    if p.protocol == "openai":
        return DEFAULT_OPENAI_CONTEXT_WINDOW
    return DEFAULT_ANTHROPIC_CONTEXT_WINDOW


@dataclass
class FeaturesConfig:
    """功能开关。"""

    coordinator_mode: bool = False
    fork_teammate: bool = False


@dataclass
class Config:
    """整体配置"""

    providers: list[ProviderConfig] = field(default_factory=list)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)


def load(path: str) -> Config:
    """读取并校验配置文件，返回 Config。

    任一 provider 缺少必要字段或协议非法时，抛出 ConfigError 并指明位置。
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"配置文件格式错误，无法解析 YAML: {e}")

    if data is None:
        raise ConfigError("配置文件为空")

    if "providers" not in data:
        raise ConfigError("配置文件缺少 'providers' 字段")

    providers = data["providers"]
    if not isinstance(providers, list):
        raise ConfigError("'providers' 字段必须是列表")

    if not providers:
        raise ConfigError("'providers' 列表不能为空")

    configs: list[ProviderConfig] = []
    for i, item in enumerate(providers):
        if not isinstance(item, dict):
            raise ConfigError(f"providers[{i}] 不是有效的字典格式")

        # 逐项校验必要字段
        for field_name in ("name", "protocol", "api_key", "model"):
            value = item.get(field_name)
            if not value or not str(value).strip():
                raise ConfigError(f"providers[{i}].{field_name} 不能为空")

        protocol = item["protocol"]
        if protocol not in SUPPORTED_PROTOCOLS:
            raise ConfigError(
                f"providers[{i}].protocol 不支持: {protocol}，"
                f"支持: {', '.join(sorted(SUPPORTED_PROTOCOLS))}"
            )

        configs.append(
            ProviderConfig(
                name=str(item["name"]),
                protocol=protocol,
                api_key=str(item["api_key"]),
                model=str(item["model"]),
                base_url=item.get("base_url") or None,
                thinking=bool(item.get("thinking", False)),
                context_window=int(item.get("context_window", 0) or 0),
            )
        )

    # 解析 features 段
    features = FeaturesConfig()
    raw_features = data.get("features")
    if isinstance(raw_features, dict):
        features = FeaturesConfig(
            coordinator_mode=bool(raw_features.get("coordinator_mode", False)),
            fork_teammate=bool(raw_features.get("fork_teammate", False)),
        )

    return Config(providers=configs, features=features)
