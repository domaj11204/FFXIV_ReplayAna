# FFXIV Wipe Analyzer (FFXIV 副本滅團時間軸產生器)

基於 Python FastAPI 與 FFmpeg 的影像分析服務。分析 FFXIV 戰鬥影片（如 YouTube），自動辨識滅團 (Wipe) 時間點並輸出 JSON 時間軸。

## 核心特色

1. **雙階段高效分析 (Map-Reduce Style)**:
   * 階段一：以 FFmpeg `blackdetect` 快速偵測 3~12 秒黑屏（使用 `fps=2` 降採樣，速度達 50x~60x）。
   * 階段二：僅針對黑屏後 30 秒窗口比對 `RESTART` 字樣，節省頻寬與運算資源。
2. **實況畫面相容**：自動裁切中央區域，避開四周的視訊鏡頭與聊天室 UI。
3. **金色遮罩匹配 (Mask-Based Matching)**：利用 HSV 色域提取金色文字遮罩進行模板比對，忽略動態戰鬥背景與特效，確保精準度。

---

## 本地開發與測試

使用 `uv` 進行專案與依賴管理。

### 1. 啟動 API 服務
```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 2. 執行測試
* [test_api.py](test_api.py)：測試完整分析。
* [test_first_11m.py](test_first_11m.py)：僅分析前 11 分鐘以利快速驗證。
```bash
uv run python test_first_11m.py
```

---

## Google Cloud Build 與 GCS 整合部署 (Cloud Run)

專案配置為私有部署。敏感的 YouTube `cookies.txt` 與 RESTART 模板圖片存放於 Google Cloud Storage (GCS) 中，供 Cloud Run 執行時動態下載。

### 1. 建立 GCS Bucket 並上傳資源
```bash
# 建立 Bucket
gcloud storage buckets create gs://inspiring-bee-481116-m0-ffxiv-assets --location=asia-east1 --project="inspiring-bee-481116-m0"

# 上傳設定檔與模板
gcloud storage cp cookies.txt gs://inspiring-bee-481116-m0-ffxiv-assets/
gcloud storage cp restart_template.png gs://inspiring-bee-481116-m0-ffxiv-assets/
```

### 2. 部署至 Cloud Run (綁定 GCS Bucket)
```bash
gcloud run deploy ffxiv-replay-ana \
  --source . \
  --region asia-east1 \
  --no-allow-unauthenticated \
  --service-account="antigravity@inspiring-bee-481116-m0.iam.gserviceaccount.com" \
  --project="inspiring-bee-481116-m0" \
  --set-env-vars GCS_BUCKET_NAME="inspiring-bee-481116-m0-ffxiv-assets" \
  --quiet
```

### 3. 啟動 Discord Bot (本地)
```bash
uv run python discord_bot.py
```

### 4. Bot 指令參數
Discord 指令 `/analyze` 參數：
- `youtube_url` (必填)：影片網址
- `threshold` (選填)：比對相似度閾值 (預設 0.65)
- `x_min` / `x_max` / `y_min` / `y_max` (選填)：中央偵測區裁切比例
- `scan_duration_limit` (選填)：限制分析影片前 N 秒 (預設 0.0 表示分析整部)

---

## 三種建置與部署版本指南

### 1. 模式一：Cloud Run 全雲端版
適用於 24 小時在線且免用本地硬體資源的情境。

* **部署指令**：
  ```bash
  gcloud run deploy ffxiv-replay-ana \
    --image asia-east1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/ffxiv-replay-ana:latest \
    --region asia-east1 \
    --set-env-vars GCS_BUCKET_NAME="YOUR_BUCKET"
  ```

### 2. 模式二：獨立 HTTP-Server (支援 IPv6 雙棧 + Web UI)
適用於本地 Ubuntu、NAS 等環境運行，內建網頁介面。

* **特色**：
  * 內建網頁 UI：包含輸入框、動態分析進度與一鍵複製按鈕。
  * IPv6 雙棧支援：Uvicorn 綁定 `::`，同時監聽 IPv6 與 IPv4。
* **啟動方式 A (使用 GCS)**：
  ```bash
  docker run -d -p 8080:8080 \
    -e GCS_BUCKET_NAME="YOUR_BUCKET" \
    -e GOOGLE_APPLICATION_CREDENTIALS="/app/key.json" \
    -v $(pwd)/key.json:/app/key.json \
    --name ffxiv-analyzer-web \
    ffxiv-replay-ana
  ```
* **啟動方式 B (純本地獨立模式)**：
  ```bash
  docker run -d -p 8080:8080 \
    -v $(pwd)/cookies.txt:/app/cookies.txt \
    -v $(pwd)/restart_template.png:/app/restart_template.png \
    --name ffxiv-analyzer-web \
    ffxiv-replay-ana
  ```
* **使用方式**：瀏覽器開啟 `http://[YOUR_IPV6_ADDRESS]:8080/` 或 `http://localhost:8080/`。

### 3. 模式三：Discord User-Installable App (個人帳號安裝版)
適用於非伺服器管理員，或希望在任何伺服器與私訊中使用 Bot 的情境。

* **特色**：安裝於個人帳號，可在任何伺服器或私訊中呼叫 `/analyze`，不干擾他人。
* **配置步驟**：
  1. 至 [Discord Developer Portal](https://discord.com/developers/applications) 選擇 Bot，進入 **Installation** 面板。
  2. **Installation Contexts** 勾選 **User Install**。
  3. **Default Install Settings** 的 Scopes 加入 `applications.commands`。
  4. 分享下方的 **Install Link**，引導使用者完成「新增至我的應用程式 (Add to My Apps)」安裝。

---

## CI/CD 自動化管道說明

專案於 `.github/workflows/` 配置 GitHub Actions，支援代碼推送後自動化建置與部署。

### 1. GCP Cloud Run 自動部署 (`deploy-cloudrun.yml`)
推送變更至 `main` 分支且修改 `main.py` 或 Docker 配置時，自動編譯並部署至 Cloud Run。
* Secrets 設定需求：`GCP_PROJECT_ID`、`GCP_SA_KEY`、`GCS_BUCKET_NAME`。

### 2. GHCR Docker 鏡像發布 (`build-docker-image.yml`)
推送以 `v` 開頭的 Tag（如 `v1.0.0`）或手動觸發時，自動編譯 Docker 映像檔並推送至 GitHub Container Registry (GHCR)。
* 拉取映像檔：
  ```bash
  docker pull ghcr.io/YOUR_GITHUB_USERNAME/ffxiv-replay-ana:latest
  ```

### 3. 遠端 VM Discord Bot 自動更新 (`deploy-discord-bot.yml`)
推送變更至 `main` 分支且修改 `discord_bot.py` 時，透過 SSH 登入遠端主機，同步 `uv` 依賴並重啟 PM2 服務。
* Secrets 設定需求：`SERVER_HOST`、`SERVER_USER`、`SSH_PRIVATE_KEY`、`SERVER_PORT` (選填)。

---

## Docker 部署與跨平台運行

### 1. 建置 Docker 映像檔
```bash
docker build -t ffxiv-replay-ana .
```

### 2. 運行容器 (單獨啟動)
* **方案 A：GCS 整合模式** (自動下載 GCS 的 cookies.txt 與模板，需掛載 GCP 金鑰)：
  ```bash
  docker run -d -p 8080:8080 \
    -e PROXY_URL="YOUR_PROXY" \
    -e GCS_BUCKET_NAME="YOUR_BUCKET" \
    -e GOOGLE_APPLICATION_CREDENTIALS="/app/key.json" \
    -v $(pwd)/key.json:/app/key.json \
    --name ffxiv-analyzer \
    ffxiv-replay-ana
  ```
* **方案 B：純本地獨立模式** (直接掛載本地資源)：
  ```bash
  docker run -d -p 8080:8080 \
    -v $(pwd)/cookies.txt:/app/cookies.txt \
    -v $(pwd)/restart_template.png:/app/restart_template.png \
    --name ffxiv-analyzer \
    ffxiv-replay-ana
  ```

### 3. 一鍵在本機 Docker 同時啟動後端與 Discord Bot (推薦)
為簡化本地部署與測試，專案提供了專屬的 Docker 啟動指令檔（支援 Windows CMD 與 Linux/Git Bash），會自動安全地載入 `.env` 環境變數、建立 Docker 內部網路 `ffxiv-net`，並將後端與 Bot 容器安全串接通訊，免去設定外部代理解析或手動組裝指令。

* **Windows CMD**:
  ```cmd
  # 在 CMD 中執行以查看互動式選單：
  run\run.bat
  
  # 或直接指定動作：
  run\run.bat start
  ```
* **Linux / WSL / Git Bash**:
  ```bash
  # 給予執行權限：
  chmod +x run/run.sh
  
  # 執行以查看互動式選單：
  ./run/run.sh
  
  # 或直接指定動作：
  ./run/run.sh start
  ```

> [!NOTE]
> 腳本可用指令包含：`build`, `start`, `stop`, `restart`, `status`, `logs [backend|bot]`。
> 啟動後，API 分析後端會映射至主機 `http://localhost:8080`，Bot 容器則直接利用 Docker 內部 DNS 對應後端進行分析請求，不對外暴露 Bot 容器本身。

---

## 建議：如何提供 URL 給外網使用

### 管道 A：Cloudflare Tunnel (推薦)
免費、無需公網 IP，免去設定 Port Forwarding。

1. **安裝服務**：
   ```bash
   sudo apt-get install cloudflared
   ```
2. **暴露本地 8080 埠**：
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```
3. **設定 Discord Bot**：將終端機輸出的 HTTPS 域名寫入 Discord Bot `.env` 中 `CLOUD_RUN_URL`。

### 管道 B：ngrok
1. 安裝並設定 [ngrok](https://ngrok.com/)。
2. 執行：
   ```bash
   ngrok http 8080
   ```
3. 將產生的 HTTPS URL 寫入 Discord Bot 設定。

---

## 更新日誌 (Change Log)

### v1.0.0
- **語系與詞彙在地化**：優化了 Discord Bot 在分析流程中各個階段呈現的提示文字與 Embed 內容（如將「提取影片」改為「下載影片」、「黑屏偵測」改為「黑畫面偵測」），使其符合繁體中文的使用習慣，介面呈現更加流暢與口語化。
- **正式版發布**：此版本標記為本專案的第一個正式發布版本，確認了地端/雲端雙模式、高畫質/長影片下載分析、直播倒數防呆等核心功能的穩定性。

### v0.0.22
- 先下載後分析優化：針對 YouTube 影片引入「本地下載後分析」高速模式。利用 `yt-dlp` 地端下載優化（避開 YouTube 的 HTTP 傳輸限速），將低畫質影片高速下載至暫存區，再傳遞給 `FFmpeg` 進行本地零延遲分析。成功將分析倍速自原先 HTTP 網路串流的 **`3.78x`** 飆升至 **`150x ~ 300x`**（提升約 40 倍），且內建下載失敗自動退回流式解析與 `finally` 暫存檔安全清理機制。

### v0.0.21
- 動態超時控制：根據影片長度動態調整第一階段 FFmpeg 偵測的超時設定，解決 3 小時以上長影片超時被誤殺 (code: -9) 的問題。
- 解析階段優化：在 ytdl 階段一若因影片狀態（如轉檔中）錯誤則直接中斷，不進行無謂的代理解析 Fallback。
- Webhook 分支修復：修正 GitHub Actions 部署通知無法獲取真實分支名稱的問題。

### v0.0.20
- 服務通用化：將 Bot 端顯示的「雲端分析」文字通用化為「分析服務異常」、「後端分析伺服器」，相容地端 Docker 環境。
- 剩餘時間動態倒數：實作直播轉檔動態倒數，低於 1 分鐘時自動提示「後台轉檔已接近尾聲」。

### v0.0.19
- Bot 依賴修復：導入 `YoutubeDL`，修復快速解析影片資訊失敗問題。
- Fallback 流程優化：排查「轉檔中/直播中」等影片狀態，避免 Fallback 下載卡死。

### v0.0.17 ~ v0.0.18
- 直播轉檔檢測：當解析剛結束且正在轉檔的直播時，拋出 400 提示並估算等待時間。
- 日誌精簡防溢：FFmpeg 命令設定 `-loglevel warning`。在 API 拋出錯誤前剔除 FFmpeg 長 Banner 行，防範 Discord 1024 字元限制。

### v0.0.14 ~ v0.0.16
- 排除 DASH 格式：限制影片格式提取排除 DASH manifest 格式，防止 FFmpeg 解析失敗。
- Fallback 擴展：將「黑屏偵測失敗」與 「Exit Code 錯誤」納入 Fallback 機制，自動切換至地端下載。

### v0.0.12 ~ v0.0.13
- 下載進度條：本地下載期間，解析 `yt-dlp` 進度並於 Discord Embed 渲染進度條，顯示速度、大小與 ETA。
- 更新節流控制：限制每 3 秒更新一次 Discord 狀態，防止觸發 429 頻率限制，下載結束時強制更新為 100%。
- 修復 edit_field 錯誤：改用符合 Discord SDK 規範的 `set_field_at` 方法。

### v0.0.11
- 介面美化與拔除 Emoji：移除 Bot 介面中所有 Emoji，並將「滅團」全面調整為「Wipe」風格字詞。
- 實時耗時提示：在 API 請求發送等待及 Fallback 下載期間，定時在 Embed 提示已耗時秒數。
- Cookie 掛載修正：部署工作流同步掛載 `cookies.txt` 至 Bot 容器，解決無法獲取影片標題的 Bug。

### v0.0.10
- 預估耗時提示：快速抓取影片 metadata，動態顯示預估分析時間。
- 錯誤訊息截斷：將報錯詳情限制在 900 字元內，避免觸發 Discord 400 Bad Request。

### v0.0.9
- 卡死與洩漏修復：`try...finally` 結構確保 `threading.Timer` 被釋放，並將 FFmpeg 的 `stderr` 導向至 `DEVNULL` 防緩衝區阻塞卡死。
- 進程強制釋放：將超時釋放手段改為 `process.kill()`。
