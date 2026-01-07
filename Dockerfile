FROM python:3.11-slim

WORKDIR /app


# 复制依赖文件（使用事先下载好的 Linux 版离线包）
COPY requirements.txt .
COPY python_packages_linux /app/python_packages

# 安装Python依赖
ENV http_proxy=""
ENV https_proxy=""
ENV no_proxy="*"
RUN pip install --no-cache-dir --no-index --find-links=/app/python_packages -r requirements.txt

# 复制应用代码
COPY . .

# 暴露端口
EXPOSE 8080

# 健康检查 - 由 docker-compose.yml 管理，这里不再配置
# HEALTHCHECK 配置已移至 docker-compose.yml

# 启动应用
CMD ["python", "main.py"]
