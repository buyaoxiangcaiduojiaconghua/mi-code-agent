"""slash 命令体系子包"""

from micodeagent.command.command import Command, Kind
from micodeagent.command.dispatch import parse
from micodeagent.command.registry import Registry

__all__ = ["Command", "Kind", "Registry", "parse"]
