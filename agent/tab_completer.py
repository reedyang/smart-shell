#!/usr/bin/env python3
"""
Tab键自动补全模块
支持文件名和目录名的自动补全功能
"""

import os
import sys
import glob
from pathlib import Path
from typing import List, Optional, Tuple

# 尝试导入readline，在Windows上可能不可用
try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False


class TabCompleter:
    """Tab键自动补全器"""
    
    def __init__(self, work_directory: Path):
        """
        初始化补全器
        Args:
            work_directory: 当前工作目录
        """
        self.work_directory = work_directory
        self._setup_readline()
    
    def _setup_readline(self):
        """设置readline以支持tab补全"""
        if not READLINE_AVAILABLE:
            print("⚠️ 警告: readline模块不可用，tab补全功能将不可用")
            return
        
        try:
            # 设置补全函数
            readline.set_completer(self._completer)
            # 设置tab键为补全触发键
            readline.parse_and_bind('tab: complete')
            # 设置补全分隔符
            readline.set_completer_delims(' \t\n`!@#$%^&*()=+[{]}\\|;:\'",<>?')
        except Exception as e:
            print(f"⚠️ 警告: 无法设置tab补全功能: {e}")
    
    def _completer(self, text: str, state: int) -> Optional[str]:
        """
        readline补全函数
        Args:
            text: 当前输入的文本
            state: 补全状态（0表示开始，>0表示继续）
        Returns:
            补全的文本，如果state为0则返回None表示结束
        """
        if state == 0:
            # 第一次调用，生成补全列表
            self._completions = self._get_completions(text)
            self._completion_index = 0
            
            # 如果有多个匹配项，显示所有选项
            if len(self._completions) > 1:
                print(f"\n可用的补全选项:")
                for completion in self._completions:
                    print(f"  {completion}")
                print()
        
        if self._completion_index < len(self._completions):
            result = self._completions[self._completion_index]
            self._completion_index += 1
            return result
        
        return None
    
    def _get_completions(self, text: str) -> List[str]:
        """
        获取补全列表
        Args:
            text: 当前输入的文本
        Returns:
            补全选项列表
        """
        if not text:
            # 空文本，返回当前目录的所有文件和文件夹
            return self._get_directory_contents()
        
        # 检查是否包含路径分隔符
        if '/' in text or '\\' in text:
            return self._get_path_completions(text)
        else:
            # 当前目录下的文件/文件夹补全
            return self._get_local_completions(text)
    
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
        """
        获取当前目录下的本地补全
        Args:
            text: 要补全的文本
        Returns:
            匹配的文件/文件夹名列表
        """
        try:
            matches = []
            for item in self.work_directory.iterdir():
                if item.name.lower().startswith(text.lower()):
                    matches.append(item.name)
            
            # 如果有多个匹配项，找到共同前缀
            if len(matches) > 1:
                common_prefix = self._find_common_prefix(matches)
                if common_prefix and len(common_prefix) > len(text):
                    # 返回共同前缀作为唯一补全选项
                    return [common_prefix]
            
            return sorted(matches)
        except Exception:
            return []
    
    def _find_common_prefix(self, strings: List[str]) -> str:
        """
        找到字符串列表的共同前缀
        Args:
            strings: 字符串列表
        Returns:
            共同前缀
        """
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
    
    def _get_path_completions(self, text: str) -> List[str]:
        """
        获取路径补全
        Args:
            text: 包含路径的文本
        Returns:
            匹配的路径列表
        """
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
            
            # 如果有多个匹配项，找到共同前缀
            if len(matches) > 1:
                common_prefix = self._find_common_prefix(matches)
                if common_prefix and len(common_prefix) > len(text):
                    # 返回共同前缀作为唯一补全选项
                    return [common_prefix]
            
            return sorted(matches)
        except Exception:
            return []
    
    def update_work_directory(self, new_directory: Path):
        """更新工作目录"""
        self.work_directory = new_directory
    
    def get_input_with_completion(self, prompt: str) -> str:
        """
        获取带自动补全的用户输入
        Args:
            prompt: 输入提示
        Returns:
            用户输入的文本
        """
        try:
            if READLINE_AVAILABLE:
                return input(prompt)
            else:
                # 如果readline不可用，使用简单的输入
                return input(prompt)
        except (EOFError, KeyboardInterrupt):
            raise


def create_tab_completer(work_directory: Path) -> TabCompleter:
    """
    创建tab补全器
    Args:
        work_directory: 工作目录
    Returns:
        TabCompleter实例
    """
    return TabCompleter(work_directory) 