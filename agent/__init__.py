"""
文件管理AI Agent包

这个包包含基于本地Ollama的文件管理AI Agent，具有以下功能：
- 文件和目录管理
- 智能目录切换
- 操作结果反馈
- 自然语言交互
"""

from .file_manager_agent import FileManagerAgent

__version__ = "1.0.0"
__author__ = "AI Assistant"
__all__ = ["FileManagerAgent"] 