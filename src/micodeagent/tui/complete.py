"""补全菜单状态机与渲染"""

from __future__ import annotations

from dataclasses import dataclass, field

from micodeagent.command.command import Command
from micodeagent.command.registry import Registry

MAX_ROWS = 8


@dataclass
class CompletionMenu:
    """Tab 补全菜单状态机。"""

    items: list[Command] = field(default_factory=list)
    cursor: int = 0
    offset: int = 0
    active: bool = False

    def update(self, input_text: str, reg: Registry) -> None:
        text = input_text.strip()
        if not text.startswith("/"):
            self.active = False
            return
        self.items = reg.prefix_match(text)
        self.active = True
        if self.cursor >= len(self.items):
            self.cursor = max(0, len(self.items) - 1)
        if self.offset >= len(self.items):
            self.offset = max(0, len(self.items) - MAX_ROWS)

    def move_up(self) -> None:
        if not self.items:
            return
        self.cursor = max(0, self.cursor - 1)
        self._clamp_offset()

    def move_down(self) -> None:
        if not self.items:
            return
        self.cursor = min(len(self.items) - 1, self.cursor + 1)
        self._clamp_offset()

    def selected(self) -> Command | None:
        if self.items and 0 <= self.cursor < len(self.items):
            return self.items[self.cursor]
        return None

    def hide(self) -> None:
        self.active = False
        self.items = []
        self.cursor = 0
        self.offset = 0

    def render(self, width: int) -> str:
        if not self.active:
            return ""
        if not self.items:
            return "（无匹配命令）"

        visible = self.items[self.offset : self.offset + MAX_ROWS]
        name_w = max(len(c.name) for c in visible)
        lines = []
        for i, c in enumerate(visible):
            line = f"/{c.name.ljust(name_w)}  {c.description}"
            if self.offset + i == self.cursor:
                lines.append(f"> {line}")
            else:
                lines.append(f"  {line}")

        if self.offset > 0:
            lines.insert(0, f"↑ {self.offset} more")
        if self.offset + MAX_ROWS < len(self.items):
            lines.append(f"↓ {len(self.items) - self.offset - MAX_ROWS} more")

        return "\n".join(lines)

    def _clamp_offset(self) -> None:
        if self.cursor < self.offset:
            self.offset = self.cursor
        elif self.cursor >= self.offset + MAX_ROWS:
            self.offset = self.cursor - MAX_ROWS + 1
