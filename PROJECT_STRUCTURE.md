# 项目结构说明

## 目录结构
```
ds/
├── agent/                          # AI Agent核心模块
│   ├── __init__.py                # 包初始化文件
│   ├── file_manager_agent.py      # 主要的AI Agent实现
│   ├── demo_file_manager.py       # 功能演示脚本
│   ├── test_new_features.py       # 新功能测试脚本
│   └── README_file_manager.md     # 详细使用说明
├── run_agent.py                   # 主启动脚本
├── run_demo.py                    # 演示启动脚本
└── deepseek_python.py            # DeepSeek Python示例
```

## 使用方法

### 1. 运行AI Agent
```bash
python run_agent.py                    # 在当前目录运行
python run_agent.py /path/to/directory # 在指定目录运行
```

### 2. 运行演示
```bash
python run_demo.py
```

### 3. 直接运行（在agent目录中）
```bash
cd agent
python file_manager_agent.py          # 运行主程序
python demo_file_manager.py           # 运行演示
python test_new_features.py           # 运行测试
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