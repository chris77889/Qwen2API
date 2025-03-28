# Qwen2API

通义千问 API 的Python版本实现，基于FastAPI和httpx，提供与原JavaScript版本相同的功能。

## 功能特点

- 支持通义千问全部模型
- 支持流式输出
- 支持思考过程显示
- 支持搜索功能
- 支持图像生成
- 支持多账户轮询调度

## 环境要求

- Python 3.7+
- FastAPI
- Uvicorn
- httpx
- python-multipart

## 快速开始

### 1. 安装依赖

> 导出依赖 
>```bash
>pipdeptree --warn silence | Select-String -Pattern '^\w+' > .\requirements.txt
>```

```bash
pip install -r requirements.txt
```

### 2. 配置文件

配置文件在第一次启动会自动生成。

### 3. 启动服务

```bash
python run.py
```

## API接口

提供与 OpenAI 兼容的接口

## 高级功能

### 思考过程

在模型名称后添加`-thinking`后缀，例如：`qwen-max-latest-thinking`。

### 网络搜索

在模型名称后添加`-search`后缀，例如：`qwen-max-latest-search`。

### 图像生成

在模型名称后添加`-draw`后缀，例如：`qwen-max-latest-draw`。


## 免责声明

本项目仅供学习和研究使用，不构成任何商业用途。使用本项目所产生的任何直接或间接的法律责任由使用者自行承担。本项目不对使用者的任何行为负责。

## 许可证

MIT License