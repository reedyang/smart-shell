import ollama
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
import shutil
from datetime import datetime

# 导入tab补全模块
import os
import platform

# 根据操作系统选择合适的输入处理器
if platform.system() == "Windows":
    try:
        from .windows_input import create_windows_input_handler
        TAB_COMPLETION_AVAILABLE = True
        INPUT_HANDLER_TYPE = "windows"
    except ImportError:
        TAB_COMPLETION_AVAILABLE = False
        INPUT_HANDLER_TYPE = "none"
else:
    try:
        from .tab_completer import create_tab_completer
        TAB_COMPLETION_AVAILABLE = True
        INPUT_HANDLER_TYPE = "readline"
    except ImportError:
        TAB_COMPLETION_AVAILABLE = False
        INPUT_HANDLER_TYPE = "none"

class FileManagerAgent:
    def __init__(self, model_name: str = "gemma3:4b", work_directory: Optional[str] = None, provider: str = "ollama", openai_conf: Optional[dict] = None, openwebui_conf: Optional[dict] = None, params: Optional[dict] = None):
        """
        初始化文件管理AI Agent
        Args:
            model_name: 模型名称
            work_directory: 工作目录
            provider: 模型服务提供方
            openai_conf: openai参数
            openwebui_conf: openwebui参数
            params: 通用参数
        """
        self.model_name = model_name
        self.work_directory = Path(work_directory) if work_directory else Path.cwd()
        self.conversation_history = []
        self.operation_results = []
        self.provider = provider
        self.openai_conf = openai_conf
        self.openwebui_conf = openwebui_conf
        self.params = params
        # 兼容params统一配置
        if self.provider == 'openai' and self.openai_conf is None and params is not None:
            self.openai_conf = params
        if self.provider == 'openwebui' and self.openwebui_conf is None and params is not None:
            self.openwebui_conf = params
        self._validate_model()
        
        # 系统提示词
        prompt_path = os.path.join(os.path.dirname(__file__), 'system_prompt.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()
        
        # 初始化输入处理器
        self.input_handler = None
        if TAB_COMPLETION_AVAILABLE:
            try:
                if INPUT_HANDLER_TYPE == "windows":
                    self.input_handler = create_windows_input_handler(self.work_directory)
                    print("✅ Windows Tab键自动补全功能已启用")
                elif INPUT_HANDLER_TYPE == "readline":
                    self.input_handler = create_tab_completer(self.work_directory)
                    print("✅ Unix/Linux Tab键自动补全功能已启用")
                else:
                    print("⚠️ 未知的输入处理器类型")
            except Exception as e:
                print(f"⚠️ 输入处理器初始化失败: {e}")
        else:
            print("⚠️ Tab补全功能不可用")
    
    def _validate_model(self):
        """验证模型是否可用（仅ollama模式）"""
        if self.provider != "ollama":
            return
        try:
            import ollama
            models = ollama.list()
            available_models = []
            for model in models.get('models', []):
                if hasattr(model, 'model'):
                    available_models.append(model.model)
                elif isinstance(model, dict):
                    available_models.append(model.get('name', model.get('model', 'unknown')))
                else:
                    available_models.append(str(model))
            if self.model_name not in available_models:
                print(f"⚠️ 警告: 模型 '{self.model_name}' 不在可用模型列表中")
                print(f"📋 可用模型: {available_models}")
                if available_models:
                    print(f"💡 建议使用: {available_models[0]}")
        except Exception as e:
            print(f"⚠️ 无法验证模型: {e}")

    def call_ai(self, user_input: str, context: str = "", stream: bool = False):
        """调用大模型API获取AI回复，支持流式输出。stream=True时返回生成器"""
        try:
            # 确保os未被局部变量遮蔽
            import os
            os_info = os.uname() if hasattr(os, 'uname') else os.name
            messages = [{"role": "system", "content": f"{self.system_prompt}\n当前操作系统信息：{os_info}"}]
            for msg in self.conversation_history[-5:]:
                messages.append(msg)
            current_input = f"当前工作目录: {self.work_directory}\n"
            if self.operation_results:
                current_input += f"最近的操作结果: {self.operation_results[-1]}\n"
            if context:
                current_input += f"操作上下文: {context}\n"
            current_input += f"用户输入: {user_input}"
            messages.append({"role": "user", "content": current_input})

            if self.provider == "openai" and self.openai_conf:
                import requests
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                api_key = self.openai_conf.get("api_key")
                base_url = self.openai_conf.get("base_url", "https://api.openai.com/v1")
                model = self.model_name
                url = base_url.rstrip("/") + "/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": stream
                }
                resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=120, stream=stream)
                resp.raise_for_status()
                if stream:
                    def gen():
                        buffer = ""
                        for line in resp.iter_lines():
                            if not line or not line.startswith(b"data: "):
                                continue
                            data = line[6:]
                            if data.strip() == b"[DONE]":
                                break
                            try:
                                data_str = data.decode('utf-8', errors='replace')
                                delta = json.loads(data_str)["choices"][0]["delta"].get("content", "")
                                if delta:
                                    buffer += delta
                                    yield delta
                            except Exception:
                                continue
                        self.conversation_history.append({"role": "user", "content": user_input})
                        self.conversation_history.append({"role": "assistant", "content": buffer})
                    return gen()
                else:
                    data = resp.json()
                    ai_response = data["choices"][0]["message"]["content"]
                    self.conversation_history.append({"role": "user", "content": user_input})
                    self.conversation_history.append({"role": "assistant", "content": ai_response})
                    return ai_response
            elif self.provider == "openwebui" and self.openwebui_conf:
                import requests
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                api_key = self.openwebui_conf.get("api_key")
                base_url = self.openwebui_conf.get("base_url", "http://localhost:8080/v1")
                model = self.model_name
                url = base_url.rstrip("/") + "/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": model,
                    "messages": messages,
                    "stream": stream
                }
                resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=120, stream=stream)
                resp.raise_for_status()
                if stream:
                    def gen():
                        buffer = ""
                        for line in resp.iter_lines(decode_unicode=True):
                            if not line or not line.startswith("data: "):
                                continue
                            data = line[6:]
                            if data.strip() == "[DONE]":
                                break
                            try:
                                delta = json.loads(data)["choices"][0]["delta"].get("content", "")
                                if delta:
                                    buffer += delta
                                    yield delta
                            except Exception:
                                continue
                        self.conversation_history.append({"role": "user", "content": user_input})
                        self.conversation_history.append({"role": "assistant", "content": buffer})
                    return gen()
                else:
                    data = resp.json()
                    ai_response = data["choices"][0]["message"]["content"]
                    self.conversation_history.append({"role": "user", "content": user_input})
                    self.conversation_history.append({"role": "assistant", "content": ai_response})
                    return ai_response
            else:
                import ollama
                if stream:
                    response = ollama.chat(
                        model=self.model_name,
                        messages=messages,
                        stream=True
                    )
                    def gen():
                        buffer = ""
                        for chunk in response:
                            delta = chunk.get("message", {}).get("content", "")
                            if delta:
                                buffer += delta
                                yield delta
                        self.conversation_history.append({"role": "user", "content": user_input})
                        self.conversation_history.append({"role": "assistant", "content": buffer})
                    return gen()
                else:
                    response = ollama.chat(
                        model=self.model_name,
                        messages=messages,
                        stream=False
                    )
                    ai_response = response['message']['content']
                    self.conversation_history.append({"role": "user", "content": user_input})
                    self.conversation_history.append({"role": "assistant", "content": ai_response})
                    return ai_response
        except Exception as e:
            error_msg = f"调用大模型API时出错: {str(e)} (provider: {self.provider}, model: {self.model_name})"
            return error_msg

    def extract_json_command(self, text: str) -> Optional[Dict]:
        """从AI回复中提取JSON命令"""
        try:
            # 先尝试查找markdown代码块中的JSON
            json_code_pattern = r'```(?:json)?\s*(\{.*?"action".*?\})\s*```'
            code_matches = re.findall(json_code_pattern, text, re.DOTALL)
            
            if code_matches:
                # 尝试解析找到的JSON
                for match in code_matches:
                    try:
                        parsed = json.loads(match.strip())
                        if "action" in parsed:
                            return parsed
                    except:
                        continue
            
            # 如果没找到代码块，尝试直接查找JSON
            # 使用更复杂的方法来匹配嵌套的JSON
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if line.startswith('{') and '"action"' in line:
                    try:
                        # 尝试解析这一行作为JSON
                        parsed = json.loads(line)
                        if "action" in parsed:
                            return parsed
                    except:
                        continue
            
            return None
        except Exception as e:
            print(f"⚠️ JSON提取错误: {e}")
            return None

    def action_list_directory(self, path: Optional[str] = None, file_filter: Optional[str] = None) -> Dict[str, Any]:
        """列出目录内容"""
        target_path = Path(path) if path else self.work_directory
        
        if not target_path.exists():
            return {"success": False, "error": f"目录 '{target_path}' 不存在"}
        
        if not target_path.is_dir():
            return {"success": False, "error": f"'{target_path}' 不是一个目录"}
        
        items = []
        try:
            for item in target_path.iterdir():
                # 应用文件过滤器
                if file_filter:
                    if item.is_file():
                        # 检查文件扩展名或名称是否匹配过滤器
                        if not (file_filter.lower() in item.name.lower() or 
                               item.suffix.lower() == f".{file_filter.lower()}" or
                               item.name.lower().endswith(f".{file_filter.lower()}")):
                            continue
                    else:
                        # 对于目录，只检查名称是否包含过滤器
                        if file_filter.lower() not in item.name.lower():
                            continue
                
                item_info = {
                    "name": item.name,
                    "type": "directory" if item.is_dir() else "file",
                    "size": item.stat().st_size if item.is_file() else 0,
                    "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                }
                items.append(item_info)
        except PermissionError:
            return {"success": False, "error": "权限不足，无法访问目录"}
        
        sorted_items = sorted(items, key=lambda x: (x["type"], x["name"]))
        filter_info = f" (过滤: {file_filter})" if file_filter else ""
        return {
            "success": True,
            "path": str(target_path),
            "items": sorted_items,
            "total_files": len([i for i in sorted_items if i["type"] == "file"]),
            "total_dirs": len([i for i in sorted_items if i["type"] == "directory"]),
            "filter": file_filter,
            "filter_info": filter_info
        }

    def action_intelligent_filter(self, file_list_result: Dict[str, Any], filter_condition: str) -> Dict[str, Any]:
        """使用AI智能过滤文件列表"""
        try:
            # 构建文件信息文本
            files_info = []
            for item in file_list_result.get("items", []):
                info = f"- {item['name']} | {item['type']} | {item['size']} bytes | 修改时间: {item['modified']}"
                files_info.append(info)
            
            files_text = "\n".join(files_info)
            
            # 构建AI提示 - 明确这是数据分析任务，不是命令生成
            ai_prompt = f"""
你现在是一个数据分析助手，不是文件管理命令生成器。

任务：从以下文件列表中筛选出符合条件的文件。

筛选条件：{filter_condition}

文件数据：
{files_text}

分析要求：
1. 仔细检查每个文件的信息（名称、大小、时间等）
2. 判断哪些文件符合筛选条件
3. 只返回符合条件的文件名，每行一个
4. 不要返回JSON、不要生成命令、不要添加解释

示例（假设要筛选大于500字节的文件）：
large_document.txt
big_image.jpg

现在开始分析："""
            
            # 调用AI进行筛选
            ai_response = self.call_ai(ai_prompt)
            
            # 解析AI回复，提取符合条件的文件名
            if "无符合条件的文件" in ai_response:
                filtered_items = []
            else:
                lines = ai_response.strip().split('\n')
                valid_names = []
                original_items = {item['name']: item for item in file_list_result.get("items", [])}
                
                for line in lines:
                    line = line.strip()
                    # 跳过空行、说明文字、JSON格式等
                    if (line and 
                        not line.startswith('请') and 
                        not line.startswith('根据') and 
                        not line.startswith('文件') and
                        not line.startswith('筛选') and
                        not line.startswith('可选') and
                        not line.startswith('示例') and
                        not line.startswith('{') and
                        not line.startswith('```') and
                        line != ''):
                        
                        # 移除可能的序号、标记符号等
                        clean_name = line.replace('- ', '').replace('* ', '').replace('+ ', '').strip()
                        
                        # 检查是否是有效的文件名（存在于原始列表中）
                        if clean_name in original_items:
                            valid_names.append(clean_name)
                
                # 根据AI返回的文件名筛选原始列表
                filtered_items = []
                for name in valid_names:
                    filtered_items.append(original_items[name])
            
            # 构建结果，保持与list_directory相同的格式
            return {
                "success": True,
                "path": file_list_result.get("path", ""),
                "items": filtered_items,
                "total_files": len([i for i in filtered_items if i["type"] == "file"]),
                "total_dirs": len([i for i in filtered_items if i["type"] == "directory"]),
                "filter": filter_condition,
                "filter_info": f" (智能过滤: {filter_condition})"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"智能过滤失败: {str(e)}",
                "original_result": file_list_result
            }

    def action_change_directory(self, path: str) -> Dict[str, Any]:
        """切换工作目录"""
        try:
            if path == "..":
                new_path = self.work_directory.parent
            elif path == ".":
                new_path = self.work_directory
            elif path.startswith("/") or path.startswith("\\") or (len(path) > 1 and path[1] == ":"):
                # 绝对路径
                new_path = Path(path)
            else:
                # 相对路径
                new_path = self.work_directory / path
            
            # 解析路径
            new_path = new_path.resolve()
            
            if not new_path.exists():
                return {"success": False, "error": f"目录 '{path}' 不存在"}
            
            if not new_path.is_dir():
                return {"success": False, "error": f"'{path}' 不是一个目录"}
            
            old_dir = self.work_directory
            self.work_directory = new_path
            
            # 更新输入处理器的工作目录
            if self.input_handler:
                self.input_handler.update_work_directory(new_path)
            
            return {
                "success": True,
                "old_directory": str(old_dir),
                "new_directory": str(new_path),
                "message": f"已切换到目录: {new_path}"
            }
            
        except Exception as e:
            return {"success": False, "error": f"切换目录失败: {str(e)}"}

    def action_rename_file(self, old_name: str, new_name: str) -> Dict[str, Any]:
        """重命名文件或文件夹"""
        try:
            old_path = self.work_directory / old_name
            new_path = self.work_directory / new_name
            
            if not old_path.exists():
                return {"success": False, "error": f"文件 '{old_name}' 不存在"}
            
            if new_path.exists():
                return {"success": False, "error": f"目标文件 '{new_name}' 已存在"}
            
            old_path.rename(new_path)
            return {
                "success": True,
                "old_name": old_name,
                "new_name": new_name,
                "message": f"成功将 '{old_name}' 重命名为 '{new_name}'"
            }
            
        except Exception as e:
            return {"success": False, "error": f"重命名失败: {str(e)}"}

    def action_move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """移动文件或文件夹，支持通配符批量移动"""
        import glob
        try:
            # 判断是否为通配符批量移动
            if '*' in source or '?' in source:
                pattern = str((self.work_directory / source).resolve())
                matched_files = [Path(p) for p in glob.glob(pattern) if Path(p).is_file()]
                if not matched_files:
                    return {"success": False, "error": f"未找到匹配的文件: {source}"}
                if destination.startswith("/") or destination.startswith("\\") or (len(destination) > 1 and destination[1] == ":"):
                    dest_path = Path(destination)
                else:
                    dest_path = self.work_directory / destination
                dest_path.mkdir(parents=True, exist_ok=True)
                moved = []
                for file_path in matched_files:
                    target = dest_path / file_path.name
                    shutil.move(str(file_path), str(target))
                    moved.append(file_path.name)
                return {
                    "success": True,
                    "source": source,
                    "destination": str(dest_path),
                    "moved_files": moved,
                    "message": f"成功批量移动 {len(moved)} 个文件到 '{dest_path}'"
                }
            else:
                source_path = self.work_directory / source
                if destination.startswith("/") or destination.startswith("\\") or (len(destination) > 1 and destination[1] == ":"):
                    dest_path = Path(destination)
                else:
                    dest_path = self.work_directory / destination
                if not source_path.exists():
                    return {"success": False, "error": f"源文件 '{source}' 不存在"}
                shutil.move(str(source_path), str(dest_path))
                return {
                    "success": True,
                    "source": source,
                    "destination": str(dest_path),
                    "message": f"成功将 '{source}' 移动到 '{dest_path}'"
                }
        except Exception as e:
            return {"success": False, "error": f"移动失败: {str(e)}"}

    def action_delete_file(self, file_name: str, confirmed: bool = False) -> Dict[str, Any]:
        """删除文件或文件夹，支持通配符批量删除"""
        import glob
        # 判断是否为通配符批量删除
        if '*' in file_name or '?' in file_name:
            pattern = str((self.work_directory / file_name).resolve())
            matched_files = [Path(p) for p in glob.glob(pattern)]
            if not matched_files:
                return {"success": False, "error": f"未找到匹配的文件: {file_name}"}
            if not confirmed:
                confirmation = input(f"您确定要批量删除 {len(matched_files)} 个文件/目录吗？(y/n): ")
                if confirmation.lower() != 'y':
                    return {
                        "success": False,
                        "warning": f"用户拒绝批量删除 '{file_name}', 请跳过这些文件/目录",
                        "confirmation_needed": False
                    }
            results = []
            for file_path in matched_files:
                try:
                    if not file_path.exists():
                        results.append({"file": str(file_path), "success": False, "error": "不存在"})
                        continue
                    if file_path.is_dir():
                        shutil.rmtree(file_path)
                        results.append({"file": str(file_path), "success": True, "type": "directory", "message": f"成功删除目录 '{file_path.name}'"})
                    else:
                        file_path.unlink()
                        results.append({"file": str(file_path), "success": True, "type": "file", "message": f"成功删除文件 '{file_path.name}'"})
                except Exception as e:
                    results.append({"file": str(file_path), "success": False, "error": f"删除失败: {str(e)}"})
            all_success = all(r.get("success", False) for r in results)
            return {"success": all_success, "deleted": results, "count": len(results)}

        # 单文件/目录删除
        if not confirmed:
            confirmation = input(f"您确定要删除 '{file_name}' 吗？(y/n): ")
            if confirmation.lower() != 'y':
                return {
                    "success": False,
                    "warning": f"用户拒绝删除 '{file_name}'，请跳过这个文件/目录",
                    "confirmation_needed": False
                }
        try:
            file_path = self.work_directory / file_name
            if not file_path.exists():
                return {"success": False, "error": f"文件 '{file_name}' 不存在"}
            if file_path.is_dir():
                shutil.rmtree(file_path)
                return {
                    "success": True,
                    "file_name": file_name,
                    "type": "directory",
                    "message": f"成功删除目录 '{file_name}'"
                }
            else:
                file_path.unlink()
                return {
                    "success": True,
                    "file_name": file_name,
                    "type": "file",
                    "message": f"成功删除文件 '{file_name}'"
                }
        except Exception as e:
            return {"success": False, "error": f"删除失败: {str(e)}"}

    def action_create_directory(self, dir_name: str) -> Dict[str, Any]:
        """创建新文件夹"""
        try:
            dir_path = self.work_directory / dir_name
            
            if dir_path.exists():
                return {"success": False, "error": f"文件夹 '{dir_name}' 已存在"}
            
            dir_path.mkdir(parents=True)
            return {
                "success": True,
                "dir_name": dir_name,
                "full_path": str(dir_path),
                "message": f"成功创建文件夹 '{dir_name}'"
            }
            
        except Exception as e:
            return {"success": False, "error": f"创建文件夹失败: {str(e)}"}

    def action_get_file_info(self, file_name: str) -> Dict[str, Any]:
        """获取文件信息"""
        try:
            file_path = self.work_directory / file_name
            
            if not file_path.exists():
                return {"success": False, "error": f"文件 '{file_name}' 不存在"}
            
            stat = file_path.stat()
            return {
                "success": True,
                "name": file_name,
                "type": "directory" if file_path.is_dir() else "file",
                "size": stat.st_size,
                "created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "permissions": oct(stat.st_mode)[-3:],
                "full_path": str(file_path)
            }
            
        except Exception as e:
            return {"success": False, "error": f"获取文件信息失败: {str(e)}"}

    def action_ffmpeg(self, source: str, target: str, options: Optional[str] = None) -> Dict[str, Any]:
        """调用ffmpeg处理媒体文件"""
        import subprocess
        if not source or not target:
            print("⚠️ 缺少 source 或 target 参数")
            return {"success": False, "error": "缺少 source 或 target 参数"}
        
        # 检查源文件是否存在
        source_path = self.work_directory / source
        if not source_path.exists():
            print(f"⚠️ 源文件 '{source}' 不存在")
            return {"success": False, "error": f"源文件 '{source}' 不存在"}

        ffmpeg_cmd = ["ffmpeg", "-y", "-i", source]
        if options:
            ffmpeg_cmd += options.split()
        ffmpeg_cmd.append(target)
        print(f"🔄 正在执行 ffmpeg 命令: {' '.join(ffmpeg_cmd)}")
        try:
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            if result.returncode == 0:
                return {"success": True, "message": "媒体文件处理成功"}
            else:
                return {"success": False, "error": f"ffmpeg 执行失败: {result.stderr}"}
        except FileNotFoundError:
            return {"success": False, "error": "未检测到 ffmpeg，请确保已安装并配置好 PATH 环境变量"}
        except Exception as e:
            return {"success": False, "error": f"ffmpeg 执行异常: {str(e)}"}
    
    def action_summarize_file(self, file_path: str, max_lines: int = 50) -> dict:
        """总结文本文件内容"""
        try:
            abs_path = Path(file_path)
            if not abs_path.is_absolute():
                abs_path = self.work_directory / file_path
            if not abs_path.exists():
                return {"success": False, "error": f"文件 '{file_path}' 不存在"}
            if not abs_path.is_file():
                return {"success": False, "error": f"'{file_path}' 不是一个文件"}
            stat = abs_path.stat()
            text_exts = ['.txt', '.md', '.json', '.py', '.csv', '.log', '.ini', '.yaml', '.yml']
            if abs_path.suffix.lower() not in text_exts and stat.st_size > 1024*1024:
                return {"success": False, "error": "仅支持文本文件或小于1MB的文件总结"}
            try:
                with open(abs_path, 'r', encoding='utf-8', errors='replace') as f:
                    lines = []
                    for i, line in enumerate(f):
                        if i >= max_lines:
                            lines.append('... (内容过长已截断)')
                            break
                        lines.append(line.rstrip('\n'))
                    content = '\n'.join(lines)
            except Exception as e:
                return {"success": False, "error": f"无法读取文件内容: {str(e)}"}
            prompt = f"请用中文简要总结以下文件内容（200字以内）：\n{content}"
            summary = self.call_ai(prompt)
            return {"success": True, "summary": summary, "file": str(abs_path)}
        except Exception as e:
            return {"success": False, "error": f"总结文件失败: {str(e)}"}
    
    def action_shell_command(self, command: str) -> dict:
        """执行任意系统命令，返回输出和错误信息"""
        # 请求用户确实是否执行这条命令
        if not command.strip():
            return {"success": False, "error": "命令不能为空"}
        confirm = input(f"⚠️ 确认执行系统命令: {command} ? (y/n): ")
        if confirm.lower() != "y":
            return {"success": False, "error": "用户取消了操作"}

        import subprocess
        try:
            # Windows下建议用shell=True，Linux下shell=False更安全
            result = subprocess.run(command, shell=True, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(self.work_directory))
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
                "returncode": result.returncode
            }
        except Exception as e:
            return {"success": False, "error": f"系统命令执行异常: {str(e)}"}
        
    def action_create_script(self, filename: str, content: str) -> dict:
        """创建脚本文件，支持任意内容和扩展名"""
        # 请求用户确认是否创建脚本文件
        print("请求创建脚本文件: {filename}")
        print(f"内容:\n{content}")
        confirm = input(f"⚠️ 确认创建脚本文件: {filename} ? (y/n): ")
        if confirm.lower() != "y":
            return {"success": False, "error": "用户取消了操作"}

        try:
            if not filename or not content:
                return {"success": False, "error": "缺少文件名或内容"}
            # 只允许创建在当前工作目录下
            script_path = self.work_directory / filename
            if script_path.exists():
                return {"success": False, "error": f"文件 '{filename}' 已存在"}
            with open(script_path, 'w', encoding='utf-8', errors='replace') as f:
                f.write(content)
            # 可选：为 .sh/.bat/.ps1/.py 等脚本加可执行权限（仅Linux/Mac）
            import stat
            if script_path.suffix in ['.sh', '.py', '.pl', '.rb'] and hasattr(os, 'chmod'):
                try:
                    os.chmod(script_path, os.stat(script_path).st_mode | stat.S_IXUSR)
                except Exception:
                    pass
            return {"success": True, "filename": filename, "full_path": str(script_path), "message": f"成功创建脚本文件 '{filename}'"}
        except Exception as e:
            return {"success": False, "error": f"创建脚本文件失败: {str(e)}"}

    def action_read_file(self, file_path: str, max_lines: int = 100) -> dict:
        """读取文本文件内容，返回前max_lines行，支持自动编码检测，适合预览文本文件。"""
        try:
            abs_path = Path(file_path)
            if not abs_path.is_absolute():
                abs_path = self.work_directory / file_path
            if not abs_path.exists():
                return {"success": False, "error": f"文件 '{file_path}' 不存在"}
            if not abs_path.is_file():
                return {"success": False, "error": f"'{file_path}' 不是一个文件"}
            stat = abs_path.stat()
            text_exts = ['.txt', '.md', '.json', '.py', '.csv', '.log', '.ini', '.yaml', '.yml']
            if abs_path.suffix.lower() not in text_exts and stat.st_size > 1024*1024:
                return {"success": False, "error": "仅支持文本文件或小于1MB的文件读取"}
            # 自动尝试多种编码
            encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16', 'latin1']
            content = None
            for enc in encodings:
                try:
                    with open(abs_path, 'r', encoding=enc, errors='replace') as f:
                        lines = []
                        for i, line in enumerate(f):
                            if i >= max_lines:
                                lines.append('... (内容过长已截断)')
                                break
                            lines.append(line.rstrip('\n'))
                        content = '\n'.join(lines)
                    break
                except Exception:
                    continue
            if content is None:
                return {"success": False, "error": "无法读取文件内容，可能编码不受支持"}
            return {"success": True, "file": str(abs_path), "content": content}
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {str(e)}"}

    def execute_command(self, command: Dict) -> Dict[str, Any]:
        """执行AI生成的命令，支持批量命令和cls命令"""
        print(f"🔍 正在执行命令: {command}")
        action = command.get("action")
        params = command.get("params", {})

        if action == "cls":
            import os
            os.system('cls' if os.name == 'nt' else 'clear')
            return {"success": True, "message": "屏幕已清空"}

        elif action == "batch":
            commands = params.get("commands", [])
            results = []
            all_success = True
            for subcmd in commands:
                sub_action = subcmd.get("action")
                sub_result = self.execute_command(subcmd)
                results.append({"action": sub_action, "result": sub_result})
                if not sub_result.get("success", True):
                    all_success = False
            return {"success": all_success, "results": results}

        elif action == "list":
            path = params.get("path")
            file_filter = params.get("filter")
            smart_filter = params.get("smart_filter")  # 智能过滤条件

            # 首先获取所有文件
            result = self.action_list_directory(path, file_filter)

            if result["success"]:
                # 如果有智能过滤条件，使用AI进行筛选
                if smart_filter:
                    print(f"🧠 正在使用AI智能过滤: {smart_filter}")
                    filtered_result = self.action_intelligent_filter(result, smart_filter)
                    if filtered_result["success"]:
                        result = filtered_result

                filter_info = result.get("filter_info", "")
                smart_info = f" [智能过滤: {smart_filter}]" if smart_filter else ""
                print(f"\n📁 目录内容 ({result['path']}){filter_info}{smart_info}:")
                print("-" * 80)
                for item in result["items"]:
                    icon = "📁" if item["type"] == "directory" else "📄"
                    print(f"{icon} {item['name']:<40} {item['size']:>10} bytes  {item['modified']}")
                print("-" * 80)
                print(f"📊 统计: {result['total_dirs']} 个文件夹, {result['total_files']} 个文件")
                if file_filter:
                    print(f"🔍 已应用过滤器: {file_filter}")
                if smart_filter:
                    print(f"🧠 智能过滤条件: {smart_filter}")
            else:
                print(f"❌ {result['error']}")

            return result

        elif action == "cd":
            path = params.get("path", "")
            result = self.action_change_directory(path)

            if result["success"]:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result['error']}")

            return result

        elif action == "rename":
            old_name = params.get("old_name")
            new_name = params.get("new_name")
            if old_name and new_name:
                result = self.action_rename_file(old_name, new_name)

                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")

                return result

        elif action == "move":
            source = params.get("source")
            destination = params.get("destination")
            if source and destination:
                result = self.action_move_file(source, destination)

                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")

                return result

        elif action == "delete":
            # 支持多种参数名: file_name, path, name
            file_name = params.get("file_name") or params.get("path") or params.get("name")
            if file_name:
                result = self.action_delete_file(file_name, False)

                if result["success"]:
                    print(f"✅ {result['message']}")
                elif result.get("confirmation_needed"):
                    print(f"⚠️ {result['warning']}")
                    print(f"💡 如需确认删除，请使用：删除{file_name}并确认")

                return result
            else:
                print("❌ 删除命令缺少文件名参数")
                return {"success": False, "error": "缺少文件名参数"}

        elif action == "mkdir":
            path = params.get("path")
            if path:
                result = self.action_create_directory(path)

                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")

                return result

        elif action == "info":
            # 支持多种参数名: file_name, path, name
            file_name = params.get("file_name") or params.get("path") or params.get("name")
            if file_name:
                result = self.action_get_file_info(file_name)

                if result["success"]:
                    print(f"\n📋 文件信息：")
                    print(f"名称: {result['name']}")
                    print(f"类型: {result['type']}")
                    print(f"大小: {result['size']} bytes")
                    print(f"创建时间: {result['created']}")
                    print(f"修改时间: {result['modified']}")
                    print(f"权限: {result['permissions']}")
                    print(f"完整路径: {result['full_path']}")
                else:
                    print(f"❌ {result['error']}")

                return result
            else:
                print("❌ 查看文件信息命令缺少文件名参数")
                return {"success": False, "error": "缺少文件名参数"}

        elif action == "ffmpeg":
            source = params.get("source")
            target = params.get("target")
            options = params.get("options")
            if source and target:
                result = self.action_ffmpeg(source, target, options)
                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")
                return result
            else:
                print("❌ 命令缺少参数 source 或 target")
                return {"success": False, "error": "缺少 source 或 target 参数"}

        elif action == "summarize":
            file_path = params.get("path")
            if file_path:
                result = self.action_summarize_file(file_path)
                if result["success"]:
                    print(f"\n📄 文件 {result['file']} 总结：")
                    print(result["summary"])
                else:
                    print(f"❌ {result['error']}")
                return result
            else:
                print("❌ summarize命令缺少path参数")
                return {"success": False, "error": "缺少path参数"}

        elif action == "shell":
            shell_cmd = params.get("command")
            if shell_cmd:
                result = self.action_shell_command(shell_cmd)
                if result["success"]:
                    print(f"\n💻 系统命令输出:\n{result['stdout']}")
                else:
                    print(f"❌ 系统命令执行失败: {result.get('stderr', result.get('error', '未知错误'))}")
                return result
            else:
                print("❌ shell命令缺少command参数")
                return {"success": False, "error": "缺少command参数"}

        elif action == "script":
            filename = params.get("filename")
            content = params.get("content")
            if filename and content:
                result = self.action_create_script(filename, content)
                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")
                return result
            else:
                print("❌ script命令缺少filename或content参数")
                return {"success": False, "error": "缺少filename或content参数"}
        
        elif action == "read":
            file_path = params.get("path")
            max_lines = params.get("max_lines", 100)
            if file_path:
                result = self.action_read_file(file_path, max_lines)
                if result["success"]:
                    print(f"\n📄 文件 {result['file']} 内容预览：")
                else:
                    print(f"❌ {result['error']}")
                return result
            else:
                print("❌ read命令缺少path参数")
                return {"success": False, "error": "缺少path参数"}

        return {"success": False, "error": "未知的操作类型"}

    def run(self):
        """运行AI Agent主循环，支持自动多轮命令执行，AI可根据上次执行结果继续生成命令，遇到{"action": "done"}时终止。"""
        print("🤖 增强版文件管理AI Agent已启动")
        print(f"📁 当前工作目录: {self.work_directory}")
        print(f"🧠 使用模型: {self.model_name}")
        print("💡 输入 'exit' 或 'quit' 退出程序")
        print("🔄 支持切换目录和各种文件管理操作")
        print("🎬 支持媒体文件处理（需提前安装ffmpeg并配置PATH）")
        print("=" * 80)

        import os
        os_name = os.name

        import subprocess
        import re
        system_cmd_patterns = [
            r'^cd(\s+.+)?$',
            r'^(dir|ls|list)(\s+.+)?$',
            r'^(del|delete|rm)(\s+.+)?$',
            r'^(ping)(\s+.+)?$',
            r'^(ipconfig|ifconfig)(\s+.+)?$',
            r'^(type|cat)(\s+.+)?$',
            r'^(echo)(\s+.+)?$',
            r'^(whoami|hostname|date|time)(\s+.+)?$',
            r'^(wmic|net)(\s+.+)?$',
        ]
        system_cmd_re = re.compile('|'.join(system_cmd_patterns), re.IGNORECASE)

        while True:
            try:
                # 显示完整路径，使用tab补全
                if self.input_handler:
                    user_input = self.input_handler.get_input_with_completion(f"\n👤 [{str(self.work_directory)}]: ").strip()
                else:
                    user_input = input(f"\n👤 [{str(self.work_directory)}]: ").strip()
                
                if user_input.lower() in ['exit', 'quit', '退出']:
                    break
                if user_input.lower() == 'cls' or user_input.lower() == 'clear' or user_input.lower() == '清空屏幕':
                    # 清空屏幕
                    import os
                    os.system('cls' if os_name == 'nt' else 'clear')
                    continue
                if not user_input:
                    continue

                # 检查是否为可执行文件，如果是则直接执行
                if self._is_executable_file(user_input):
                    # 检测到可执行文件，直接运行
                    self._execute_file_directly(user_input)
                    continue

                # 判断是否为常见系统命令
                if system_cmd_re.match(user_input):
                    if user_input.lower().startswith('ls') and os_name == 'nt':
                        user_input = 'dir ' + user_input[2:].strip()
                    elif user_input.lower().startswith('list') and os_name == 'nt':
                        user_input = 'dir ' + user_input[4:].strip()
                    elif user_input.lower().startswith('dir') and os_name != 'nt':
                        user_input = 'ls ' + user_input[3:].strip()

                    # 直接执行系统命令
                    try:
                        # Windows下cd命令特殊处理
                        if user_input.lower().startswith('cd '):
                            path = user_input[3:].strip()
                            result = self.action_change_directory(path)
                            if result["success"]:
                                print(f"✅ {result['message']}")
                            else:
                                print(f"❌ {result['error']}")
                        else:
                            # 其它命令直接用subprocess
                            completed = subprocess.run(user_input, shell=True, capture_output=True, text=True, encoding='utf-8', errors='replace', cwd=str(self.work_directory))
                            if completed.stdout:
                                print(completed.stdout)
                            if completed.stderr:
                                print(completed.stderr)
                    except Exception as e:
                        print(f"❌ 系统命令执行异常: {e}")
                    continue

                last_result = None
                next_input = user_input
                while True:
                    # 获取AI回复
                    print("🤖 AI正在思考...")
                    # 流式输出AI回复
                    stream_gen = self.call_ai(next_input, context=json.dumps(last_result, ensure_ascii=False) if last_result else "", stream=True)
                    ai_response = ""
                    try:
                        for chunk in stream_gen:
                            print(chunk, end="", flush=True)
                            ai_response += chunk
                    except Exception as e:
                        print(f"\n❌ AI流式输出异常: {e}")
                    print()
                    # 提取并执行命令
                    command = self.extract_json_command(ai_response)
                    if not command:
                        # 未检测到有效命令，终止本轮
                        break
                    if command.get("action") == "done":
                        print("✅ AI已声明所有操作完成。");
                        break
                    print("\n⚡ 执行操作...")
                    result = self.execute_command(command)
                    # 保存操作结果
                    self.operation_results.append({
                        "command": command,
                        "result": result,
                        "timestamp": datetime.now().isoformat()
                    })
                    last_result = result
                    # 若AI未自动输出done，则继续将本次结果传给AI生成下一个命令
                    next_input = "命令执行结果：" + json.dumps(self.operation_results[-1], ensure_ascii=False)

                    if result.get("success", True) and command.get("last_action") == True:
                        print("✅ 操作已完成")
                        break

            except KeyboardInterrupt:
                print("\n👋 程序已中断，再见！")
                break
            except Exception as e:
                print(f"❌ 发生错误: {str(e)}")

    def _is_executable_file(self, user_input: str) -> bool:
        """
        检查输入是否为可执行文件
        Args:
            user_input: 用户输入
        Returns:
            True if executable, False otherwise
        """
        import shutil
        import os
        
        # 去除可能的参数
        command = user_input.split()[0] if user_input.strip() else ""
        if not command:
            return False
            
        # 检查是否为绝对路径或相对路径的可执行文件
        if os.path.isabs(command):
            # 绝对路径
            if os.path.isfile(command) and os.access(command, os.X_OK):
                return True
        else:
            # 相对路径或文件名
            # 1. 检查当前目录
            current_path = self.work_directory / command
            if current_path.is_file() and os.access(current_path, os.X_OK):
                return True
                
            # 2. 检查当前目录下的常见可执行文件扩展名
            for ext in ['.exe', '.bat', '.cmd', '.com', '.py', '.ps1']:
                current_path_with_ext = self.work_directory / (command + ext)
                if current_path_with_ext.is_file():
                    return True
                    
            # 3. 检查PATH环境变量
            if shutil.which(command):
                return True
                
        return False
    
    def _execute_file_directly(self, user_input: str) -> bool:
        """
        直接执行可执行文件
        Args:
            user_input: 用户输入
        Returns:
            True if executed successfully, False otherwise
        """
        import subprocess
        import os
        
        try:
            # 在Windows下，如果是Python文件，需要特殊处理
            if user_input.endswith('.py') or user_input.split()[0].endswith('.py'):
                # Python文件
                completed = subprocess.run(['python', user_input], 
                                         shell=True, 
                                         capture_output=True, 
                                         text=True, 
                                         encoding='utf-8', 
                                         errors='replace', 
                                         cwd=str(self.work_directory))
            else:
                # 其他可执行文件
                completed = subprocess.run(user_input, 
                                         shell=True, 
                                         capture_output=True, 
                                         text=True, 
                                         encoding='utf-8', 
                                         errors='replace', 
                                         cwd=str(self.work_directory))
            
            # 输出结果
            if completed.stdout:
                print(completed.stdout)
            if completed.stderr:
                print(completed.stderr)
                
            return True
            
        except Exception as e:
            print(f"❌ 执行文件失败: {e}")
            return False
