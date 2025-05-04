# 使用官方 Python 镜像作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Shanghai

# 安装系统依赖
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY requirements.txt .
COPY config.yaml.example config.yaml
COPY accounts.yml.example accounts.yml
COPY app/ app/
COPY run.py .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 创建日志目录
RUN mkdir -p logs && chmod 777 logs

# 暴露端口（根据实际配置修改）
EXPOSE 8000

# 启动命令
CMD ["python", "run.py"] 