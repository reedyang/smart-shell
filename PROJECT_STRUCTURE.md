# 项目结构说明

## 目录结构
```
ds/
├── agent/                          # AI Agent核心模块
│   ├── __init__.py                # 包初始化文件
│   ├── file_manager_agent.py      # 主要的AI Agent实现
│   ├── demo_file_manager.py       # 功能演示脚本
└── main.py                        # 主启动脚本
```

## 使用方法

### 1. 运行AI Agent
```bash
python main.py       # 使用默认AI模型
python main.py model # 使用指定的AI模型
```

## 新功能特性

### 🔀 目录切换功能
- 支持相对路径和绝对路径切换
- 智能路径验证
- 动态提示符显示当前目录

### 🧠 操作结果反馈
- 记录所有操作结果
- 将结果传递给AI分析
- 提供基于结果的智能建议
- 支持上下文理解

## 依赖要求
- Python 3.7+
- ollama Python包
- 本地Ollama服务运行
- 可用的语言模型（如gemma3:4b）

## 安装依赖
```bash
pip install ollama
```

## 启动Ollama服务
```bash
ollama serve
```

## 下载模型
```bash
ollama pull gemma3:4b
``` 