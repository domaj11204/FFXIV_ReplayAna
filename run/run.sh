#!/bin/bash
# run.sh - 啟動 FFXIV Wipe Analyzer 雙容器服務 (Linux/Mini-PC 專用)

# 1. 設定鏡像名稱 (使用當前最新的穩定版本 v0.0.9)
IMAGE_NAME="ghcr.io/domaj11204/ffxiv_replayana:latest"

echo "正在從 GHCR 拉取最新 Docker 鏡像..."
docker pull ${IMAGE_NAME}

# 2. 停止並刪除已存在的容器
if [ "$(docker ps -aq -f name=ffxiv-analyzer-web)" ]; then
  echo "停止並移除舊的 ffxiv-analyzer-web 容器..."
  docker stop ffxiv-analyzer-web
  docker rm ffxiv-analyzer-web
fi

if [ "$(docker ps -aq -f name=ffxiv-discord-bot)" ]; then
  echo "停止並移除舊的 ffxiv-discord-bot 容器..."
  docker stop ffxiv-discord-bot
  docker rm ffxiv-discord-bot
fi

# 3. 確保本地 cookie 檔案存在，以利雙向掛載同步
touch cookies.txt
touch www.youtube.com_cookies.txt
COOKIE_MOUNT="-v $(pwd)/cookies.txt:/app/cookies.txt -v $(pwd)/www.youtube.com_cookies.txt:/app/www.youtube.com_cookies.txt"

# 4. 啟動 Web UI & API 服務容器 (使用主機網路模式)
echo "正在啟動 Web UI & API 容器..."
docker run -d \
  --name ffxiv-analyzer-web \
  --restart unless-stopped \
  --network host \
  --env-file .env \
  $COOKIE_MOUNT \
  ${IMAGE_NAME}

# 5. 啟動 Discord Bot 容器 (使用主機網路模式，覆蓋 Entrypoint 並掛載 Cookie 檔案)
echo "正在啟動 Discord Bot 容器..."
docker run -d \
  --name ffxiv-discord-bot \
  --restart unless-stopped \
  --network host \
  --env-file .env \
  $COOKIE_MOUNT \
  ${IMAGE_NAME} \
  python discord_bot.py

# 6. 清除過期的虛擬映像檔以釋放硬碟空間
docker image prune -f

echo "=========================================================="
echo "✅ 雙容器已成功於 Mini-PC 地端啟動！"
echo "Web UI 網址：http://localhost:8080  或  http://[Mini-PC_IP]:8080"
echo "使用 'docker logs -f ffxiv-analyzer-web' 查看分析進度與日誌。"
echo "=========================================================="
