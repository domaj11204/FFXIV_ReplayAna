# FFXIV Wipe Analyzer (FFXIV 副本滅團時間軸產生器)

這是一個基於 Python FastAPI 與 FFmpeg 的影像分析服務，能快速且精確地分析 FFXIV 副本戰鬥錄影（如 YouTube 影片或串流），自動辨識隊伍滅團 (Wipe) 的時間點並產生 JSON 格式的時間軸。

## 核心特色

1. **雙階段高效分析 (Map-Reduce Style)**:
   * **階段一**: 快速使用 FFmpeg `blackdetect` 偵測 3~12 秒的黑屏區間。利用 `fps=2` 降採樣，處理速度可達 **50x ~ 60x** 以上。
   * **階段二**: 只針對黑屏結束後的 30 秒窗口下載並比對 `RESTART` 金色字樣，大幅節省頻寬與運算資源。
2. **實況畫面兼容**:
   * 自動裁切畫面中央區域進行分析，完美**避開實況主的視訊鏡頭與聊天室 UI** 等四周覆蓋物。
3. **金色遮罩匹配 (Mask-Based Matching)**:
   * 透過 HSV 空間分割出金色的文字形狀遮罩，在進行模板比對時**完全忽略動態戰鬥背景與特效**，保證 100% 辨識精度。

---

## 本地開發與測試

使用 `uv` 進行依賴與專案管理。

### 1. 安裝依賴並啟動 API 伺服器
```bash
# 啟動本地開發伺服器 (預設在 8080 埠)
uv run uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

### 2. 執行測試腳本
*   [test_api.py](test_api.py)：測試完整影片分析。
*   [test_first_11m.py](test_first_11m.py)：限制分析影片的前 11 分鐘以利快速驗證。
```bash
uv run python test_first_11m.py
```

---

## ☁️ Google Cloud Build 與 GCS 整合部署 (Cloud Run)

專案配置了私有部署 (`--no-allow-unauthenticated`)。敏感的 YouTube `cookies.txt` 與 RESTART 模板圖片可以上傳到 **Google Cloud Storage (GCS) Bucket** 中，由 Cloud Run 執行時動態下載，方便隨時更新。

### 1. 建立 GCS Bucket 並上傳資源
請在專案目錄下執行以下指令建立私有儲存桶，並上傳預設資源：
```bash
# 建立專屬私有 GCS Bucket (例如台灣 asia-east1 區域)
gcloud storage buckets create gs://inspiring-bee-481116-m0-ffxiv-assets \
  --location=asia-east1 \
  --project="inspiring-bee-481116-m0"

# 上傳您的 YouTube cookies.txt 與預設匹配模板圖片
gcloud storage cp cookies.txt gs://inspiring-bee-481116-m0-ffxiv-assets/
gcloud storage cp restart_template.png gs://inspiring-bee-481116-m0-ffxiv-assets/
```

### 2. 部署程式碼至 Cloud Run (綁定 GCS Bucket)
使用以下指令部署。我們將透過環境變數 `GCS_BUCKET_NAME` 將容器連結至該 Bucket：
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

### 2. 啟動 Discord Bot (本地 / 獨立模式)
```bash
# 使用 uv 啟動機器人
uv run python discord_bot.py
```

### 3. 指令說明
在 Discord 中輸入 `/analyze` 指令：
* `youtube_url` (必填)：YouTube 影片網址
* `threshold` (選填)：RESTART 模板比對相似度閾值 (預設 0.65)
* `x_min` / `x_max` / `y_min` / `y_max` (選填)：裁切偵測區域比例
* `scan_duration_limit` (選填)：限制只分析影片前 N 秒 (0 表示分析整部)

---

## 🚀 三種建置與部署版本指南

本專案已完全優化，提供以下三種不同場景的部署與使用方式，滿足安全性、獨立運作與便捷性的需求。

### 1. 模式一：Cloud Run 全雲端版
適合需要 24 小時在線、不想耗用本地硬體資源的情境。

* **部署方式**：使用 Cloud Build 將代碼打包並部署至 Cloud Run。
* **部署指令範例**：
  ```bash
  gcloud run deploy ffxiv-replay-ana \
    --image asia-east1-docker.pkg.dev/YOUR_PROJECT_ID/cloud-run-source-deploy/ffxiv-replay-ana:latest \
    --region asia-east1 \
    --set-env-vars GCS_BUCKET_NAME="YOUR_BUCKET"
  ```

### 2. 模式二：任何 Docker 運行的獨立 HTTP-Server (支援 IPv6 雙棧 + 質感 Web UI)
如果您想直接提供一個「看起來安全、沒有奇怪 URL 參數」的網頁工具給朋友，或是希望在擁有公網 IPv6 的本地 Ubuntu / NAS 上運行，這是最方便的選擇。

* **特色**：
  * **內建 FFXIV 暗黑科技風網頁**：打開瀏覽器直接點擊，包含輸入框、動態分析進度與「一鍵複製結果」按鈕，極富遊戲代入感。
  * **IPv6 雙棧支援**：Docker 內部將 Uvicorn 綁定至 `::`。在支援雙棧的系統上，能同時監聽 IPv6 與 IPv4 請求。
* **運行指令 (方案 A：與 GCS 整合)**：
  ```bash
  docker run -d -p 8080:8080 \
    -e GCS_BUCKET_NAME="YOUR_BUCKET" \
    -e GOOGLE_APPLICATION_CREDENTIALS="/app/key.json" \
    -v $(pwd)/key.json:/app/key.json \
    --name ffxiv-analyzer-web \
    ffxiv-replay-ana
  ```
* **運行指令 (方案 B：純本地獨立模式)**：
  如果您想完全擺脫 GCP/GCS，將本地 `cookies.txt` 與模板掛載進去即可：
  ```bash
  docker run -d -p 8080:8080 \
    -v $(pwd)/cookies.txt:/app/cookies.txt \
    -v $(pwd)/restart_template.png:/app/restart_template.png \
    --name ffxiv-analyzer-web \
    ffxiv-replay-ana
  ```
* **如何使用**：
  用瀏覽器訪問 `http://[YOUR_IPV6_ADDRESS]:8080/` 或 `http://localhost:8080/`，即可看到精美的圖形化分析工具。

### 3. 模式三：Discord User-Installable App (個人帳號安裝版)
特別適合隊友「**沒有伺服器管理員權限，無法把機器人拉進頻道**」的情境。

* **特色**：
  * 隊友可以將 Bot 直接安裝到「個人帳號」，而不是伺服器。
  * 隊友可在**任何伺服器**的輸入框直接呼叫 `/analyze`，或是在與機器人的**私訊對話框 (DM)** 中單獨使用，隱私且不打擾他人。
* **配置步驟**：
  1. 進入 [Discord Developer Portal](https://discord.com/developers/applications)。
  2. 選擇您的 Bot，點選左側選單的 **Installation**。
  3. 在 **Installation Contexts** 勾選 **User Install** (可與 Guild Install 並存)。
  4. 在 **Default Install Settings** 的 Scopes 中加入 `applications.commands`。
  5. 複製下方的 **Install Link** 分享給您的朋友。朋友點擊後選擇「新增至我的應用程式 (Add to My Apps)」即可完成安裝。

---

## 🛠️ CI/CD 自動化管道說明

我們在 `.github/workflows/` 下為這三種版本配置了對應的 GitHub Actions CI/CD，讓您修改程式碼後可輕鬆實現自動建置與部署。

### 1. GCP Cloud Run 自動部署 (`deploy-cloudrun.yml`)
當推送變更至 `main` 分支且修改了 `main.py` 或 Docker 設定時，會自動編譯並重新部署至 Cloud Run。
* **需要設定的 Repository Secrets**：
  * `GCP_PROJECT_ID`：您的 GCP 專案 ID。
  * `GCP_SA_KEY`：擁有 Artifact Registry 寫入權限與 Cloud Run 管理員權限的 Service Account 金鑰 JSON。
  * `GCS_BUCKET_NAME`：用於存放 assets 的 GCP 儲存桶名稱。

### 2. GHCR 獨立 Docker 鏡像發布 (`build-docker-image.yml`)
當您在 Git 建立並推送以 `v` 開頭的 Tag (例如 `v1.0.0`)，或是在 Actions 面板手動點擊執行時，工作流會自動打包 Docker 鏡像，並將其推送到 GitHub Container Registry (GHCR)。
* **使用方式**：
  不需要設定額外的 Secrets！打包完成後，任何人皆可直接拉取最新的 Docker 鏡像：
  ```bash
  docker pull ghcr.io/YOUR_GITHUB_USERNAME/ffxiv-replay-ana:latest
  ```

### 3. 遠端 VM Discord Bot 自動更新 (`deploy-discord-bot.yml`)
當推送變更至 `main` 分支且修改了 `discord_bot.py` 時，會自動透過 SSH 登入您託管 Bot 的虛擬主機，拉取最新代碼、同步 `uv` 依賴並重啟 PM2 服務。
* **需要設定的 Repository Secrets**：
  * `SERVER_HOST`：您虛擬主機的公網 IP 位址。
  * `SERVER_USER`：SSH 登入帳號。
  * `SSH_PRIVATE_KEY`：登入伺服器所用的 SSH 私鑰。
  * `SERVER_PORT`：（選填）SSH 連接埠，預設為 22。

---

## 🐳 Docker 部署與跨平台運行指南 (本地 / Ubuntu / 任何伺服器)

本專案已完全容器化，API 服務可以透過 `Dockerfile` 打包，並輕鬆遷移至任何安裝有 Docker 的 Ubuntu 或其他作業系統中運行。

### 1. 建置 Docker 映像檔
在專案根目錄下，執行以下命令進行映像檔打包：
```bash
docker build -t ffxiv-replay-ana .
```

### 2. 在 Ubuntu 或本地運行容器
依據您的整合方式，選擇以下其中一種執行方式：

#### 方案甲：與 GCS 整合模式 (與雲端相同)
此模式會自動下載 GCS 儲存桶中的 `cookies.txt` 與模板，需要掛載您的 GCP 憑證金鑰：
```bash
docker run -d -p 8080:8080 \
  -e PROXY_URL="http://k4zo76031-region-TW-sid-yW5Pb2GJ-t-5:jkmchk4r@hk.novproxy.io:1000" \
  -e GCS_BUCKET_NAME="inspiring-bee-481116-m0-ffxiv-assets" \
  -e GOOGLE_APPLICATION_CREDENTIALS="/app/inspiring-bee-481116-m0-1b2c8b808a2a.json" \
  -v $(pwd)/inspiring-bee-481116-m0-1b2c8b808a2a.json:/app/inspiring-bee-481116-m0-1b2c8b808a2a.json \
  --name ffxiv-analyzer \
  ffxiv-replay-ana
```

#### 方案乙：純本地獨立模式 (不依賴 GCP 金鑰與 GCS)
如果您不希望使用 GCS 下載，可以直接把本地的 `cookies.txt` 與 `restart_template.png` 映射進去：
```bash
docker run -d -p 8080:8080 \
  -v $(pwd)/cookies.txt:/app/cookies.txt \
  -v $(pwd)/restart_template.png:/app/restart_template.png \
  --name ffxiv-analyzer \
  ffxiv-replay-ana
```

---

## 🌐 建議：如何提供 URL 給外網 (Discord Bot) 使用？

如果您將此 API 服務部署在本地電腦或局域網的 Ubuntu 伺服器上，但需要讓外網（例如 Discord Bot 服務端）能夠訪問它，以下是推薦的兩種外網暴露（Tunneling）管道：

### 管道 A：Cloudflare Tunnel (最推薦 🌟)
這套方案完全免費、無需公網 IP、不需在路由器進行 Port Forwarding (虛擬伺服器設定)，且由 Cloudflare 提供 DDoS 安全防護。

1. **在 Ubuntu 上安裝 Cloudflare 守護進程**：
   ```bash
   sudo apt-get install cloudflared
   ```
2. **一鍵將本地 8080 連接埠暴露至外網**：
   ```bash
   cloudflared tunnel --url http://localhost:8080
   ```
3. **獲取外網 URL**：
   執行後控制台會印出一個臨時的隨機 HTTPS 域名，例如 `https://your-unique-subdomain.trycloudflare.com`。
4. **Discord Bot 配置**：
   直接將此 URL 寫入 Discord Bot 本地 `.env` 中的 `CLOUD_RUN_URL` 環境變數即可：
   `CLOUD_RUN_URL=https://your-unique-subdomain.trycloudflare.com/analyze`

### 管道 B：ngrok (適合臨時快速調試)
1. 註冊並安裝 [ngrok](https://ngrok.com/)。
2. 終端機執行：
   ```bash
   ngrok http 8080
   ```
3. 獲得類似 `https://xxxx.ngrok-free.app` 的隨機外網 URL，寫入 Discord Bot 設定檔即可使用。

---

## 📝 更新日誌 (Change Log)

### v0.0.21
- **動態超時控制**：依據影片長度動態調整第一階段 FFmpeg 黑屏偵測的超時時間（每 1 小時影片額外給予 120 秒，基礎 180 秒），徹底解決 3 小時以上長影片在分析時被誤殺 (code: -9) 的問題。
- **解析階段優化**：在 `get_youtube_video_info` 階段一因影片本身狀態（如轉檔中）拋出錯誤時，直接中斷並不進行無謂的階段二代理解析 Fallback。
- **Webhook 分支修復**：修正 GitHub Actions 的 Discord Webhook 在 Tag 部署時無法取得真實分支名稱的問題（透過 `git branch` 反查真實的分支如 `main`）。

### v0.0.20
- **服務通用化**：將 Discord Bot 顯示的「雲端分析失敗」、「Cloud Run 服務」等字眼通用化為「分析服務異常」、「後端分析伺服器」，完美兼容本地 Docker 容器運行環境。
- **動態剩餘時間倒數**：在後端實作了基於 `release_timestamp`（或 `timestamp`）加上影片時長計算直播結束時間的演算法，扣除當前系統時間以實現「轉檔剩餘時間動態遞減」倒數，並在小於 1 分鐘時自動提示「後台轉檔已接近尾聲」。

### v0.0.19
- **Bot 依賴修復**：在 `discord_bot.py` 中導入 `YoutubeDL`，修復快速解析影片資訊失效且日誌報錯 `name 'YoutubeDL' is not defined` 的問題。
- **Fallback 流程避空**：優化本地 GCS Fallback 機制觸發條件，主動排除「轉檔中/直播中」等影片本身狀態的錯誤，避免 Bot 在本地下載無法轉檔的影片而導致進度永久卡死在「分析中」。

### v0.0.17 ~ v0.0.18
- **直播轉檔檢測**：引入了 `live_status == 'post_live'` 的狀態偵測，當遇到剛結束直播且處於轉檔中的影片時，主動拋出 400 警告並估算轉換所需時間。
- **雙重日誌精簡防呆**：
  - 在 FFmpeg 指令中加入 `-loglevel warning`。
  - 在 Python 拋出異常前，以 `filtered_lines` 剔除所有與 FFmpeg 編譯配置相關的長 Banner 行，確保 Discord 訊息因長度被截斷時，仍能保留最末尾的 15 行真實報錯。

### v0.0.14 ~ v0.0.16
- **排除 DASH 格式**：針對剛結束直播的影片格式提取加入 `[protocol!*=dash]` 與 `construct_dash=False`，防止 `yt-dlp` 提取出 FFmpeg 無法解析的 DASH manifest 格式。
- **本地 Fallback 擴展**：將「黑屏偵測失敗」與 「Exit Code 錯誤」納入 Fallback 機制，當雲端 IP 被 YouTube 封鎖時自動切換至地端寬頻下載。

### v0.0.12 ~ v0.0.13
- **即時下載進度條**：在本地 GCS Fallback 下載期間，從 `yt-dlp` 的 stdout 管道中即時捕獲進度，於 Discord Embed 中動態渲染文字進度條（如 `[■■■■□□□□□□] 40.5%`）並顯示下載速度、大小與剩餘時間。
- **更新節流控制**：實作每 3 秒更新一次 Discord 狀態的節流限制（Rate Limit），防止頻繁 API 請求觸發 429 封鎖，並在下載完畢時強制更新至 100%。
- **修復 edit_field Bug**：修正 Embed 呼叫不存在的 `edit_field` 的錯誤，改用符合規範的 `set_field_at` 方法。

### v0.0.11
- **Wipe 風格美化與拔除 Emoji**：移除 Discord Bot 所有交互介面中的 Emoji 裝飾，並將所有「滅團」字眼全面調整為符合主流副本習慣的「Wipe」風格字詞（如「Wipe數:」、「Wipe #」等）。
- **實時耗時提示**：在 API 請求發送等待以及下載期間，定時在 Embed description 更新「已耗時 N 秒」的實時進度，讓使用者掌握後端分析進度。
- **Cookie 掛載修正**：在地端部署工作流中，同步為 `ffxiv-discord-bot` 容器掛載本地 `cookies.txt`，徹底解決 Bot 無法獲得影片標題與時長的 YouTube 解析封鎖 Bug。

### v0.0.10
- **預估耗時提示**：透過 `yt-dlp` 於開始分析時快速抓取影片 metadata，動態計算「影片時長 * 4.5% + 10秒」作為預估耗時，並預先更新在 Embed 狀態中。
- **安全錯誤截斷**：將 API 出錯回報詳情字元安全截斷在 900 字元以內，徹底解決因報錯過長超出 Discord Embed 1024 字元限制導致的 `400 Bad Request` 崩潰問題。

### v0.0.9
- **FFmpeg 卡死與洩漏修復**：引入 `try...finally` 結構確保 `threading.Timer` 超時保護必定被 `cancel()` 關閉。
- **預防標準錯誤阻塞**：將 FFmpeg 執行比對時的 `stderr` 重新導向至 `DEVNULL`，避免 stderr 管道被 64KB 緩衝區寫滿導致進程無限卡死。
- **版本與時間日誌前綴**：重寫 Python 全域 `print` 函數，自動附加 `[VERSION]` 及時間戳前綴並強制 flush。
- **強行釋放進程**：將異常超時的進程關閉手段由 `terminate()` 升級為 `kill()` (SIGKILL)，保證徹底清理 FFmpeg 殘留。
