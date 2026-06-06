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

*若使用自定義 `cloudbuild.yaml` 進行 CI/CD 流水線編譯，請參考：*
```bash
gcloud builds submit --config=cloudbuild.yaml --project="inspiring-bee-481116-m0"
```

---

## 🔒 安全授權測試 (E2E Verification)

由於 Cloud Run 服務已被設為私有，本地測試腳本 [test_first_11m.py](test_first_11m.py) 已整合了自動化認證與驗證流程：

1. **認證金鑰簽發**：腳本會自動調用本地的 `gcloud` 獲取合法的 Identity Token。
2. **自動 Cookie 輔助**：若本地瀏覽器（Chrome/Edge/Firefox）已登入 YouTube，腳本會自動提取該 Cookie 作為分析參數發送，避開 GCP IP 遭到封鎖的 Bot Check。

### 執行分析測試
```bash
# 本地執行 E2E 測試 (預設指向部署好的 Cloud Run 私有 URL)
uv run python test_first_11m.py
```
這將會透過安全通道將請求發送給雲端的私有 Cloud Run，並由雲端進行 11 分鐘的 Wipe 分析後回傳 JSON 結果！
