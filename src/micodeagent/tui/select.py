"""TUI provider 选择模块

多 provider 配置时，构建方向键选择列表供用户选定活动 provider。
"""

from textual.widgets import OptionList
from textual.widgets.option_list import Option

from micodeagent.config import ProviderConfig


def build_option_list(providers: list[ProviderConfig]) -> OptionList:
    """根据 providers 列表构建 OptionList，每项显示「name (model)」。"""
    option_list = OptionList(id="selector")
    for i, p in enumerate(providers):
        option_list.add_option(Option(f"{p.name} ({p.model})", id=str(i)))
    return option_list
