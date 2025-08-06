#!/usr/bin/env python3
"""
Windows兼容的输入处理模块
使用prompt_toolkit库实现稳定的Tab补全功能
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import InMemoryHistory
    PROMPT_TOOLKIT_AVAILABLE = True
except ImportError:
    PROMPT_TOOLKIT_AVAILABLE = False


class FileCompleter(Completer):
    """文件补全器"""
    
    def __init__(self, work_directory: Path):
        self.work_directory = work_directory
    
    def get_completions(self, document, complete_event):
        """获取补全选项"""
        text = document.text_before_cursor
        
        # 检查是否包含命令前缀（如 "dir ", "ls ", "cd " 等）
        command_prefix = ""
        file_part = text
        
        # 常见的文件管理命令
        commands = ["dir ", "ls ", "cd ", "copy ", "move ", "del ", "rm ", "mkdir ", "type ", "cat "]
        
        for cmd in commands:
            if text.startswith(cmd):
                command_prefix = cmd
                file_part = text[len(cmd):]
                break
        
        # 获取文件补全选项
        if not file_part:
            # 空文件部分，返回当前目录的所有文件和文件夹
            completions = self._get_directory_contents()
        elif '/' in file_part or '\\' in file_part:
            # 路径补全
            completions = self._get_path_completions(file_part)
        else:
            # 当前目录下的文件/文件夹补全
            completions = self._get_local_completions(file_part)
        
        # 确保每个补全选项只出现一次
        seen = set()
        for completion in completions:
            if completion not in seen:
                seen.add(completion)
                # 如果有命令前缀，需要包含前缀
                if command_prefix:
                    full_completion = command_prefix + completion
                    # 计算需要替换的字符数（包括命令前缀）
                    yield Completion(full_completion, start_position=-len(text))
                else:
                    # 使用负数的start_position来替换已输入的文本
                    yield Completion(completion, start_position=-len(text))
    
    def _get_directory_contents(self) -> List[str]:
        """获取当前目录的内容"""
        try:
            items = []
            for item in self.work_directory.iterdir():
                # 只显示可见文件（不以.开头）
                if not item.name.startswith('.'):
                    items.append(item.name)
            return sorted(items)
        except Exception:
            return []
    
    def _get_local_completions(self, text: str) -> List[str]:
        """获取当前目录下的本地补全"""
        try:
            matches = []
            for item in self.work_directory.iterdir():
                if item.name.lower().startswith(text.lower()):
                    matches.append(item.name)
            
            # 如果只有一个匹配项，直接返回
            if len(matches) == 1:
                return matches
            
            # 如果有多个匹配项，返回所有匹配项供用户选择
            # 不再计算共同前缀，让用户看到所有选项
            return sorted(matches)
        except Exception:
            return []
    
    def _get_path_completions(self, text: str) -> List[str]:
        """获取路径补全"""
        try:
            # 分离目录和文件名部分
            if '/' in text:
                separator = '/'
            else:
                separator = '\\'
            
            parts = text.split(separator)
            if len(parts) == 1:
                return self._get_local_completions(text)
            
            # 构建目录路径
            dir_part = separator.join(parts[:-1])
            file_part = parts[-1]
            
            # 解析目录路径
            if dir_part.startswith('/') or (len(dir_part) > 1 and dir_part[1] == ':'):
                # 绝对路径
                base_dir = Path(dir_part)
            else:
                # 相对路径
                base_dir = self.work_directory / dir_part
            
            if not base_dir.exists() or not base_dir.is_dir():
                return []
            
            # 在指定目录下查找匹配的文件/文件夹
            matches = []
            for item in base_dir.iterdir():
                if item.name.lower().startswith(file_part.lower()):
                    # 构建完整路径
                    full_path = str(base_dir / item.name)
                    # 如果原始文本以分隔符结尾，保持分隔符
                    if text.endswith(separator):
                        matches.append(full_path + separator)
                    else:
                        matches.append(full_path)
            
            # 如果只有一个匹配项，直接返回
            if len(matches) == 1:
                return matches
            
            # 如果有多个匹配项，返回所有匹配项供用户选择
            return sorted(matches)
        except Exception:
            return []
    
    def _find_common_prefix(self, strings: List[str]) -> str:
        """找到字符串列表的共同前缀"""
        if not strings:
            return ""
        
        # 找到最短字符串的长度
        min_len = min(len(s) for s in strings)
        
        # 逐字符比较
        for i in range(min_len):
            char = strings[0][i]
            for s in strings[1:]:
                if s[i] != char:
                    return strings[0][:i]
        
        return strings[0][:min_len]


class WindowsInputHandler:
    """Windows输入处理器，使用prompt_toolkit实现Tab补全"""
    
    def __init__(self, work_directory: Path):
        """
        初始化输入处理器
        Args:
            work_directory: 当前工作目录
        """
        self.work_directory = work_directory
        self.history = []
        
        if PROMPT_TOOLKIT_AVAILABLE:
            # 使用prompt_toolkit
            self.completer = FileCompleter(work_directory)
            self.session = PromptSession(
                completer=self.completer
            )
        else:
            # 回退到标准input
            self.session = None
    
    def get_input_with_completion(self, prompt: str) -> str:
        """
        获取带自动补全的用户输入
        Args:
            prompt: 输入提示
        Returns:
            用户输入的文本
        """
        try:
            if self.session:
                # 使用prompt_toolkit
                user_input = self.session.prompt(prompt).strip()
            else:
                # 回退到标准input
                user_input = input(prompt).strip()
            
            # 保存到历史记录
            if user_input:
                self.history.append(user_input)
            
            return user_input
            
        except KeyboardInterrupt:
            print("^C")
            raise
        except EOFError:
            print()
            raise KeyboardInterrupt
        except Exception as e:
            print(f"\n输入错误: {e}")
            return ""
    
    def update_work_directory(self, new_directory: Path):
        """更新工作目录"""
        self.work_directory = new_directory
        if self.session and hasattr(self, 'completer'):
            self.completer.work_directory = new_directory


def create_windows_input_handler(work_directory: Path) -> WindowsInputHandler:
    """创建Windows输入处理器"""
    return WindowsInputHandler(work_directory) 