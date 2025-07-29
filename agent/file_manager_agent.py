import ollama
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
import shutil
from datetime import datetime

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
        self.system_prompt = """
你是一个专业的文件管理助手。你可以帮助用户管理文件，包括：
1. 列出目录内容
2. 重命名文件和文件夹
3. 移动文件和文件夹
4. 删除文件和文件夹
5. 创建新文件夹
6. 查看文件信息
7. 切换工作目录
8. 转换媒体文件格式

请按照以下格式回复：
- 如果用户想执行文件操作，请在回复中包含JSON格式的操作指令
- JSON格式：{"action": "操作类型", "params": {"参数名": "参数值"}}
- 支持的操作类型：list, rename, move, delete, mkdir, info, cd

列表命令使用规则：
- 列出所有文件：{"action": "list", "params": {}} 
- 当用户说"列举所有文件"、"显示所有文件"、"查看所有文件"、"列出文件"时，使用空参数

列举指定目录下的文件：
- {"action": "list", "params": {"path": "指定目录路径"}}

简单过滤（使用filter参数）：
- 按文件扩展名：{"action": "list", "params": {"filter": "txt"}}
- 按文件名关键词：{"action": "list", "params": {"filter": "关键词"}}
- 仅限于简单的文件名匹配

智能过滤（使用smart_filter参数）：
- 时间条件：{"action": "list", "params": {"smart_filter": "2025年4月1日之前的文件"}}
- 大小条件：{"action": "list", "params": {"smart_filter": "大于1MB的文件"}}
- 复合条件：{"action": "list", "params": {"smart_filter": "最近一周修改的大文件"}}
- 任何涉及文件属性比较、日期计算、大小判断的复杂条件
- 涉及到多个关键词分别过滤不同文件的情况, 比如列举出所有视频文件这类需求，必须使用智能过滤
- 输出结果需要避免重复项

转换媒体文件格式：
- {"action": "convert", "params": { "source": "源文件路径", "target": "目标文件路径", "options": "除了源文件和目标文件之外的其他ffmpeg命令参数, 不包括ffmpeg本身"}}

关键判断：如果过滤条件涉及时间、大小、日期比较或复杂逻辑，必须使用smart_filter！
- 除了JSON指令外，还要给出自然语言的解释

重要：
- 不要"预测"或"编造"文件列表，系统会执行你的命令并显示实际结果
- 当执行列表命令时，只提供JSON指令和说明，不要列出具体的文件名
- 等待系统执行命令后，你会收到实际的操作结果用于后续建议
- 删除操作需要确认：使用 {"action": "delete", "params": {"path": "文件名", "confirmed": true}}
- 当用户说"删除并确认"或"强制删除"时，设置 "confirmed": true
- 只把包含通配符"*"的用户输入字串当作过滤条件，否则可以考虑作为目录名，文件名或者其它信息
- 如果用户需要转换媒体文件格式，使用convert命令

当你收到操作结果时，请根据结果分析情况并提供进一步的建议或操作。

安全原则：
- 删除操作需要用户确认
- 不要操作系统重要文件
- 重命名时检查目标文件是否已存在
- 切换目录前验证目录是否存在
"""

    def _validate_model(self):
        """验证模型是否可用"""
        try:
            models = ollama.list()
            # 获取可用模型列表
            available_models = []
            for model in models.get('models', []):
                if hasattr(model, 'model'):  # 新版本ollama可能有model属性
                    available_models.append(model.model)
                elif isinstance(model, dict):
                    available_models.append(model.get('name', model.get('model', 'unknown')))
                else:
                    # 如果是字符串，直接使用
                    available_models.append(str(model))
            
            if self.model_name not in available_models:
                print(f"⚠️ 警告: 模型 '{self.model_name}' 不在可用模型列表中")
                print(f"📋 可用模型: {available_models}")
                if available_models:
                    print(f"💡 建议使用: {available_models[0]}")
        except Exception as e:
            print(f"⚠️ 无法验证模型: {e}")
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
            messages = [{"role": "system", "content": self.system_prompt}]
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
            
            # 构建对话历史
            messages = [{"role": "system", "content": self.system_prompt}]
            
            # 添加对话历史
            for msg in self.conversation_history[-5:]:  # 只保留最近5轮对话
                messages.append(msg)
            
            # 构建当前用户输入，包含上下文信息
            current_input = f"当前工作目录: {self.work_directory}\n"
            
            # 添加最近的操作结果作为上下文
            if self.operation_results:
                current_input += f"最近的操作结果: {self.operation_results[-1]}\n"
            
            if context:
                current_input += f"操作上下文: {context}\n"
            
            current_input += f"用户输入: {user_input}"
            
            # 添加当前用户输入
            messages.append({"role": "user", "content": current_input})
            
            # 调用Ollama API
            response = ollama.chat(
                model=self.model_name,
                messages=messages,
                stream=False
            )
            
            ai_response = response['message']['content']
            
            # 保存对话历史
            self.conversation_history.append({"role": "user", "content": user_input})
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            return ai_response
            
        except Exception as e:
            error_msg = f"调用Ollama API时出错: {str(e)} (使用模型: {self.model_name})"
            if "status code: 400" in str(e) or "model is required" in str(e):
                error_msg += f"\n💡 建议: 请确保模型 '{self.model_name}' 已安装，运行: ollama pull {self.model_name}"
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

    def list_directory(self, path: Optional[str] = None, file_filter: Optional[str] = None) -> Dict[str, Any]:
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

    def intelligent_filter(self, file_list_result: Dict[str, Any], filter_condition: str) -> Dict[str, Any]:
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

    def change_directory(self, path: str) -> Dict[str, Any]:
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
            
            return {
                "success": True,
                "old_directory": str(old_dir),
                "new_directory": str(new_path),
                "message": f"已切换到目录: {new_path}"
            }
            
        except Exception as e:
            return {"success": False, "error": f"切换目录失败: {str(e)}"}

    def rename_file(self, old_name: str, new_name: str) -> Dict[str, Any]:
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

    def move_file(self, source: str, destination: str) -> Dict[str, Any]:
        """移动文件或文件夹"""
        try:
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

    def delete_file(self, file_name: str, confirmed: bool = False) -> Dict[str, Any]:
        """删除文件或文件夹"""
        if not confirmed:
            return {
                "success": False,
                "warning": f"即将删除 '{file_name}'，请确认是否继续",
                "confirmation_needed": True
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

    def create_directory(self, dir_name: str) -> Dict[str, Any]:
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

    def get_file_info(self, file_name: str) -> Dict[str, Any]:
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

    def convert_media(self, source: str, target: str, options: Optional[str] = None) -> Dict[str, Any]:
        """调用ffmpeg转换媒体文件格式"""
        import subprocess
        if not source or not target:
            return {"success": False, "error": "缺少 source 或 target 参数"}
        
        # 检查源文件是否存在
        source_path = self.work_directory / source
        if not source_path.exists():
            return {"success": False, "error": f"源文件 '{source}' 不存在"}

        ffmpeg_cmd = ["ffmpeg", "-y", "-i", source]
        if options:
            ffmpeg_cmd += options.split()
        ffmpeg_cmd.append(target)
        print(f"🔄 正在执行 ffmpeg 命令: {' '.join(ffmpeg_cmd)}")
        try:
            result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return {"success": True, "message": "媒体文件转换成功"}
            else:
                return {"success": False, "error": f"ffmpeg 执行失败: {result.stderr}"}
        except FileNotFoundError:
            return {"success": False, "error": "未检测到 ffmpeg，请确保已安装并配置好 PATH 环境变量"}
        except Exception as e:
            return {"success": False, "error": f"ffmpeg 执行异常: {str(e)}"}
    
    def execute_command(self, command: Dict) -> Dict[str, Any]:
        """执行AI生成的命令"""
        action = command.get("action")
        params = command.get("params", {})
        
        if action == "list":
            path = params.get("path")
            file_filter = params.get("filter")
            smart_filter = params.get("smart_filter")  # 智能过滤条件
            
            # 首先获取所有文件
            result = self.list_directory(path, file_filter)
            
            if result["success"]:
                # 如果有智能过滤条件，使用AI进行筛选
                if smart_filter:
                    print(f"🧠 正在使用AI智能过滤: {smart_filter}")
                    filtered_result = self.intelligent_filter(result, smart_filter)
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
            result = self.change_directory(path)
            
            if result["success"]:
                print(f"✅ {result['message']}")
            else:
                print(f"❌ {result['error']}")
            
            return result
            
        elif action == "rename":
            old_name = params.get("old_name")
            new_name = params.get("new_name")
            if old_name and new_name:
                result = self.rename_file(old_name, new_name)
                
                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")
                
                return result
                
        elif action == "move":
            source = params.get("source")
            destination = params.get("destination")
            if source and destination:
                result = self.move_file(source, destination)
                
                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")
                
                return result
                
        elif action == "delete":
            # 支持多种参数名: file_name, path, name
            file_name = params.get("file_name") or params.get("path") or params.get("name")
            confirmed = params.get("confirmed", False)
            if file_name:
                result = self.delete_file(file_name, confirmed)
                
                if result["success"]:
                    print(f"✅ {result['message']}")
                elif result.get("confirmation_needed"):
                    print(f"⚠️ {result['warning']}")
                    print(f"💡 如需确认删除，请使用：删除{file_name}并确认")
                else:
                    print(f"❌ {result['error']}")
                
                return result
            else:
                print("❌ 删除命令缺少文件名参数")
                return {"success": False, "error": "缺少文件名参数"}
                
        elif action == "mkdir":
            dir_name = params.get("dir_name")
            if dir_name:
                result = self.create_directory(dir_name)
                
                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")
                
                return result
                
        elif action == "info":
            # 支持多种参数名: file_name, path, name
            file_name = params.get("file_name") or params.get("path") or params.get("name")
            if file_name:
                result = self.get_file_info(file_name)
                
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
        
        elif action == "convert":
            source = params.get("source")
            target = params.get("target")
            options = params.get("options")
            if source and target:
                result = self.convert_media(source, target, options)
                if result["success"]:
                    print(f"✅ {result['message']}")
                else:
                    print(f"❌ {result['error']}")
                return result
            else:
                print("❌ 转换命令缺少参数 source 或 target")
                return {"success": False, "error": "缺少 source 或 target 参数"}

        return {"success": False, "error": "未知的操作类型"}

    def run(self):
        """运行AI Agent主循环"""
        print("🤖 增强版文件管理AI Agent已启动")
        print(f"📁 当前工作目录: {self.work_directory}")
        print(f"🧠 使用模型: {self.model_name}")
        print("💡 输入 'exit' 或 'quit' 退出程序")
        print("🔄 支持切换目录和各种文件管理操作")
        print("🎬 支持媒体文件格式转换（需提前安装ffmpeg并配置PATH）")
        print("=" * 80)
        
        while True:
            try:
                # 显示完整路径
                user_input = input(f"\n👤 您 [{str(self.work_directory)}]: ").strip()
                
                if user_input.lower() in ['exit', 'quit', '退出']:
                    print("👋 再见！")
                    break
                
                if not user_input:
                    continue
                
                # 获取AI回复
                print("🤖 AI正在思考...")
                # 流式输出AI回复
                stream_gen = self.call_ai(user_input, stream=True)
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
                if command:
                    print("\n⚡ 执行操作...")
                    result = self.execute_command(command)
                    # 保存操作结果
                    self.operation_results.append({
                        "command": command,
                        "result": result,
                        "timestamp": datetime.now().isoformat()
                    })
                    # 简化后续建议逻辑，避免无限循环
                    if result.get("success") and result.get("total_files", 0) > 10:
                        print(f"💡 提示: 发现 {result.get('total_files', 0)} 个文件，您可以使用 'cd' 切换目录或执行其他操作")
                
            except KeyboardInterrupt:
                print("\n👋 程序已中断，再见！")
                break
            except Exception as e:
                print(f"❌ 发生错误: {str(e)}")
