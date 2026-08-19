"""命令 UI 控制接口"""

from __future__ import annotations

from typing import Protocol

from micodeagent.permission import Mode


class UI(Protocol):
    """命令实现依赖的界面控制接口。"""

    # 输出
    def println(self, msg: str) -> None: ...

    def error(self, msg: str) -> None: ...

    # 状态查询
    def mode(self) -> Mode: ...

    def usage_in(self) -> int: ...

    def usage_out(self) -> int: ...

    def model_name(self) -> str: ...

    def cwd(self) -> str: ...

    def tool_count(self) -> int: ...

    def memory_files(self) -> list[str]: ...

    def session_path(self) -> str: ...

    def session_id(self) -> str: ...

    def idle(self) -> bool: ...

    # 状态写入
    def set_mode(self, m: Mode) -> None: ...

    def inject_and_send(self, label: str, preset: str) -> None: ...

    def quit(self) -> None: ...

    def force_compact(self) -> None: ...

    def open_resume_menu(self) -> None: ...

    def clear_and_new_session(self) -> None: ...


class NopUI:
    """测试桩：所有写入 no-op，查询返回零值。"""

    def println(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        pass

    def mode(self) -> Mode:
        return Mode.DEFAULT

    def usage_in(self) -> int:
        return 0

    def usage_out(self) -> int:
        return 0

    def model_name(self) -> str:
        return ""

    def cwd(self) -> str:
        return ""

    def tool_count(self) -> int:
        return 0

    def memory_files(self) -> list[str]:
        return []

    def session_path(self) -> str:
        return ""

    def session_id(self) -> str:
        return ""

    def idle(self) -> bool:
        return True

    def set_mode(self, m: Mode) -> None:
        pass

    def inject_and_send(self, label: str, preset: str) -> None:
        pass

    def quit(self) -> None:
        pass

    def force_compact(self) -> None:
        pass

    def open_resume_menu(self) -> None:
        pass

    def clear_and_new_session(self) -> None:
        pass
