# Qwen2API

通义千问 API 的Python版本实现，基于FastAPI和httpx。

> [!NOTE]  
> 现已支持前端管理，访问 **/static** 页面即可查看。

> [!IMPORTANT]  
> 请将原本的配置文件 **accounts.yml** 和 **config.yaml** 从主目录移到到 **config** 目录下

> [!IMPORTANT]  
> 数据已移动至 **data** 目录下存储，包括
> - model.json 模型配置文件
> - upload.json 缓存的图片 SHA256 URL 对应关系

## 功能特点

- [X] 支持通义千问全部模型
- [X] 支持流式输出
- [X] 支持思考过程显示
- [X] 支持搜索功能
- [X] 支持图像生成
- [X] 支持视频生成
- [X] 支持多账户轮询调度
- [X] 支持缓存上传图片URL，无需等待过久
- [X] 前端管理
- [X] Docker镜像支持（部分）

## 环境要求

- Python 3.7+
- FastAPI
- Uvicorn
- httpx
- python-multipart

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置文件

> [!IMPORTANT]  
> 配置文件现在不会自动生成。
> 请复制 config.yaml.example 去除 example 后缀，并修改，得到你的配置文件 config.yaml ，**放入 config 文件夹中**

### 3. 启动服务

```bash
python run.py
```
## Docker 命令
```
docker build -t qwen2api .
docker run -d \
  --name qwen2api \
  -v $(pwd)/config:/qwen2api/config \
  -v $(pwd)/data:/qwen2api/data \
  -v $(pwd)/logs:/qwen2api/logs \
   -p 2778:2778 \
   qwen2api:latest 
```
## API接口

提供与 OpenAI 兼容的接口

## 高级功能

### 思考过程

在模型名称后添加`-thinking`后缀，例如：`qwen-max-latest-thinking`。

### 网络搜索

在模型名称后添加`-search`后缀，例如：`qwen-max-latest-search`。

### 套娃

在模型名称后添加`-thinking-search`后缀，例如：`qwen-max-latest-thinking-search`。

### 图像生成

在模型名称后添加`-draw`后缀，例如：`qwen-max-latest-draw`。

### 视频生成

在模型名称后添加`-video`后缀，例如：`qwen-max-latest-video`。
（注意Cherry Studio无法正常显示🫥）


## 免责声明

本项目仅供学习和研究使用，不构成任何商业用途。使用本项目所产生的任何直接或间接的法律责任由使用者自行承担。本项目不对使用者的任何行为负责。

## 许可证

MIT License

#### 自用
> 导出依赖 
>```bash
>pipdeptree --warn silence | Select-String -Pattern '^\w+' > .\requirements.txt
>```