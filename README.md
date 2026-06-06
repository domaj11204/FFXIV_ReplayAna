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

## ☁️ Google Cloud Build 雲端建置與部署 (Cloud Run)

專案已配置適用於 Cloud Run 的 [Dockerfile](Dockerfile)。為保障安全性，部署時**限制了未授權的公共存取 (`--no-allow-unauthenticated`)**，僅限 IAM 授權身分或透過本地 Proxy 存取。

### 1. 部署命令 (自動觸發 Cloud Build)
在專案目錄下執行以下指令，GCP 將會使用 Cloud Build 自動於雲端編譯並部署為私有服務：
```bash
gcloud run deploy ffxiv-replay-ana \
  --source . \
  --region asia-east1 \
  --no-allow-unauthenticated \
  --service-account="antigravity@inspiring-bee-481116-m0.iam.gserviceaccount.com" \
  --project="inspiring-bee-481116-m0"
```

*若使用自定義 `cloudbuild.yaml` 進行 CI/CD 流水線編譯，請參考：*
```bash
gcloud builds submit --config=cloudbuild.yaml --project="inspiring-bee-481116-m0"
```

---

## 🔒 安全測試：使用本地認證 Proxy (Local Auth Proxy)

由於 Cloud Run 服務已被設為私有 (Private)，直接存取其 URL 會收到 `403 Forbidden` 錯誤。我們可以使用 `gcloud` 本地認證代理將請求導向雲端服務：

### 1. 啟動本地 Proxy
在您的終端機中執行以下指令（這會自動以您的 GCP 登入憑證來簽發 ID Token 並建立安全通道）：
```bash
gcloud run services proxy ffxiv-replay-ana \
  --region=asia-east1 \
  --project=inspiring-bee-481116-m0
```
啟動後，代理伺服器會監聽本地的連接埠（預設為 `http://127.0.0.1:8080`）。

### 2. 透過 Proxy 發送測試請求
當 Proxy 運作時，您可以直接向本地的 `8080` 埠發送 HTTP 請求，Proxy 會自動加上 IAM 驗證標頭並轉發給雲端的私有 Cloud Run：

```bash
# 執行本地的 11 分鐘測試腳本 (該腳本預設即向 localhost:8080 發送請求)
uv run python test_first_11m.py
```
這將會安全地調用您佈署在 GCP Cloud Run 上的服務，並回傳分析結果！
