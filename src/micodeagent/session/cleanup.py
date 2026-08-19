"""会话过期清理"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from micodeagent.compact.state import parse_session_time

logger = logging.getLogger(__name__)


def clean_expired(sessions_dir: str, max_age: timedelta) -> None:
    """删除超过 max_age 的会话目录。"""
    base = Path(sessions_dir)
    if not base.exists():
        return

    now = datetime.now()
    for sub in base.iterdir():
        if not sub.is_dir():
            continue
        ts = parse_session_time(sub.name)
        if ts is None:
            continue  # 旧格式跳过，避免误删
        if now - ts > max_age:
            try:
                shutil.rmtree(sub)
            except OSError as e:
                logger.warning("清理会话目录失败 %s: %s", sub, e)
