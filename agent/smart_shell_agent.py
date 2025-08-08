import ollama
import os
import json
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
import shutil
from datetime import datetime

# 导入历史记录管理器
from .history_manager import HistoryManager

# 导入知识库管理器
try:
    from .knowledge_manager import KnowledgeManager
    KNOWLEDGE_AVAILABLE = True
except ImportError:
    KNOWLEDGE_AVAILABLE = False
    print("⚠️ 知识库功能不可用")

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

class SmartShellAgent:
    def __init__(self, model_name: str = "gemma3:4b", work_directory: Optional[str] = None, provider: str = "ollama", openai_conf: Optional[dict] = None, openwebui_conf: Optional[dict] = None, params: Optional[dict] = None, normal_config: Optional[dict] = None, vision_config: Optional[dict] = None, config_dir: Optional[str] = None):
        """
        初始化Smart Shell
        Args:
            model_name: 模型名称（兼容旧格式）
            work_directory: 工作目录
            provider: 模型服务提供方（兼容旧格式）
            openai_conf: openai参数（兼容旧格式）
            openwebui_conf: openwebui参数（兼容旧格式）
            params: 通用参数（兼容旧格式）
            normal_config: 普通任务模型配置（新格式）
            vision_config: 视觉模型配置（新格式）
            config_dir: 配置文件目录（可选，用于指定历史记录保存位置）
        """
        self.work_directory = Path(work_directory) if work_directory else Path.cwd()
        self.conversation_history = []
        self.operation_results = []
        
        # 初始化历史记录管理器，使用指定的配置目录或自动查找
        if config_dir:
            # 使用指定的配置目录
            self.history_manager = HistoryManager(config_dir)
            self.config_dir = Path(config_dir)
        else:
            # 自动查找配置文件目录
            current_config_dir = Path(".smartshell")
            user_config_dir = Path.home() / ".smartshell"
            
            # 如果用户目录下有配置文件，使用用户目录
            if (user_config_dir / "config.json").exists():
                config_dir = user_config_dir
            elif (current_config_dir / "config.json").exists():
                config_dir = current_config_dir
            else:
                # 默认使用用户目录
                config_dir = user_config_dir
                
            self.history_manager = HistoryManager(str(config_dir))
            self.config_dir = Path(config_dir)

        # 加载配置以确定知识库开关（默认开启）
        self.knowledge_enabled = True
        try:
            cfg_path = self.config_dir / "config.json"
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                self.knowledge_enabled = bool(cfg_data.get("knowledge_enabled", True))
        except Exception as e:
            print(f"⚠️ 读取配置中的知识库开关失败，默认开启: {e}")
        
        # 初始化知识库管理器
        self.knowledge_manager = None
        if KNOWLEDGE_AVAILABLE and self.knowledge_enabled:
            try:
                # 使用轻量级的中文向量模型
                embedding_model = "nomic-embed-text"
                self.knowledge_manager = KnowledgeManager(str(config_dir), embedding_model)
                # 启动时同步知识库
                self.knowledge_manager.sync_knowledge_base()
            except Exception as e:
                print(f"⚠️ 知识库初始化失败: {e}")
                self.knowledge_manager = None

        # 继续初始化其余组件（双模型配置、系统提示词、输入处理器）
        if normal_config and vision_config:
            self.dual_model_mode = True
            self.normal_config = normal_config
            self.vision_config = vision_config
            # 设置普通任务模型
            self.normal_provider = normal_config.get("provider", "ollama")
            self.normal_params = normal_config.get("params", {})
            self.normal_model_name = self.normal_params.get("model", "gemma3:4b")
            # 设置视觉模型
            self.vision_provider = vision_config.get("provider", "ollama")
            self.vision_params = vision_config.get("params", {})
            self.vision_model_name = self.vision_params.get("model", "qwen2.5vl:7b")
            # 兼容旧接口
            self.model_name = self.normal_model_name
            self.provider = self.normal_provider
            self.params = self.normal_params
            self.openai_conf = self.normal_params if self.normal_provider == "openai" else None
            self.openwebui_conf = self.normal_params if self.normal_provider == "openwebui" else None
        else:
            # 兼容旧格式
            self.dual_model_mode = False
            self.model_name = model_name
            self.provider = provider
            self.openai_conf = openai_conf
            self.openwebui_conf = openwebui_conf
            self.params = params
            # 兼容params统一配置
            if self.provider == 'openai' and self.openai_conf is None and params is not None:
                self.openai_conf = params
            if self.provider == 'openwebui' and self.openwebui_conf is None and params is not None:
                self.openwebui_conf = params

        # 验证模型
        self._validate_model()

        # 系统提示词
        prompt_path = os.path.join(os.path.dirname(__file__), 'system_prompt.txt')
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()

        # 初始化输入处理器，确保属性存在
        self.input_handler = None
        if TAB_COMPLETION_AVAILABLE:
            try:
                if INPUT_HANDLER_TYPE == "windows":
                    # 构建初始历史供 prompt_toolkit 使用
                    try:
                        initial_history = self.history_manager.get_all_history()
                    except Exception:
                        initial_history = []
                    self.input_handler = create_windows_input_handler(self.work_directory, initial_history)
                elif INPUT_HANDLER_TYPE == "readline":
                    self.input_handler = create_tab_completer(self.work_directory)
                else:
                    print("⚠️ 未知的输入处理器类型")
            except Exception as e:
                print(f"⚠️ 输入处理器初始化失败: {e}")
        else:
            print("⚠️ Tab补全功能不可用")

    def _save_knowledge_enabled_to_config(self) -> bool:
        """将知识库开关状态保存到 config.json"""
        try:
            cfg_path = self.config_dir / "config.json"
            cfg_data = {}
            if cfg_path.exists():
                try:
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        cfg_data = json.load(f) or {}
                except Exception:
                    cfg_data = {}
            cfg_data["knowledge_enabled"] = bool(self.knowledge_enabled)
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"⚠️ 保存知识库开关到配置失败: {e}")
            return False

    def _enable_knowledge(self) -> Dict[str, Any]:
        """开启知识库功能，持久化并即时生效"""
        if self.knowledge_enabled and self.knowledge_manager is not None:
            return {"success": True, "message": "知识库已处于开启状态"}
        self.knowledge_enabled = True
        saved = self._save_knowledge_enabled_to_config()
        if not KNOWLEDGE_AVAILABLE:
            return {"success": False, "error": "缺少知识库依赖，无法启用"}
        try:
            embedding_model = "nomic-embed-text"
            self.knowledge_manager = KnowledgeManager(str(self.config_dir), embedding_model)
            self.knowledge_manager.sync_knowledge_base()
            return {"success": True, "message": f"知识库已开启{'（已保存配置）' if saved else ''}"}
        except Exception as e:
            self.knowledge_manager = None
            return {"success": False, "error": f"启用知识库失败: {e}"}

    def _disable_knowledge(self) -> Dict[str, Any]:
        """关闭知识库功能，持久化并即时生效"""
        if not self.knowledge_enabled and self.knowledge_manager is None:
            return {"success": True, "message": "知识库已处于关闭状态"}
        self.knowledge_enabled = False
        saved = self._save_knowledge_enabled_to_config()
        # 释放引用（让底层资源由GC清理）
        self.knowledge_manager = None
        return {"success": True, "message": f"知识库已关闭{'（已保存配置）' if saved else ''}"}
        
        # 支持新的双模型配置
        if normal_config and vision_config:
            self.dual_model_mode = True
            self.normal_config = normal_config
            self.vision_config = vision_config
            
            # 设置普通任务模型
            self.normal_provider = normal_config.get("provider", "ollama")
            self.normal_params = normal_config.get("params", {})
            self.normal_model_name = self.normal_params.get("model", "gemma3:4b")
            
            # 设置视觉模型
            self.vision_provider = vision_config.get("provider", "ollama")
            self.vision_params = vision_config.get("params", {})
            self.vision_model_name = self.vision_params.get("model", "qwen2.5vl:7b")
            
            # 兼容旧接口
            self.model_name = self.normal_model_name
            self.provider = self.normal_provider
            self.params = self.normal_params
            self.openai_conf = self.normal_params if self.normal_provider == "openai" else None
            self.openwebui_conf = self.normal_params if self.normal_provider == "openwebui" else None

        else:
            # 兼容旧格式
            self.dual_model_mode = False
            self.model_name = model_name
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

                elif INPUT_HANDLER_TYPE == "readline":
                    self.input_handler = create_tab_completer(self.work_directory)

                else:
                    print("⚠️ 未知的输入处理器类型")
            except Exception as e:
                print(f"⚠️ 输入处理器初始化失败: {e}")
        else:
            print("⚠️ Tab补全功能不可用")
    
    def _validate_model(self):
        """验证模型是否可用（仅ollama模式）"""
        if self.dual_model_mode:
            # 双模型模式：验证两个模型
            self._validate_single_model(self.normal_provider, self.normal_model_name, "普通任务模型")
            self._validate_single_model(self.vision_provider, self.vision_model_name, "视觉模型")
        else:
            # 单模型模式：验证单个模型
            self._validate_single_model(self.provider, self.model_name, "模型")
    
    def _validate_single_model(self, provider: str, model_name: str, model_type: str):
        """验证单个模型是否可用"""
        if provider != "ollama":
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
            if model_name not in available_models:
                print(f"⚠️ 警告: {model_type} '{model_name}' 不在可用模型列表中")
                print(f"📋 可用模型: {available_models}")
                if available_models:
                    print(f"💡 建议使用: {available_models[0]}")
                print(f"💡 请检查 llm-filemgr.json 中的 {model_type.lower().replace('模型', '_model')} 配置")
        except ImportError:
            print(f"❌ 错误: 未安装 ollama 包，无法验证 {model_type}。请运行: pip install ollama")
        except Exception as e:
            print(f"⚠️ 验证{model_type}时出错: {e}")
            print(f"💡 请确保 Ollama 服务正在运行")

    def call_ai(self, user_input: str, context: str = "", stream: bool = False):
        """调用大模型API获取AI回复，支持流式输出。stream=True时返回生成器"""
        try:
            # 确保os未被局部变量遮蔽
            import os
            os_info = os.uname() if hasattr(os, 'uname') else os.name
            messages = [{"role": "system", "content": f"{self.system_prompt}\n当前操作系统信息：{os_info}"}]
            for msg in self.conversation_history[-5:]:
                messages.append(msg)
            
            # 从知识库获取相关上下文
            knowledge_context = ""
            if self.knowledge_manager:
                try:
                    knowledge_context = self.knowledge_manager.get_knowledge_context(user_input)
                    if knowledge_context:
                        print(f"📚 从知识库检索到相关信息")
                except Exception as e:
                    print(f"⚠️ 知识库检索失败: {e}")
            
            current_input = f"当前工作目录: {self.work_directory}\n"
            if self.operation_results:
                current_input += f"最近的操作结果: {self.operation_results[-1]}\n"
            if context:
                current_input += f"操作上下文: {context}\n"
            if knowledge_context:
                current_input += f"知识库相关信息:\n{knowledge_context}\n"
            current_input += f"用户输入: {user_input}"
            messages.append({"role": "user", "content": current_input})

            # 根据模式选择模型配置
            if self.dual_model_mode:
                # 双模型模式：使用普通任务模型
                provider = self.normal_provider
                model_name = self.normal_model_name
                params = self.normal_params
                openai_conf = params if provider == "openai" else None
                openwebui_conf = params if provider == "openwebui" else None
                
                # 检查普通任务模型配置
                if not provider or not model_name:
                    return "❌ 错误：普通任务模型未正确配置。请检查 llm-filemgr.json 中的 normal_model 配置。"
            else:
                # 单模型模式：使用原有配置
                provider = self.provider
                model_name = self.model_name
                openai_conf = self.openai_conf
                openwebui_conf = self.openwebui_conf
                
                # 检查单模型配置
                if not provider or not model_name:
                    return "❌ 错误：模型未正确配置。请检查 llm-filemgr.json 配置文件。"

            if provider == "openai" and openai_conf:
                import requests
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                api_key = openai_conf.get("api_key")
                base_url = openai_conf.get("base_url", "https://api.openai.com/v1")
                model = model_name
                
                # 检查OpenAI配置
                if not api_key:
                    return "❌ 错误：OpenAI API密钥未配置。请在 llm-filemgr.json 中设置 api_key。"
                
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
            elif provider == "openwebui" and openwebui_conf:
                import requests
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                api_key = openwebui_conf.get("api_key")
                base_url = openwebui_conf.get("base_url", "http://localhost:8080/v1")
                model = model_name
                
                # 检查OpenWebUI配置
                if not api_key:
                    return "❌ 错误：OpenWebUI API密钥未配置。请在 llm-filemgr.json 中设置 api_key。"
                
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
                # 检查是否为Ollama提供者
                if provider != "ollama":
                    return f"❌ 错误：不支持的模型提供者 '{provider}'。支持的提供者：ollama, openai, openwebui"
                
                try:
                    import ollama
                except ImportError:
                    return "❌ 错误：未安装 ollama 包。请运行：pip install ollama"
                
                if stream:
                    response = ollama.chat(
                        model=model_name,
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
                        model=model_name,
                        messages=messages,
                        stream=False
                    )
                    ai_response = response['message']['content']
                    self.conversation_history.append({"role": "user", "content": user_input})
                    self.conversation_history.append({"role": "assistant", "content": ai_response})
                    return ai_response
        except Exception as e:
            error_msg = f"调用大模型API时出错: {str(e)} (provider: {provider}, model: {model_name})"
            return error_msg

    def call_ai_multimodal(self, user_input: str, image_path: str, context: str = "", stream: bool = False):
        """调用支持多模态的大模型API进行图片分析，支持流式输出"""
        try:
            import os
            import base64
            os_info = os.uname() if hasattr(os, 'uname') else os.name
            
            # 读取并编码图片
            with open(image_path, 'rb') as image_file:
                image_data = base64.b64encode(image_file.read()).decode('utf-8')
            
            # 构建多模态消息 - 使用简化的系统提示，避免生成JSON命令
            system_prompt = """你是一个图片分析助手。请直接分析用户提供的图片，描述图片中的内容、物体、场景、文字等信息。不要生成任何JSON命令或代码，只提供自然语言的分析结果。"""
            
            messages = [{"role": "system", "content": system_prompt}]
            
            # 添加包含图片的消息 - 使用正确的Ollama格式
            messages.append({
                "role": "user", 
                "content": user_input,
                "images": [image_data]
            })

            # 根据模式选择模型配置
            if self.dual_model_mode:
                # 双模型模式：使用视觉模型
                provider = self.vision_provider
                model_name = self.vision_model_name
                params = self.vision_params
                openai_conf = params if provider == "openai" else None
                openwebui_conf = params if provider == "openwebui" else None
                
                # 检查视觉模型配置
                if not provider or not model_name:
                    return "❌ 错误：视觉模型未正确配置。请检查 llm-filemgr.json 中的 vision_model 配置。"
            else:
                # 单模型模式：使用原有配置
                provider = self.provider
                model_name = self.model_name
                openai_conf = self.openai_conf
                openwebui_conf = self.openwebui_conf
                
                # 检查单模型配置
                if not provider or not model_name:
                    return "❌ 错误：模型未正确配置。请检查 llm-filemgr.json 配置文件。"

            if provider == "ollama":
                try:
                    import ollama
                except ImportError:
                    return "❌ 错误：未安装 ollama 包。请运行：pip install ollama"
                
                if stream:
                    response = ollama.chat(
                        model=model_name,
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
                        model=model_name,
                        messages=messages,
                        stream=False
                    )
                    ai_response = response['message']['content']
                    self.conversation_history.append({"role": "user", "content": user_input})
                    self.conversation_history.append({"role": "assistant", "content": ai_response})
                    return ai_response
            else:
                # 对于不支持多模态的提供者，回退到文本模式
                return f"⚠️ 警告：{provider} 提供者不支持多模态功能，回退到文本模式。\n" + self.call_ai(user_input, context, stream)
                
        except Exception as e:
            error_msg = f"调用多模态大模型API时出错: {str(e)} (provider: {provider}, model: {model_name})"
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
        """执行任意系统命令，支持实时输出和交互输入"""
        # 请求用户确实是否执行这条命令
        if not command.strip():
            return {"success": False, "error": "命令不能为空"}
        confirm = input(f"⚠️ 确认执行系统命令: {command} ? (y/n): ")
        if confirm.lower() != "y":
            return {"success": False, "error": "用户取消了操作"}

        import subprocess
        import sys
        try:
            # 使用Popen启动进程，让进程继承当前终端，支持交互
            process = subprocess.Popen(
                command,
                shell=True,
                stdin=sys.stdin,      # 继承当前终端的输入
                stdout=sys.stdout,    # 继承当前终端的输出
                stderr=sys.stderr,    # 继承当前终端的错误输出
                cwd=str(self.work_directory)
            )
            
            # 等待进程结束
            return_code = process.wait()
            
            if return_code == 0:
                return {"success": True, "message": "命令执行成功"}
            else:
                return {"success": False, "error": f"命令执行失败，退出码: {return_code}"}
                
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

    def action_analyze_image(self, file_path: str, prompt: str = "") -> dict:
        """分析图片内容，支持多种图片格式"""
        try:
            abs_path = Path(file_path)
            if not abs_path.is_absolute():
                abs_path = self.work_directory / file_path
            if not abs_path.exists():
                return {"success": False, "error": f"图片文件 '{file_path}' 不存在"}
            if not abs_path.is_file():
                return {"success": False, "error": f"'{file_path}' 不是一个文件"}
            
            # 检查文件扩展名
            image_exts = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif']
            if abs_path.suffix.lower() not in image_exts:
                return {"success": False, "error": f"不支持的文件格式: {abs_path.suffix}"}
            
            # 构建分析提示
            if prompt:
                analysis_prompt = f"请分析这张图片：{prompt}\n\n图片路径：{str(abs_path)}"
            else:
                analysis_prompt = f"请详细描述这张图片的内容，包括：\n1. 图片中的主要物体和场景\n2. 颜色和构图\n3. 文字内容（如果有）\n4. 图片的整体风格和特点\n\n图片路径：{str(abs_path)}"
            
            # 调用AI进行图片分析
            analysis = self.call_ai_multimodal(analysis_prompt, str(abs_path))
            
            return {"success": True, "analysis": analysis, "file": str(abs_path)}
        except Exception as e:
            return {"success": False, "error": f"图片分析失败: {str(e)}"}

    def action_git(self, command: str, args: Optional[str] = None) -> dict:
        """执行Git命令，支持所有Git操作，写操作需要用户确认"""
        try:
            import subprocess
            import sys
            
            # 构建完整的Git命令
            if args:
                full_command = f"git {command} {args}"
            else:
                full_command = f"git {command}"
            
            # 检查是否为写操作，需要用户确认
            write_commands = [
                'add', 'commit', 'push', 'pull', 'merge', 'rebase', 'reset', 
                'checkout', 'branch', 'tag', 'remote', 'fetch', 'clone', 'init',
                'stash', 'cherry-pick', 'revert', 'clean', 'rm', 'mv'
            ]
            
            is_write_operation = command.lower() in write_commands
            
            if is_write_operation:
                # 显示将要执行的命令并请求用户确认
                print(f"⚠️ 即将执行Git写操作: {full_command}")
                confirm = input("确认执行此Git命令吗？(y/n): ")
                if confirm.lower() != 'y':
                    return {
                        "success": False, 
                        "command": full_command,
                        "error": "用户取消了Git写操作",
                        "message": "Git命令已取消"
                    }
            
            # 检查是否在Git仓库中
            try:
                result = subprocess.run(
                    ["git", "rev-parse", "--git-dir"],
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    errors='replace',
                    cwd=str(self.work_directory),
                    timeout=10
                )
                if result.returncode != 0:
                    return {"success": False, "error": "当前目录不是Git仓库"}
            except subprocess.TimeoutExpired:
                return {"success": False, "error": "Git仓库检查超时"}
            except FileNotFoundError:
                return {"success": False, "error": "Git未安装或不在PATH中"}
            
            # 执行Git命令，使用UTF-8编码并处理编码错误
            process = subprocess.Popen(
                full_command,
                shell=True,
                stdin=sys.stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(self.work_directory)
            )
            
            stdout, stderr = process.communicate()
            return_code = process.returncode
            
            if return_code == 0:
                return {
                    "success": True, 
                    "command": full_command,
                    "output": stdout.strip() if stdout else "",
                    "message": "Git命令执行成功"
                }
            else:
                return {
                    "success": False, 
                    "command": full_command,
                    "error": stderr.strip() if stderr else f"Git命令执行失败，退出码: {return_code}",
                    "output": stdout.strip() if stdout else ""
                }
                
        except Exception as e:
            return {"success": False, "error": f"Git命令执行异常: {str(e)}"}

    def action_diff(self, file1: str, file2: str, options: Optional[str] = None) -> dict:
        """跨平台文件比较：Windows上优先使用diff.exe，否则使用fc命令；其他平台使用diff命令"""
        try:
            import subprocess
            import sys
            import os
            import shutil
            import platform
            from pathlib import Path
            
            # 检查文件是否存在
            file1_path = Path(file1)
            file2_path = Path(file2)
            
            if not file1_path.exists():
                return {"success": False, "error": f"文件不存在: {file1}"}
            if not file2_path.exists():
                return {"success": False, "error": f"文件不存在: {file2}"}
            
            # 根据操作系统选择合适的比较命令
            if platform.system() == "Windows":
                # Windows平台：优先使用diff.exe，否则使用fc命令
                if shutil.which("diff.exe"):
                    # 使用diff.exe
                    if options:
                        full_command = f"diff.exe {options} \"{file1}\" \"{file2}\""
                    else:
                        full_command = f"diff.exe \"{file1}\" \"{file2}\""
                    command_type = "diff.exe"
                else:
                    # 使用fc命令
                    if options:
                        full_command = f"cmd /c fc {options} \"{file1}\" \"{file2}\""
                    else:
                        full_command = f"cmd /c fc \"{file1}\" \"{file2}\""
                    command_type = "fc"
            else:
                # 其他平台：使用diff命令
                if options:
                    full_command = f"diff {options} \"{file1}\" \"{file2}\""
                else:
                    full_command = f"diff \"{file1}\" \"{file2}\""
                command_type = "diff"
            
            # 执行比较命令，使用UTF-8编码并处理编码错误
            process = subprocess.Popen(
                full_command,
                shell=True,
                stdin=sys.stdin,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                cwd=str(self.work_directory)
            )
            
            stdout, stderr = process.communicate()
            return_code = process.returncode
            
            # 根据命令类型处理返回码
            if command_type == "fc":
                # fc命令的特殊处理：返回码1表示有差异，0表示无差异
                if return_code in [0, 1]:
                    return {
                        "success": True, 
                        "command": full_command,
                        "command_type": command_type,
                        "output": stdout.strip() if stdout else "",
                        "has_differences": return_code == 1,
                        "message": "文件比较完成" + ("，发现差异" if return_code == 1 else "，文件相同")
                    }
                else:
                    return {
                        "success": False, 
                        "command": full_command,
                        "command_type": command_type,
                        "error": stderr.strip() if stderr else f"fc命令执行失败，退出码: {return_code}",
                        "output": stdout.strip() if stdout else ""
                    }
            else:
                # diff/diff.exe命令：返回码0表示无差异，1表示有差异，2表示错误
                if return_code in [0, 1]:
                    return {
                        "success": True, 
                        "command": full_command,
                        "command_type": command_type,
                        "output": stdout.strip() if stdout else "",
                        "has_differences": return_code == 1,
                        "message": "文件比较完成" + ("，发现差异" if return_code == 1 else "，文件相同")
                    }
                else:
                    return {
                        "success": False, 
                        "command": full_command,
                        "command_type": command_type,
                        "error": stderr.strip() if stderr else f"{command_type}命令执行失败，退出码: {return_code}",
                        "output": stdout.strip() if stdout else ""
                    }
                
        except Exception as e:
            return {"success": False, "error": f"文件比较命令执行异常: {str(e)}"}

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

            if not result["success"]:
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
                    print(f"\n💻 系统命令执行成功: {result['message']}")
                else:
                    print(f"❌ 系统命令执行失败: {result.get('error', '未知错误')}")
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
        
        elif action == "analyze_image":
            file_path = params.get("path")
            prompt = params.get("prompt", "")
            if file_path:
                result = self.action_analyze_image(file_path, prompt)
                if result["success"]:
                    print(f"\n🖼️ 图片分析结果 ({result['file']}):")
                    print("=" * 60)
                    print(result["analysis"])
                    print("=" * 60)
                else:
                    print(f"❌ {result['error']}")
                return result
            else:
                print("❌ analyze_image命令缺少path参数")
                return {"success": False, "error": "缺少path参数"}

        elif action == "git":
            git_command = params.get("command")
            git_args = params.get("args")
            if git_command:
                result = self.action_git(git_command, git_args)
                if result["success"]:
                    print(f"\n🔧 Git命令执行成功: {result['command']}")
                    if result.get("output"):
                        print("📤 输出:")
                        print(result["output"])
                else:
                    # 检查是否为用户取消的情况
                    if "用户取消了Git写操作" in result.get("error", ""):
                        print(f"ℹ️ {result['message']}")
                    else:
                        print(f"❌ Git命令执行失败: {result['error']}")
                    if result.get("output"):
                        print("📤 输出:")
                        print(result["output"])
                return result
            else:
                print("❌ git命令缺少command参数")
                return {"success": False, "error": "缺少command参数"}

        elif action == "diff":
            file1 = params.get("file1")
            file2 = params.get("file2")
            options = params.get("options")
            if file1 and file2:
                result = self.action_diff(file1, file2, options)
                if result["success"]:
                    command_type = result.get("command_type", "unknown")
                    print(f"\n🔍 文件比较完成 (使用 {command_type}): {result['command']}")
                    print(f"📊 结果: {result['message']}")
                    if result.get("output"):
                        print("📤 差异详情:")
                        print(result["output"])
                else:
                    print(f"❌ 文件比较失败: {result['error']}")
                    if result.get("output"):
                        print("📤 输出:")
                        print(result["output"])
                return result
            else:
                print("❌ diff命令缺少file1或file2参数")
                return {"success": False, "error": "缺少file1或file2参数"}

        elif action == "knowledge_sync":
            """同步知识库"""
            if not self.knowledge_enabled:
                return {"success": False, "error": "知识库功能已关闭，可使用 'knowledge on' 开启"}
            if not self.knowledge_manager:
                return {"success": False, "error": "知识库功能不可用"}
            
            try:
                self.knowledge_manager.sync_knowledge_base()
                return {"success": True, "message": "知识库同步完成"}
            except Exception as e:
                return {"success": False, "error": f"知识库同步失败: {str(e)}"}

        elif action == "knowledge_stats":
            """获取知识库统计信息"""
            if not self.knowledge_enabled:
                return {"success": False, "error": "知识库功能已关闭，可使用 'knowledge on' 开启"}
            if not self.knowledge_manager:
                return {"success": False, "error": "知识库功能不可用"}
            
            try:
                stats = self.knowledge_manager.get_knowledge_stats()
                if stats:
                    print(f"\n📊 知识库统计信息:")
                    print(f"📄 文档总数: {stats.get('total_documents', 0)}")
                    print(f"📝 文本片段总数: {stats.get('total_chunks', 0)}")
                    print(f"📁 支持的文件类型: {', '.join(stats.get('supported_extensions', []))}")
                    
                    file_types = stats.get('file_types', {})
                    if file_types:
                        print(f"📋 文件类型分布:")
                        for ext, count in file_types.items():
                            print(f"  {ext}: {count} 个文件")
                else:
                    print("❌ 获取知识库统计信息失败")
                
                return {"success": True, "stats": stats}
            except Exception as e:
                return {"success": False, "error": f"获取知识库统计信息失败: {str(e)}"}

        elif action == "knowledge_search":
            """搜索知识库"""
            if not self.knowledge_enabled:
                return {"success": False, "error": "知识库功能已关闭，可使用 'knowledge on' 开启"}
            if not self.knowledge_manager:
                return {"success": False, "error": "知识库功能不可用"}
            
            query = params.get("query", "")
            top_k = params.get("top_k", 5)
            
            if not query:
                return {"success": False, "error": "缺少搜索查询参数"}
            
            try:
                results = self.knowledge_manager.search_knowledge(query, top_k)
                if results:
                    print(f"\n🔍 知识库搜索结果 (查询: '{query}'):")
                    print("=" * 80)
                    for i, result in enumerate(results, 1):
                        print(f"{i}. 来源: {result['source']}")
                        print(f"   相似度: {1 - result['similarity']:.3f}")
                        print(f"   内容: {result['content'][:200]}...")
                        print("-" * 40)
                else:
                    print(f"🔍 未找到相关结果: '{query}'")
                
                return {"success": True, "results": results, "query": query}
            except Exception as e:
                return {"success": False, "error": f"知识库搜索失败: {str(e)}"}

        elif action == "knowledge_enable" or action == "knowledge_on":
            result = self._enable_knowledge()
            if result.get("success"):
                print(f"✅ {result.get('message', '知识库已开启')}")
            else:
                print(f"❌ {result.get('error', '开启失败')}")
            return result

        elif action == "knowledge_disable" or action == "knowledge_off":
            result = self._disable_knowledge()
            if result.get("success"):
                print(f"✅ {result.get('message', '知识库已关闭')}")
            else:
                print(f"❌ {result.get('error', '关闭失败')}")
            return result

        return {"success": False, "error": "未知的操作类型"}

    def run(self):
        """运行AI Agent主循环，支持自动多轮命令执行，AI可根据上次执行结果继续生成命令，遇到{"action": "done"}时终止。"""
        import sys
        
        # 启动时提示知识库状态
        if not self.knowledge_enabled:
            print("知识库当前处于关闭状态。可使用 'knowledge on' 或 '开启知识库' 来开启")
        elif not self.knowledge_manager:
            # 已开启但不可用（依赖缺失或初始化失败）
            print("知识库已开启但当前不可用。请检查依赖或稍后重试。可使用 'knowledge off' 暂时关闭。")

        print("输入 'exit' 或 'quit' 退出程序, 输入 'help' 查看帮助")
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
                # 获取用户输入，支持历史记录
                user_input = self._get_user_input_with_history()
                
                # 保存到历史记录（非空输入）
                if user_input.strip():
                    self.history_manager.add_entry(user_input)
                
                if user_input.lower() in ['exit', 'quit', '退出']:
                    break
                if user_input.lower() == 'cls' or user_input.lower() == 'clear' or user_input.lower() == '清空屏幕':
                    # 清空屏幕
                    import os
                    os.system('cls' if os_name == 'nt' else 'clear')
                    continue
                if user_input.lower() == 'clear history' or user_input.lower() == '清除历史记录':
                    # 清除历史记录
                    self.history_manager.clear_history()
                    print("✅ 历史记录已清除")
                    continue
                
                # 知识库开关命令（不受当前开关状态限制）
                if user_input.lower() in ['knowledge on', 'knowledge enable', '开启知识库']:
                    self.execute_command({"action": "knowledge_on", "params": {}})
                    continue
                if user_input.lower() in ['knowledge off', 'knowledge disable', '关闭知识库']:
                    self.execute_command({"action": "knowledge_off", "params": {}})
                    continue

                # 知识库相关命令
                if self.knowledge_enabled and self.knowledge_manager:
                    if user_input.lower() in ['knowledge sync', '同步知识库', '知识库同步']:
                        result = self.execute_command({"action": "knowledge_sync", "params": {}})
                        continue
                    
                    if user_input.lower() in ['knowledge stats', '知识库统计', '查看知识库']:
                        result = self.execute_command({"action": "knowledge_stats", "params": {}})
                        continue
                    
                    if user_input.lower().startswith('knowledge search ') or user_input.lower().startswith('搜索知识库 '):
                        query = user_input[16:] if user_input.lower().startswith('knowledge search ') else user_input[5:]
                        if query.strip():
                            result = self.execute_command({
                                "action": "knowledge_search", 
                                "params": {"query": query.strip()}
                            })
                        else:
                            print("❌ 请提供搜索查询内容")
                        continue
                else:
                    # 如果知识库关闭，拦截相关命令并提示
                    if user_input.lower().startswith('knowledge '):
                        print("ℹ️ 知识库已关闭，可使用 'knowledge on' 开启")
                        continue
                if user_input.lower() == 'help' or user_input.lower() == '帮助':
                    # 显示帮助信息
                    print("\n🌟 Smart Shell 帮助信息")
                    print("=" * 80)
                    print("\n📌 内置命令：")
                    print("  1. exit, quit, 退出            - 退出程序")
                    print("  2. cls, clear, 清空屏幕        - 清空屏幕")
                    print("  3. clear history, 清除历史记录 - 清除命令历史记录")
                    print("  4. help, 帮助                  - 显示此帮助信息")
                    
                    if self.knowledge_enabled:
                        print("\n📚 知识库命令：")
                        print("  5. knowledge on/off, 开启/关闭知识库  - 开关知识库功能（状态会保存到config.json）")
                        print("  6. knowledge sync, 同步知识库        - 同步知识库文档")
                        print("  7. knowledge stats, 知识库统计       - 查看知识库统计信息")
                        print("  8. knowledge search <查询>           - 搜索知识库")
                    
                    print("\n📌 系统命令：")
                    print("  在PATH环境变量中能够找到的命令都可以直接使用")
                    print("\n📌 自然语言命令：")
                    print("您可以使用自然语言描述您的需求，例如：")
                    print("  1. 创建一个名为test的文件夹")
                    print("  2. 将文件a.txt重命名为b.txt")
                    print("  3. 分析这张图片的内容")
                    print("  4. 总结这个文本文件")
                    print("  5. 将视频转换为mp4格式")
                    print("  6. 比较两个文件的差异")
                    print("  7. 查找最近修改的文件")
                    print("  8. 删除所有临时文件")
                    
                    if self.knowledge_manager:
                        print("  9. 同步知识库")
                        print("  10. 查看知识库统计")
                        print("  11. 在知识库中搜索特定内容")
                    
                    print("\n💡 提示：")
                    print("  - Tab键可以自动补全文件路径")
                    print("  - 上下方向键可以浏览历史命令")
                    print("  - 支持中英文混合输入")
                    print("  - AI会理解您的自然语言指令并执行相应操作")
                    if self.knowledge_manager:
                        print("  - 知识库会自动检索相关信息来辅助AI回答")
                    print("=" * 80)
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
                            if not result["success"]:
                                print(f"❌ {result['error']}")
                        else:
                            # 其它命令直接用subprocess，继承当前终端
                            try:
                                process = subprocess.Popen(
                                    user_input,
                                    shell=True,
                                    stdin=sys.stdin,
                                    stdout=sys.stdout,
                                    stderr=sys.stderr,
                                    cwd=str(self.work_directory)
                                )
                                
                                # 等待进程结束
                                return_code = process.wait()
                                if return_code != 0:
                                    print(f"⚠️ 命令退出码: {return_code}")
                            except Exception as e:
                                print(f"❌ 命令执行异常: {e}")
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
                        # AI输出完成后添加换行符
                        print()
                    except Exception as e:
                        print(f"\n❌ AI流式输出异常: {e}")
                    # 提取并执行命令
                    command = self.extract_json_command(ai_response)
                    if not command:
                        # 未检测到有效命令，终止本轮
                        break
                    if command.get("action") == "done":
                        print("✅ AI已声明所有操作完成。");
                        break
                    print("⚡ 执行操作...")
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
    
    def _get_user_input_with_history(self) -> str:
        """
        获取用户输入，支持历史记录导航
        Returns:
            用户输入的字符串
        """
        import sys
        import platform
        
        prompt = f"👤 [{str(self.work_directory)}]: "
        
        # 重置历史记录索引
        self.history_manager.reset_index()

        # 优先使用已初始化的输入处理器（例如 Windows 下的 prompt_toolkit 补全）
        if self.input_handler is not None:
            try:
                user_input = self.input_handler.get_input_with_completion(prompt)
                # 这里不直接写入 HistoryManager，交由上层 run() 统一处理，避免重复
                return user_input
            except Exception as e:
                print(f"⚠️ 输入处理器出错，回退到平台特定输入方案: {e}")
        
        # 在Windows系统上，优先使用prompt_toolkit以获得更好的中文输入支持
        if platform.system() == "Windows":
            try:
                # 尝试使用prompt_toolkit
                from prompt_toolkit import PromptSession
                from prompt_toolkit.history import InMemoryHistory
                
                # 创建历史记录
                history = InMemoryHistory()
                for entry in self.history_manager.get_all_history():
                    history.append_string(entry)
                
                # 创建会话
                session = PromptSession(history=history)
                
                # 获取用户输入
                user_input = session.prompt(prompt).strip()
                
                # 保存到历史记录
                if user_input:
                    self.history_manager.add_entry(user_input)
                
                return user_input
                
            except ImportError:
                # 如果没有prompt_toolkit，回退到标准input
                print("⚠️ 提示：安装 prompt_toolkit 可获得更好的输入体验：pip install prompt_toolkit")
                try:
                    user_input = input(prompt).strip()
                    if user_input:
                        self.history_manager.add_entry(user_input)
                    return user_input
                except KeyboardInterrupt:
                    print("\n👋 程序已中断，再见！")
                    sys.exit(0)
            except Exception as e:
                # 如果prompt_toolkit出错，回退到标准input
                print(f"⚠️ prompt_toolkit 出错，回退到标准输入: {e}")
                try:
                    user_input = input(prompt).strip()
                    if user_input:
                        self.history_manager.add_entry(user_input)
                    return user_input
                except KeyboardInterrupt:
                    print("\n👋 程序已中断，再见！")
                    sys.exit(0)
        else:
            # 非Windows系统使用简单的input
            try:
                user_input = input(prompt).strip()
                if user_input:
                    self.history_manager.add_entry(user_input)
                return user_input
            except KeyboardInterrupt:
                print("\n👋 程序已中断，再见！")
                sys.exit(0)
    
    def _execute_file_directly(self, user_input: str) -> bool:
        """
        直接执行可执行文件，实时显示输出并支持交互输入
        Args:
            user_input: 用户输入
        Returns:
            True if executed successfully, False otherwise
        """
        import subprocess
        import os
        import sys
        
        try:
            # 在Windows下，如果是Python文件，需要特殊处理
            if user_input.endswith('.py') or user_input.split()[0].endswith('.py'):
                # Python文件
                cmd = ['python', user_input]
            else:
                # 其他可执行文件
                cmd = user_input
            
            # 使用Popen启动进程，让进程继承当前终端，支持交互
            process = subprocess.Popen(
                cmd,
                shell=True,
                stdin=sys.stdin,      # 继承当前终端的输入
                stdout=sys.stdout,    # 继承当前终端的输出
                stderr=sys.stderr,    # 继承当前终端的错误输出
                cwd=str(self.work_directory)
            )
            
            # 等待进程结束
            return_code = process.wait()
            
            if return_code == 0:
                return True
            else:
                print(f"⚠️ 进程退出码: {return_code}")
                return False
                
        except Exception as e:
            print(f"❌ 执行文件失败: {e}")
            return False
