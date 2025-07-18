#!/usr/bin/env python3
"""
文件管理AI Agent演示启动脚本
"""

import sys
import os
from pathlib import Path

# 添加agent目录到Python路径
current_dir = Path(__file__).parent
agent_dir = current_dir / "agent"
sys.path.insert(0, str(agent_dir))

def main():
    """主函数"""
    print("🚀 启动文件管理AI Agent演示...")
    
    try:
        # 导入演示模块
        from agent.demo_file_manager import main as demo_main
        demo_main()
        
    except ImportError as e:
        print(f"❌ 导入错误: {e}")
        print("请确保agent目录中的文件完整")
        return 1
    except Exception as e:
        print(f"❌ 运行错误: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 