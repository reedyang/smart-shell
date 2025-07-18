#!/usr/bin/env python3
"""
文件管理AI Agent演示脚本
展示新增的两个功能：
1. 支持切换当前目录
2. 将命令输出结果传给大模型，辅助后续操作
"""

import os
import tempfile
from pathlib import Path
from file_manager_agent import FileManagerAgent

def create_demo_structure():
    """创建演示用的文件结构"""
    # 创建临时目录作为演示环境
    demo_dir = Path(tempfile.mkdtemp(prefix="file_manager_demo_"))
    
    # 创建文件和文件夹
    (demo_dir / "documents").mkdir()
    (demo_dir / "projects").mkdir()
    (demo_dir / "backup").mkdir()
    
    # 创建一些示例文件
    (demo_dir / "readme.txt").write_text("这是一个示例文件")
    (demo_dir / "old_document.docx").write_text("旧文档内容")
    (demo_dir / "temporary_file.tmp").write_text("临时文件")
    
    (demo_dir / "documents" / "report.pdf").write_text("报告内容")
    (demo_dir / "documents" / "presentation.pptx").write_text("演示文稿")
    
    (demo_dir / "projects" / "project1.py").write_text("print('Hello World')")
    (demo_dir / "projects" / "config.json").write_text('{"version": "1.0"}')
    
    print(f"📁 演示环境已创建: {demo_dir}")
    return demo_dir

def demo_directory_switching():
    """演示目录切换功能"""
    print("\n" + "="*60)
    print("🎯 演示功能1: 支持切换当前目录")
    print("="*60)
    
    demo_dir = create_demo_structure()
    
    # 创建AI Agent并设置工作目录
    agent = FileManagerAgent(model_name="gemma3:4b", work_directory=str(demo_dir))
    
    print("\n📋 演示场景：")
    print("1. 查看当前目录内容")
    print("2. 切换到子目录")
    print("3. 在子目录中进行操作")
    print("4. 返回上级目录")
    
    # 模拟AI交互
    test_commands = [
        {"action": "list", "params": {}},
        {"action": "cd", "params": {"path": "documents"}},
        {"action": "list", "params": {}},
        {"action": "cd", "params": {"path": ".."}},
        {"action": "list", "params": {}},
    ]
    
    for i, command in enumerate(test_commands, 1):
        print(f"\n🔄 步骤 {i}: {command}")
        result = agent.execute_command(command)
        print(f"📊 结果: {result.get('message', result)}")
    
    return agent

def demo_result_feedback():
    """演示将操作结果传递给大模型的功能"""
    print("\n" + "="*60)
    print("🎯 演示功能2: 将命令输出结果传给大模型")
    print("="*60)
    
    demo_dir = create_demo_structure()
    agent = FileManagerAgent(model_name="gemma3:4b", work_directory=str(demo_dir))
    
    print("\n📋 演示场景：")
    print("1. 列出目录内容")
    print("2. AI根据目录内容提供建议")
    print("3. 执行AI建议的操作")
    print("4. AI根据操作结果提供进一步建议")
    
    # 模拟用户请求
    user_requests = [
        "显示当前目录的文件",
        "帮我整理一下这些文件",
        "把临时文件删除掉",
    ]
    
    for i, request in enumerate(user_requests, 1):
        print(f"\n🗣️ 用户请求 {i}: {request}")
        
        # 获取AI回复
        ai_response = agent.call_ollama(request)
        print(f"🤖 AI回复: {ai_response}")
        
        # 提取并执行命令
        command = agent.extract_json_command(ai_response)
        if command:
            print(f"⚡ 执行命令: {command}")
            result = agent.execute_command(command)
            
            # 保存操作结果
            agent.operation_results.append({
                "command": command,
                "result": result,
                "timestamp": "demo_time"
            })
            
            # 简化建议，避免CPU过载
            if result.get("success"):
                print(f"💡 提示: 操作已完成，您可以继续其他文件管理操作")
    
    return agent

def interactive_demo():
    """交互式演示"""
    print("\n" + "="*60)
    print("🎮 交互式演示")
    print("="*60)
    
    demo_dir = create_demo_structure()
    agent = FileManagerAgent(model_name="gemma3:4b", work_directory=str(demo_dir))
    
    print(f"\n📁 演示环境: {demo_dir}")
    print("💡 试试这些命令：")
    print("  - 显示当前目录文件")
    print("  - 切换到 documents 目录")
    print("  - 重命名 old_document.docx 为 new_document.docx")
    print("  - 创建一个新文件夹")
    print("  - 删除临时文件")
    print("  - 输入 'demo_exit' 退出演示")
    
    while True:
        try:
            # 显示完整路径
            user_input = input(f"\n👤 您 [{str(agent.work_directory)}]: ").strip()
            
            if user_input.lower() in ['demo_exit', 'exit']:
                print("👋 演示结束！")
                break
            
            if not user_input:
                continue
            
            # 获取AI回复
            print("🤖 AI正在思考...")
            ai_response = agent.call_ollama(user_input)
            print(f"🤖 AI: {ai_response}")
            
            # 提取并执行命令
            command = agent.extract_json_command(ai_response)
            if command:
                print("\n⚡ 执行操作...")
                result = agent.execute_command(command)
                
                # 保存操作结果
                agent.operation_results.append({
                    "command": command,
                    "result": result,
                    "timestamp": "demo_time"
                })
                
                # 简化建议，避免CPU过载
                if result.get("success"):
                    print(f"💡 提示: 操作已完成，您可以继续其他文件管理操作")
                        
        except KeyboardInterrupt:
            print("\n👋 演示已中断！")
            break
        except Exception as e:
            print(f"❌ 演示中发生错误: {str(e)}")

def main():
    """主函数"""
    print("🚀 文件管理AI Agent功能演示")
    print("展示两个新功能：")
    print("1. 支持切换当前目录")
    print("2. 将命令输出结果传给大模型，辅助后续操作")
    
    try:
        import ollama
        # 检查Ollama连接
        models = ollama.list()
        # 更安全的方式获取模型名称
        model_names = []
        for model in models.get('models', []):
            if hasattr(model, 'model'):  # 新版本ollama可能有model属性
                model_names.append(model.model)
            elif isinstance(model, dict):
                model_names.append(model.get('name', model.get('model', 'unknown')))
            else:
                # 如果是字符串，直接使用
                model_names.append(str(model))
        print(f"✅ Ollama连接正常，可用模型: {model_names}")
        
        # 演示目录切换功能
        demo_directory_switching()
        
        # 演示结果反馈功能
        demo_result_feedback()
        
        # 交互式演示
        print("\n🎮 现在您可以进行交互式体验...")
        interactive_demo()
        
    except ImportError:
        print("❌ 请先安装 ollama 包: pip install ollama")
    except Exception as e:
        print(f"❌ 无法连接到Ollama: {e}")
        print("请确保Ollama服务正在运行")

if __name__ == "__main__":
    main() 