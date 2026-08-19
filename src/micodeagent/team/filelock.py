"""团队文件锁"""

from __future__ import annotations

import asyncio
import os
import random
import time
from contextlib import asynccontextmanager

LOCK_MAX_RETRIES = 10
LOCK_STALE_AFTER = 10.0
LOCK_BACKOFF_MIN = 0.005
LOCK_BACKOFF_MAX = 0.1


@asynccontextmanager
async def acquire(lock_path: str):
    """获取文件锁，10 次重试，stale 锁过期可抢占。"""
    for _ in range(LOCK_MAX_RETRIES):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            break
        except FileExistsError:
            try:
                st = os.stat(lock_path)
                if time.time() - st.st_mtime > LOCK_STALE_AFTER:
                    os.unlink(lock_path)
                    continue
            except OSError:
                pass
            await asyncio.sleep(random.uniform(LOCK_BACKOFF_MIN, LOCK_BACKOFF_MAX))
    else:
        # 最后一次尝试，若 stale 直接删
        try:
            st = os.stat(lock_path)
            if time.time() - st.st_mtime > LOCK_STALE_AFTER:
                os.unlink(lock_path)
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
                os.close(fd)
        except (OSError, FileExistsError):
            pass

    try:
        yield
    finally:
        try:
            os.unlink(lock_path)
        except OSError:
            pass
