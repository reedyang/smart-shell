#!/usr/bin/env python3
"""
文件管理AI Agent主启动脚本

用法：
    python run_agent.py       # 使用默认AI模型
    python run_agent.py model # 使用指定的AI模型
"""

import sys
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
    
    # 指定使用的模型
    model_name = "gemma3:4b"
    
    # 处理命令行参数
    if len(sys.argv) > 1:
        model_name = sys.argv[1]
    
    # 检查Ollama是否可用
    try:
        import ollama
        models = ollama.list()
        # 更安全的方式获取模型名称
        available_models = []
        for model in models.get('models', []):
            if hasattr(model, 'model'):  # 新版本ollama可能有model属性
                available_models.append(model.model)
            elif isinstance(model, dict):
                available_models.append(model.get('name', model.get('model', 'unknown')))
            else:
                # 如果是字符串，直接使用
                available_models.append(str(model))
        print(f"📋 可用模型: {available_models}")
        
        # 检查指定模型是否可用
        if model_name not in available_models:
            print(f"⚠️ 指定模型 {model_name} 不可用")
            if available_models:
                model_name = available_models[0]  # 使用第一个可用模型
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
    
    # 创建并运行AI Agent
    try:
        agent = FileManagerAgent(
            model_name=model_name,
            work_directory=work_directory
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