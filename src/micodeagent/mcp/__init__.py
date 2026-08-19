"""MCP 客户端子包

实现 MCP 客户端：配置加载、连接管理、工具适配。
"""

from micodeagent.mcp.config import Config, ServerConfig, load_config
from micodeagent.mcp.manager import Manager, new_manager
from micodeagent.mcp.tool import McpTool

__all__ = [
    "Config",
    "ServerConfig",
    "Manager",
    "McpTool",
    "load_config",
    "new_manager",
]
