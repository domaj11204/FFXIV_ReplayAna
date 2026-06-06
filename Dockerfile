# 使用官方 Python 輕量鏡像
FROM python:3.12-slim

# 設定環境變數
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    UV_SYSTEM_PYTHON=1 \
    PATH="/app/.venv/bin:$PATH"

# 安裝系統依賴：ffmpeg 以及 OpenCV 所需的共享庫 (libgl1-mesa-glx, libglib2.0-0)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 從官方鏡像拷貝 uv 執行檔，用於超快速的套件安裝
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# 設定工作目錄
WORKDIR /app

# 先拷貝專案定義與鎖定檔，快取套件安裝步驟
COPY pyproject.toml uv.lock README.md /app/

# 在系統環境中同步安裝依賴套件（Cloud Run 不需要虛擬環境，直接安裝於系統可簡化指令與容器大小）
RUN uv sync --no-dev --no-install-project

# 拷貝核心程式碼與預設的 RESTART 模板圖片
COPY main.py restart_template.png /app/

# 暴露埠號 (Cloud Run 會自動映射 PORT 環境變數，預設為 8080)
EXPOSE 8080

# 啟動 FastAPI 服務，使用環境變數中的 PORT
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT}
