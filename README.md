# 文件管理AI Agent使用说明
#
# 支持本地Ollama模型、OpenAI API、OpenWebUI API三种大模型接入方式。


## 概述
这是一个基于本地Ollama大模型的AI文件管理助手，可以通过自然语言与用户交互，执行各种文件管理操作。

## 功能特性

### 🎯 核心功能
- 📁 **列出目录内容** - 查看文件和文件夹
- 🔄 **文件重命名** - 重命名文件和文件夹
- 📦 **文件移动** - 移动文件到其他位置
- 🗑️ **文件删除** - 安全删除文件和文件夹
- 📂 **创建文件夹** - 创建新的目录
- 📋 **文件信息** - 查看文件详细信息
- 🔀 **目录切换** - 切换当前工作目录
- 🎬 **转换媒体文件** - 调用ffmpeg命令转换媒体文件格式
- 🧠 **智能建议** - 基于操作结果提供后续建议

### 🛡️ 安全特性
- 删除操作需要确认
- 防止操作系统重要文件
- 重命名时检查文件冲突
- 工作目录限制

## 安装依赖

### 1. 安装Ollama
```bash
# 访问 https://ollama.ai 下载并安装Ollama
# 或者使用包管理器安装
```

### 2. 安装Python依赖
```bash
pip install ollama
```

### 3. 下载模型
```bash
# 下载推荐的模型
ollama pull gemma3:4b

# 或者下载其他模型
ollama pull qwen3:1.7b
ollama pull llama3.1
ollama pull mistral
```

## 使用方法

### 启动Agent
```bash
python file_manager_agent.py
```

### 对话示例

#### 1. 列出目录内容
```
👤 您: 显示当前目录的文件
👤 您: 列出文件夹内容
👤 您: 查看这个目录里有什么
```

#### 2. 重命名文件
```
👤 您: 把 old_file.txt 重命名为 new_file.txt
👤 您: 重命名文件夹 old_folder 为 new_folder
👤 您: 将 document.docx 改名为 报告.docx
```

#### 3. 移动文件
```
👤 您: 把 file.txt 移动到 ../backup/ 目录
👤 您: 将所有图片移动到 images 文件夹
```

#### 4. 删除文件
```
👤 您: 删除 temporary.txt
👤 您: 清理 temp 文件夹
```

#### 5. 创建文件夹
```
👤 您: 创建一个名为 projects 的文件夹
👤 您: 新建目录 backup
```

#### 6. 查看文件信息
```
👤 您: 查看 document.pdf 的详细信息
👤 您: 显示 image.jpg 的属性
```

#### 7. 切换目录
```
👤 您: 切换到 documents 目录
👤 您: 进入 projects 文件夹
👤 您: 返回上级目录
👤 您: 切换到 /home/user/Downloads
```

#### 8. 智能建议
```
👤 您: 显示当前目录文件
🤖 AI: 我看到您有很多临时文件，建议整理一下
👤 您: 帮我整理这些文件
🤖 AI: 建议创建一个临时文件夹并移动相关文件
```

## 配置选项

### 使用外部大模型（OpenAI API 或 OpenWebUI API）

你可以通过在用户主目录或源码根目录下新建 `llm-filemgr.json` 配置文件，指定大模型服务：

```json
{
  "provider": "openai", // 可选值: ollama, openai, openwebui
  "params": {
    "api_key": "sk-xxx",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-3.5-turbo"
  }
}
```

> ⚠️ JSON标准不允许注释，实际文件请去掉注释行。

配置说明：
- `provider`：指定使用哪个大模型服务。`ollama`为本地模型，`openai`为OpenAI官方API，`openwebui`为OpenWebUI API。
- `params`：填写对应API的key、base_url和模型名。
- 若无此文件或provider为ollama，则默认使用本地ollama。

#### 示例：使用OpenAI API
```json
{
  "provider": "openai",
  "params": {
    "api_key": "sk-xxx",
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o"
  }
}
```

#### 示例：使用OpenWebUI API
```json
{
  "provider": "openwebui",
  "params": {
    "api_key": "your-key",
    "base_url": "http://localhost:8080/v1",
    "model": "your-model"
  }
}
```
#### 示例：使用局域网其它设备上部署的Ollama模型
{
  "provider": "openai",
  "params": {
    "api_key": "",
    "base_url": "http://<ip address>:11434/v1",
    "model": "gemma3:4b"
  }
}

配置文件查找顺序：
1. 用户主目录（如 `C:/Users/你的用户名/llm-filemgr.json`）
2. 源码根目录
3. 未找到则默认本地ollama

如需切换回本地ollama，只需删除或重命名配置文件，或将provider设为`ollama`。

### 修改模型
```python
# 在 file_manager_agent.py 中修改
agent = FileManagerAgent(model_name="gemma3:4b")
```

### 修改工作目录
```python
# 指定特定的工作目录
agent = FileManagerAgent(work_directory="/path/to/your/directory")
```

## AI指令格式

AI Agent会在回复中包含JSON格式的操作指令：

```json
{
    "action": "操作类型",
    "params": {
        "参数名": "参数值"
    }
}
```

### 支持的操作类型

| 操作类型 | 参数 | 说明 |
|---------|------|------|
| `list` | `path` (可选) | 列出目录内容 |
| `rename` | `old_name`, `new_name` | 重命名文件/文件夹 |
| `move` | `source`, `destination` | 移动文件/文件夹 |
| `delete` | `file_name`, `confirmed` | 删除文件/文件夹 |
| `mkdir` | `dir_name` | 创建新文件夹 |
| `info` | `file_name` | 查看文件信息 |
| `cd` | `path` | 切换当前目录 |
| `convert` | `source`, `target`,  `options`(可选) | 转换媒体文件格式 |

## 故障排除

### 1. 无法连接到Ollama
```bash
# 检查Ollama是否运行
ollama list

# 启动Ollama服务
ollama serve
```

### 2. 模型不存在
```bash
# 查看已安装的模型
ollama list

# 下载所需模型
ollama pull gemma3:4b
```

### 3. 权限错误
- 确保对工作目录有读写权限
- 不要在系统目录中运行

## 注意事项

### ⚠️ 安全提醒
1. 首次使用时建议在测试目录中运行
2. 删除操作不可逆，请谨慎操作
3. 不要在系统重要目录中使用
4. 定期备份重要文件

### 💡 使用技巧
1. 使用自然语言描述您的需求
2. 可以一次性描述多个操作
3. 支持中文和英文对话
4. 如果AI理解有误，可以重新描述

## 新功能详解

### 🔀 目录切换功能
AI Agent现在支持智能目录切换，可以：
- 切换到子目录：`cd documents`
- 返回上级目录：`cd ..`
- 切换到绝对路径：`cd /home/user/projects`
- 当前目录显示：提示符会显示当前目录名

### 🧠 操作结果反馈
AI Agent会：
- 记录每次操作的结果
- 将操作结果传递给大模型进行分析
- 基于操作结果提供智能建议
- 支持连续操作的上下文理解

### 示例工作流
```
👤 您: 显示当前目录文件
🤖 AI: 执行 list 命令...
📁 显示文件列表
💡 AI建议: 我看到有很多临时文件，建议整理一下

👤 您: 帮我整理临时文件
🤖 AI: 我建议创建一个 temp 文件夹并移动临时文件
⚡ 执行创建文件夹和移动操作...
💡 AI建议: 文件已整理完成，您可以定期清理 temp 文件夹
```

## 演示脚本

### 运行演示
```bash
python run_agent.py
```
![Convert media demo](demo/convert_media.png "Convert media demo")

## 许可证
MIT License