#!/usr/bin/env python3
"""
文件管理AI Agent直接启动脚本
在agent目录中运行，避免导入路径问题
"""

import sys
from pathlib import Path

def main():
    """主函数"""
    print("🚀 启动文件管理AI Agent...")
    
    # 指定使用的模型
    model_name = "gemma3:4b"
    
    # 处理命令行参数
    work_directory = None
    if len(sys.argv) > 1:
        work_directory = sys.argv[1]
        if not Path(work_directory).exists():
            print(f"❌ 指定的目录不存在: {work_directory}")
            return 1
    
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
                print(f"💡 可以使用: {available_models[0]}")
                print(f"💡 建议运行: ollama pull {model_name}")
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
        from file_manager_agent import FileManagerAgent
        
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