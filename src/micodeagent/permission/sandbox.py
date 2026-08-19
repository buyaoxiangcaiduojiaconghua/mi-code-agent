"""L2: 路径沙箱

限制文件操作在项目根目录内，先解析符号链接再前缀判断。
"""

import os
from pathlib import Path


def resolve_root(root: str) -> str:
    """解析并验证项目根目录"""
    return str(Path(root).expanduser().resolve(strict=True))


def eval_symlinks_or_ancestor(abs_path: str) -> str:
    """解析符号链接，目标不存在时回退到最近已存在祖先"""
    p = Path(abs_path)
    try:
        return str(p.resolve(strict=True))
    except FileNotFoundError:
        parts = []
        current = p
        while current != current.parent:
            if current.exists():
                try:
                    resolved_parent = str(current.resolve(strict=True))
                    if parts:
                        return os.path.join(resolved_parent, *reversed(parts))
                    return resolved_parent
                except FileNotFoundError:
                    pass
            parts.append(current.name)
            current = current.parent
        return str(Path(abs_path).resolve())


def sandbox_ok(root: str, path: str) -> bool:
    """检查路径是否在项目根内"""
    if not path:
        return True
    p = Path(path)
    if not p.is_absolute():
        p = Path(root) / p
    abs_path = str(p)
    resolved = eval_symlinks_or_ancestor(abs_path)
    root_resolved = root.rstrip(os.sep) + os.sep
    return resolved == root or resolved.startswith(root_resolved)
