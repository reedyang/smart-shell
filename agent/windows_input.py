#!/usr/bin/env python3
"""
Windows兼容的输入处理模块
使用prompt_toolkit库实现稳定的Tab补全功能和中文输入支持
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import InMemoryHistory
    from prompt_toolkit.formatted_text import FormattedText
    from prompt_toolkit.styles import Style
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
        
        # 如果输入为空或只有空白字符，直接返回所有文件
        if not text or text.strip() == "":
            completions = self._get_directory_contents()
            seen = set()
            for completion in completions:
                if completion not in seen:
                    seen.add(completion)
                    yield Completion(completion, start_position=-len(text))
            return
        
        # 智能检测文件名部分
        file_part, prefix, suffix = self._extract_file_part(text)
        
        # 获取文件补全选项
        if '/' in file_part or '\\' in file_part:
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
                # 构建完整的补全结果
                full_completion = prefix + completion + suffix
                yield Completion(full_completion, start_position=-len(text))
    
    def _extract_file_part(self, text: str) -> tuple:
        """
        智能提取输入文本中的文件名部分
        Args:
            text: 输入文本
        Returns:
            (file_part, prefix, suffix) - 文件名部分、前缀、后缀
        """

        # 获取当前目录的所有文件名
        try:
            current_files = [item.name for item in self.work_directory.iterdir() if not item.name.startswith('.')]
        except Exception:
            current_files = []
        
        # 智能检测：查找可能匹配当前目录文件名的部分
        words = text.split()
        if not words:
            return "", "", ""
        
        # 策略1：检查最后一个词是否匹配文件名开头
        last_word = words[-1]
        for filename in current_files:
            if filename.lower().startswith(last_word.lower()):
                prefix = " ".join(words[:-1])
                if prefix:
                    prefix += " "
                return last_word, prefix, ""
        
        # 策略2：检查最后几个词组合是否匹配文件名
        for i in range(len(words), 0, -1):
            candidate = " ".join(words[i-1:])
            for filename in current_files:
                if filename.lower().startswith(candidate.lower()):
                    prefix = " ".join(words[:i-1])
                    if prefix:
                        prefix += " "
                    return candidate, prefix, ""
        
        # 策略3：检查是否包含完整的文件名（带扩展名）
        for filename in current_files:
            if filename.lower() in text.lower():
                # 找到文件名在文本中的位置
                filename_lower = filename.lower()
                text_lower = text.lower()
                start_pos = text_lower.find(filename_lower)
                if start_pos != -1:
                    prefix = text[:start_pos]
                    suffix = text[start_pos + len(filename):]
                    return filename, prefix, suffix
        
        # 策略4：如果没有找到匹配，使用最后一个词作为候选
        prefix = " ".join(words[:-1])
        if prefix:
            prefix += " "
        return last_word, prefix, ""
    
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
    """Windows输入处理器，使用prompt_toolkit实现Tab补全和中文输入支持"""
    
    def __init__(self, work_directory: Path, initial_history: Optional[List[str]] = None):
        """
        初始化输入处理器
        Args:
            work_directory: 当前工作目录
            initial_history: 预置的历史命令列表（通常来自持久化的HistoryManager）
        """
        self.work_directory = work_directory
        self.history = []
        
        if PROMPT_TOOLKIT_AVAILABLE:
            # 使用prompt_toolkit，并将历史记录注入到会话中
            self.completer = FileCompleter(work_directory)
            self._pt_history = InMemoryHistory()
            if initial_history:
                for entry in initial_history:
                    try:
                        self._pt_history.append_string(entry)
                    except Exception:
                        pass
            self.session = PromptSession(
                completer=self.completer,
                history=self._pt_history,
                enable_system_prompt=True,
                enable_suspend=True,
                complete_in_thread=True
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


def create_windows_input_handler(work_directory: Path, initial_history: Optional[List[str]] = None) -> WindowsInputHandler:
    """创建Windows输入处理器"""
    return WindowsInputHandler(work_directory, initial_history)