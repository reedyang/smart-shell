#!/usr/bin/env python3
"""
文件管理AI Agent主启动脚本

用法：
    python main.py       # 使用默认AI模型
    python main.py model # 使用指定的AI模型
"""

import sys
import json
import os
from pathlib import Path

# 添加agent目录到Python路径
current_dir = Path(__file__).parent
agent_dir = current_dir / "agent"
sys.path.insert(0, str(agent_dir))

from agent.file_manager_agent import FileManagerAgent

def main():
    """主函数"""
    print("🚀 启动文件管理AI Agent...")
    
    work_directory = None
    # 命令行参数优先，若有参数则直接用为ollama模型并忽略配置文件
    if len(sys.argv) > 1:
        model_name = sys.argv[1]
        provider = "ollama"
        params = None
        config = None
    else:
        config = None
        config_path = None
        # 优先查找用户主目录下的llm-filemgr.json
        user_home = str(Path.home())
        user_config = os.path.join(user_home, "llm-filemgr.json")
        local_config = os.path.join(current_dir, "llm-filemgr.json")
        if os.path.exists(user_config):
            config_path = user_config
        elif os.path.exists(local_config):
            config_path = local_config
        if config_path:
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except Exception as e:
                print(f"⚠️ 配置文件读取失败: {e}")
                config = None
        # 默认模型
        model_name = "gemma3:4b"
        provider = "ollama"
        params = None
        if config:
            provider = config.get("provider", "ollama").lower()
            params = config.get("params")
            if provider in ("openai", "openwebui") and params:
                model_name = params.get("model", "gpt-3.5-turbo")
            elif provider == "ollama":
                pass

    # 选择模型提供方
    if provider == "openai" and params:
        print(f"🤖 使用OpenAI API: {params.get('base_url', 'https://api.openai.com/v1')} 模型: {model_name}")
        try:
            agent = FileManagerAgent(
                model_name=model_name,
                work_directory=work_directory,
                provider="openai",
                params=params
            )
            agent.run()
            return 0
        except Exception as e:
            print(f"❌ OpenAI API模式运行错误: {str(e)}")
            return 1
    elif provider == "openwebui" and params:
        print(f"🤖 使用OpenWebUI API: {params.get('base_url', 'http://localhost:8080/v1')} 模型: {model_name}")
        try:
            agent = FileManagerAgent(
                model_name=model_name,
                work_directory=work_directory,
                provider="openwebui",
                params=params
            )
            agent.run()
            return 0
        except Exception as e:
            print(f"❌ OpenWebUI API模式运行错误: {str(e)}")
            return 1
    else:
        # 默认ollama本地
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
            print(f"📋 可用模型: {available_models}")
            if model_name not in available_models:
                print(f"⚠️ 指定模型 {model_name} 不可用")
                if available_models:
                    model_name = available_models[0]
                    print(f"💡 使用默认模型: {model_name}")
                else:
                    print("❌ 没有可用的模型")
                    return 1
        except ImportError:
            print("❌ 请先安装 ollama 包: pip install ollama")
            return 1
        except Exception as e:
            print(f"❌ 无法连接到Ollama: {str(e)}")
            print("请确保Ollama服务正在运行")
            return 1
        try:
            agent = FileManagerAgent(
                model_name=model_name,
                work_directory=work_directory,
                provider="ollama"
            )
            agent.run()
            return 0
        except KeyboardInterrupt:
            print("\n👋 程序已退出")
            return 0
        except Exception as e:
            print(f"❌ 运行错误: {str(e)}")
            return 1

if __name__ == "__main__":
    sys.exit(main()) 