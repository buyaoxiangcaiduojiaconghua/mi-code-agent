"""记忆类型定义"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NoteType(str, Enum):
    USER_PREFERENCE = "user_preference"
    CORRECTION_FEEDBACK = "correction_feedback"
    PROJECT_KNOWLEDGE = "project_knowledge"
    REFERENCE_MATERIAL = "reference_material"


@dataclass
class Note:
    """一条笔记。"""

    type: NoteType
    title: str
    content: str
    created: str = ""
    updated: str = ""


@dataclass
class UpdateAction:
    """记忆更新操作。"""

    action: str  # create / update / delete
    level: str  # project / user
    type: str = ""
    title: str = ""
    slug: str = ""
    filename: str = ""
    content: str = ""
