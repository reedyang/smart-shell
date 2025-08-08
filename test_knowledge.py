#!/usr/bin/env python3
"""
知识库功能测试脚本
"""

import sys
import os
from pathlib import Path

# 添加agent目录到Python路径
current_dir = Path(__file__).parent
agent_dir = current_dir / "agent"
sys.path.insert(0, str(agent_dir))

def test_knowledge_base():
    """测试知识库功能"""
    print("🧪 开始测试知识库功能...")
    
    try:
        # 测试导入
        from knowledge_manager import KnowledgeManager, KNOWLEDGE_AVAILABLE
        
        if not KNOWLEDGE_AVAILABLE:
            print("❌ 知识库功能不可用，缺少依赖")
            print("💡 请运行: pip install chromadb langchain sentence-transformers")
            return False
        
        # 创建测试配置目录
        test_config_dir = Path(".test_smartshell")
        test_config_dir.mkdir(exist_ok=True)
        
        # 创建测试知识库目录
        test_knowledge_dir = test_config_dir / "knowledge"
        test_knowledge_dir.mkdir(exist_ok=True)
        
        # 创建测试文档
        test_doc = test_knowledge_dir / "test_document.txt"
        with open(test_doc, 'w', encoding='utf-8') as f:
            f.write("这是一个测试文档。\n")
            f.write("Smart Shell 是一个智能的命令行工具。\n")
            f.write("它支持自然语言指令和文件管理功能。\n")
            f.write("知识库功能可以自动索引文档并提供智能检索。\n")
        
        print("✅ 测试文档创建成功")
        
        # 初始化知识库管理器
        try:
            km = KnowledgeManager(str(test_config_dir), "nomic-embed-text")
            print("✅ 知识库管理器初始化成功")
        except Exception as e:
            print(f"❌ 知识库管理器初始化失败: {e}")
            print("💡 请确保Ollama服务正在运行，并已安装nomic-embed-text模型")
            return False
        
        # 测试同步
        try:
            km.sync_knowledge_base()
            print("✅ 知识库同步成功")
        except Exception as e:
            print(f"❌ 知识库同步失败: {e}")
            return False
        
        # 测试搜索
        try:
            results = km.search_knowledge("Smart Shell", top_k=3)
            if results:
                print("✅ 知识库搜索成功")
                print(f"📊 找到 {len(results)} 个相关结果")
            else:
                print("⚠️ 知识库搜索未返回结果")
        except Exception as e:
            print(f"❌ 知识库搜索失败: {e}")
            return False
        
        # 测试统计信息
        try:
            stats = km.get_knowledge_stats()
            if stats:
                print("✅ 知识库统计信息获取成功")
                print(f"📄 文档数: {stats.get('total_documents', 0)}")
                print(f"📝 片段数: {stats.get('total_chunks', 0)}")
            else:
                print("⚠️ 知识库统计信息获取失败")
        except Exception as e:
            print(f"❌ 知识库统计信息获取失败: {e}")
            return False
        
        # 清理测试文件
        import shutil
        import time
        time.sleep(2)  # 等待数据库连接关闭
        try:
            shutil.rmtree(test_config_dir)
            print("✅ 测试文件清理完成")
        except Exception as e:
            print(f"⚠️ 测试文件清理失败: {e}")
            print("💡 请手动删除 .test_smartshell 目录")
        
        print("🎉 知识库功能测试完成！")
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("💡 请确保已安装所有依赖包")
        return False
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        return False

if __name__ == "__main__":
    success = test_knowledge_base()
    sys.exit(0 if success else 1)
