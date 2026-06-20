import os
import re
import subprocess
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from yt_dlp import YoutubeDL
from google.cloud import storage

# Proxy settings removed

import datetime
import builtins

VERSION = "v0.0.34"

def print(*args, **kwargs):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prefix = f"[{now}] [{VERSION}]"
    if args:
        new_args = (f"{prefix} {args[0]}",) + args[1:]
    else:
        new_args = (prefix,)
    
    if "flush" not in kwargs:
        kwargs["flush"] = True
        
    builtins.print(*new_args, **kwargs)

def download_from_gcs(bucket_name: str, blob_name: str, dest_path: str) -> bool:
    """
    從指定的 GCS Bucket 中下載指定的 blob 檔案至本地 dest_path。
    如果下載成功，回傳 True；若檔案不存在或下載失敗，回傳 False。
    """
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if blob.exists():
            # 確保目標目錄存在
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            blob.download_to_filename(dest_path)
            print(f"成功自 GCS Bucket [{bucket_name}] 下載 {blob_name} 至 {dest_path}")
            return True
        else:
            print(f"GCS Bucket [{bucket_name}] 中找不到資源: {blob_name}")
            return False
    except Exception as e:
        print(f"自 GCS 下載資源 [{blob_name}] 失敗: {str(e)}")
        return False

def get_local_video_info(file_path: str) -> dict:
    """
    使用 OpenCV 快速讀取本地影片的解析度與時長。
    """
    import cv2
    cap = cv2.VideoCapture(file_path)
    if not cap.isOpened():
        return {"width": 640, "height": 360, "duration": 0.0}
    
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    
    duration = 0.0
    if fps > 0:
        duration = frame_count / fps
        
    cap.release()
    return {"width": width, "height": height, "duration": duration}

def is_direct_stream_url(url: str) -> bool:
    """
    判斷傳入的 URL 是否已經是解析好的視訊直鏈（如含有 googlevideo.com 或是非 YouTube 的 MP4 網址）。
    """
    if "googlevideo.com" in url or "manifest" in url or ".mp4" in url:
        return True
    if not any(domain in url for domain in ["youtube.com", "youtu.be", "youtube-nocookie.com"]):
        return True
    return False

app = FastAPI(
    title="FFXIV Wipe Analyzer API",
    description="分析 FFXIV 影片並偵測滅團 (Wipe) 時間軸之 API",
    version="1.0.0"
)

# 啟用 CORS 支援以確保跨域相容性
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FFXIV Wipe Analyzer</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Noto+Sans+TC:wght@300;400;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0c0d0f;
            --card-bg: rgba(20, 22, 26, 0.85);
            --gold: #cca052;
            --gold-hover: #e5bd75;
            --gold-glow: rgba(204, 160, 82, 0.4);
            --text-main: #e2e8f0;
            --text-muted: #94a3b8;
            --danger: #ef4444;
            --success: #22c55e;
        }
        body {
            background-color: var(--bg-color);
            background-image: 
                radial-gradient(circle at 20% 30%, rgba(204, 160, 82, 0.05) 0%, transparent 40%),
                radial-gradient(circle at 80% 70%, rgba(204, 160, 82, 0.03) 0%, transparent 40%);
            color: var(--text-main);
            font-family: 'Outfit', 'Noto Sans TC', sans-serif;
            margin: 0;
            padding: 0;
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .container {
            width: 100%;
            max-width: 680px;
            padding: 40px 20px;
            box-sizing: border-box;
        }
        .header {
            text-align: center;
            margin-bottom: 40px;
        }
        .header h1 {
            font-size: 2.5rem;
            font-weight: 800;
            color: var(--gold);
            text-shadow: 0 0 15px rgba(204, 160, 82, 0.25);
            margin: 0 0 10px 0;
            letter-spacing: 2px;
            text-transform: uppercase;
        }
        .header p {
            color: var(--text-muted);
            font-size: 1.05rem;
            margin: 0;
        }
        .card {
            background: var(--card-bg);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(204, 160, 82, 0.15);
            border-radius: 16px;
            padding: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
            transition: all 0.3s ease;
        }
        .input-group {
            margin-bottom: 24px;
        }
        label {
            display: block;
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--gold);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        input[type="text"] {
            background: rgba(10, 11, 14, 0.8);
            border: 1px solid rgba(204, 160, 82, 0.25);
            color: var(--text-main);
            padding: 14px 16px;
            border-radius: 8px;
            font-size: 15px;
            width: 100%;
            box-sizing: border-box;
            transition: all 0.3s ease;
        }
        input[type="text"]:focus {
            outline: none;
            border-color: var(--gold);
            box-shadow: 0 0 12px var(--gold-glow);
        }
        .settings-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-bottom: 24px;
        }
        .setting-item {
            display: flex;
            flex-direction: column;
        }
        input[type="number"] {
            background: rgba(10, 11, 14, 0.8);
            border: 1px solid rgba(204, 160, 82, 0.25);
            color: var(--text-main);
            padding: 10px 12px;
            border-radius: 8px;
            font-size: 14px;
            width: 100%;
            box-sizing: border-box;
            transition: all 0.3s ease;
        }
        input[type="number"]:focus {
            outline: none;
            border-color: var(--gold);
            box-shadow: 0 0 8px var(--gold-glow);
        }
        .btn-analyze {
            background: linear-gradient(135deg, #a67c37 0%, var(--gold) 100%);
            border: none;
            color: #121315;
            padding: 15px 30px;
            font-size: 16px;
            font-weight: 700;
            border-radius: 8px;
            width: 100%;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(204, 160, 82, 0.2);
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .btn-analyze:hover {
            background: linear-gradient(135deg, var(--gold) 0%, var(--gold-hover) 100%);
            box-shadow: 0 6px 20px rgba(204, 160, 82, 0.35);
            transform: translateY(-1px);
        }
        .btn-analyze:active {
            transform: translateY(1px);
        }
        .btn-analyze:disabled {
            background: #27282c;
            color: var(--text-muted);
            box-shadow: none;
            cursor: not-allowed;
            transform: none;
        }
        .status-container {
            display: none;
            margin-top: 30px;
            padding: 20px;
            border-radius: 8px;
            background: rgba(204, 160, 82, 0.05);
            border: 1px dashed rgba(204, 160, 82, 0.3);
            text-align: center;
        }
        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(204, 160, 82, 0.1);
            border-radius: 50%;
            border-top-color: var(--gold);
            animation: spin 1s linear infinite;
            margin: 0 auto 15px auto;
        }
        @keyframes spin {
            to { transform: rotate(360deg); }
        }
        .status-text {
            font-size: 0.95rem;
            color: var(--text-main);
            margin: 0;
        }
        .status-sub {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-top: 5px;
        }
        .results-container {
            display: none;
            margin-top: 30px;
        }
        .results-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid rgba(204, 160, 82, 0.2);
            padding-bottom: 12px;
            margin-bottom: 20px;
        }
        .results-title {
            font-size: 1.15rem;
            font-weight: 700;
            color: var(--gold);
            margin: 0;
        }
        .results-duration {
            font-size: 0.85rem;
            color: var(--text-muted);
        }
        .timeline {
            position: relative;
            padding-left: 24px;
            margin-bottom: 24px;
        }
        .timeline::before {
            content: '';
            position: absolute;
            left: 5px;
            top: 5px;
            bottom: 5px;
            width: 2px;
            background: rgba(204, 160, 82, 0.2);
        }
        .timeline-item {
            position: relative;
            margin-bottom: 20px;
        }
        .timeline-item::before {
            content: '';
            position: absolute;
            left: -23px;
            top: 6px;
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--gold);
            box-shadow: 0 0 8px var(--gold);
        }
        .timeline-item.start::before {
            background: var(--text-muted);
            box-shadow: none;
        }
        .timeline-content {
            background: rgba(10, 11, 14, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 12px 16px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .timeline-time {
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--text-main);
        }
        .timeline-label {
            font-size: 0.95rem;
            color: var(--gold);
            font-weight: 600;
        }
        .timeline-score {
            font-size: 0.75rem;
            background: rgba(204, 160, 82, 0.15);
            color: var(--gold);
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 10px;
        }
        .action-group {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }
        .btn-action {
            background: rgba(204, 160, 82, 0.08);
            border: 1px solid rgba(204, 160, 82, 0.3);
            color: var(--gold);
            padding: 10px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.85rem;
            font-weight: 600;
            transition: all 0.2s ease;
            text-align: center;
        }
        .btn-action:hover {
            background: rgba(204, 160, 82, 0.2);
            border-color: var(--gold);
        }
        .error-container {
            display: none;
            margin-top: 30px;
            padding: 16px;
            border-radius: 8px;
            background: rgba(239, 68, 68, 0.1);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #fca5a5;
            font-size: 0.9rem;
            line-height: 1.4;
        }
        .copied-toast {
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%) translateY(100px);
            background: var(--gold);
            color: #121315;
            padding: 10px 24px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 0.9rem;
            box-shadow: 0 10px 20px rgba(0,0,0,0.3);
            transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            opacity: 0;
            z-index: 1000;
        }
        .copied-toast.show {
            transform: translateX(-50%) translateY(0);
            opacity: 1;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>FFXIV Wipe Analyzer</h1>
            <p>分析副本錄影，快速找出並標記所有滅團點</p>
        </div>
        
        <div class="card">
            <div class="input-group">
                <label for="video-url">YouTube 影片 / GCS 影片網址</label>
                <input type="text" id="video-url" placeholder="請貼上影片網址，例如 https://www.youtube.com/watch?v=..." autocomplete="off">
            </div>
            
            <div class="settings-grid">
                <div class="setting-item">
                    <label for="threshold">相似度閾值 (0.0~1.0)</label>
                    <input type="number" id="threshold" value="0.65" min="0.1" max="1.0" step="0.05">
                </div>
                <div class="setting-item">
                    <label for="scan-limit">限制掃描前 N 秒 (0無限制)</label>
                    <input type="number" id="scan-limit" value="0" min="0">
                </div>
            </div>
            
            <button class="btn-analyze" id="btn-submit">開始分析影片</button>
            
            <div class="status-container" id="status-box">
                <div class="spinner"></div>
                <p class="status-text" id="status-msg">正在啟動分析程序...</p>
                <p class="status-sub">因為需要串流下載與影像識別，此過程通常需要 30 秒至 2 分鐘，請勿關閉網頁。</p>
            </div>
            
            <div class="error-container" id="error-box"></div>
            
            <div class="results-container" id="results-box">
                <div class="results-header">
                    <h3 class="results-title" id="results-title">分析結果</h3>
                    <span class="results-duration" id="results-duration">影片長度: -</span>
                </div>
                
                <div class="timeline" id="timeline-box">
                    <!-- 動態生成時間軸 -->
                </div>
                
                <div class="action-group">
                    <button class="btn-action" id="btn-copy-black">🔵 複製時間軸 (黑屏點)</button>
                    <button class="btn-action" id="btn-copy-restart">🟢 複製時間軸 (RESTART點)</button>
                </div>
            </div>
        </div>
    </div>
    
    <div class="copied-toast" id="toast">已複製到剪貼簿！</div>

    <script>
        const btnSubmit = document.getElementById('btn-submit');
        const urlInput = document.getElementById('video-url');
        const thresholdInput = document.getElementById('threshold');
        const scanLimitInput = document.getElementById('scan-limit');
        
        const statusBox = document.getElementById('status-box');
        const statusMsg = document.getElementById('status-msg');
        const errorBox = document.getElementById('error-box');
        const resultsBox = document.getElementById('results-box');
        const resultsTitle = document.getElementById('results-title');
        const resultsDuration = document.getElementById('results-duration');
        const timelineBox = document.getElementById('timeline-box');
        
        const btnCopyBlack = document.getElementById('btn-copy-black');
        const btnCopyRestart = document.getElementById('btn-copy-restart');
        const toast = document.getElementById('toast');
        
        let lastResult = null;
        
        function formatTime(seconds) {
            seconds = Math.max(0, seconds);
            const h = Math.floor(seconds / 3600);
            const m = Math.floor((seconds % 3600) / 60);
            const s = Math.floor(seconds % 60);
            if (h > 0) {
                return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
            }
            return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
        }
        
        btnSubmit.addEventListener('click', async () => {
            const url = urlInput.value.trim();
            if (!url) {
                showError('請輸入有效的影片網址。');
                return;
            }
            
            errorBox.style.display = 'none';
            resultsBox.style.display = 'none';
            statusBox.style.display = 'block';
            btnSubmit.disabled = true;
            statusMsg.textContent = '正在啟動雲端分析引擎...';
            
            const tips = [
                '正在向影音平台取得串流位址...',
                '串流載入中，開始進行全黑影格快速偵測...',
                '正在掃描黑畫面區間（通常需要數十秒）...',
                '黑畫面偵測完成！正在驗證後半段是否出現 RESTART 字樣...',
                '影像比對中，利用多尺度模板演算法計算金色像素匹配度...',
                '正在彙整最終時間軸資料...'
            ];
            let tipIdx = 0;
            const statusInterval = setInterval(() => {
                if (tipIdx < tips.length) {
                    statusMsg.textContent = tips[tipIdx++];
                }
            }, 8000);
            
            try {
                const response = await fetch('/analyze', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        youtube_url: url,
                        threshold: parseFloat(thresholdInput.value),
                        scan_duration_limit: parseFloat(scanLimitInput.value),
                        template_name: "restart_template.png",
                        x_min: 0.30,
                        x_max: 0.70,
                        y_min: 0.25,
                        y_max: 0.50
                    })
                });
                
                clearInterval(statusInterval);
                
                if (!response.ok) {
                    const errorText = await response.text();
                    let errMsg = '分析失敗，請確認網址是否正確。';
                    try {
                        const errJson = JSON.parse(errorText);
                        errMsg = errJson.detail || errMsg;
                    } catch(e) {}
                    throw new Error(errMsg);
                }
                
                const data = await response.json();
                lastResult = data;
                showResults(data);
                
            } catch (err) {
                clearInterval(statusInterval);
                showError(err.message);
            } finally {
                statusBox.style.display = 'none';
                btnSubmit.disabled = false;
            }
        });
        
        function showError(msg) {
            errorBox.textContent = `⚠️ 錯誤：${msg}`;
            errorBox.style.display = 'block';
        }
        
        function showResults(data) {
            resultsTitle.textContent = data.video_title || '分析結果';
            resultsDuration.textContent = data.video_duration_seconds > 0 
                ? `影片長度: ${formatTime(data.video_duration_seconds)}` 
                : '影片長度: 未知';
            
            timelineBox.innerHTML = '';
            
            const startItem = document.createElement('div');
            startItem.className = 'timeline-item start';
            startItem.innerHTML = `
                <div class="timeline-content">
                    <span class="timeline-time">00:00</span>
                    <span class="timeline-label" style="color: var(--text-muted)">戰鬥開始 / 影片起點</span>
                </div>
            `;
            timelineBox.appendChild(startItem);
            
            if (!data.wipes || data.wipes.length === 0) {
                const emptyItem = document.createElement('div');
                emptyItem.style.padding = '15px';
                emptyItem.style.textAlign = 'center';
                emptyItem.style.color = 'var(--text-muted)';
                emptyItem.textContent = '恭喜！此錄影區間內未偵測到任何滅團 (RESTART) 標記。';
                timelineBox.appendChild(emptyItem);
            } else {
                data.wipes.forEach(w => {
                    const item = document.createElement('div');
                    item.className = 'timeline-item';
                    const displayTime = formatTime(w.black_screen_start);
                    item.innerHTML = `
                        <div class="timeline-content">
                            <span class="timeline-time">${displayTime}</span>
                            <div>
                                <span class="timeline-label">WIPE #${w.wipe_number}</span>
                                <span class="timeline-score">${Math.round(w.similarity_score * 100)}% 相似</span>
                            </div>
                        </div>
                    `;
                    timelineBox.appendChild(item);
                });
            }
            
            resultsBox.style.display = 'block';
            resultsBox.scrollIntoView({ behavior: 'smooth' });
        }
        
        function showToast() {
            toast.classList.add('show');
            setTimeout(() => {
                toast.classList.remove('show');
            }, 2000);
        }
        
        function generateTextTimeline(useRestart) {
            if (!lastResult || !lastResult.wipes) return '';
            const lines = ['00:00 戰鬥開始 / 影片起點'];
            lastResult.wipes.forEach(w => {
                const sec = useRestart ? w.restart_word_detected_at : w.black_screen_start;
                lines.push(`${formatTime(sec)} ${useRestart ? 'RESTART' : '滅團'} #${w.wipe_number}`);
            });
            return lines.join('\\n');
        }
        
        btnCopyBlack.addEventListener('click', () => {
            if (!lastResult) return;
            const text = generateTextTimeline(false);
            navigator.clipboard.writeText(text).then(() => {
                showToast();
            });
        });
        
        btnCopyRestart.addEventListener('click', () => {
            if (!lastResult) return;
            const text = generateTextTimeline(true);
            navigator.clipboard.writeText(text).then(() => {
                showToast();
            });
        });
    </script>
</body>
</html>"""

@app.get("/", response_class=HTMLResponse)
async def get_web_ui():
    return HTML_TEMPLATE


# 偵測請求的輸入模型
class AnalyzeRequest(BaseModel):
    youtube_url: str = Field(..., description="YouTube 影片網址")
    template_name: str = Field("restart_template.png", description="RESTART 模板圖片名稱，預設為 restart_template.png")
    x_min: float = Field(0.30, ge=0.0, le=1.0, description="偵測區域左邊界比例 (0.0~1.0)")
    x_max: float = Field(0.70, ge=0.0, le=1.0, description="偵測區域右邊界比例 (0.0~1.0)")
    y_min: float = Field(0.25, ge=0.0, le=1.0, description="偵測區域上邊界比例 (0.0~1.0)")
    y_max: float = Field(0.50, ge=0.0, le=1.0, description="偵測區域下邊界比例 (0.0~1.0)")
    threshold: float = Field(0.65, ge=0.0, le=1.0, description="RESTART 模板比對相似度閾值")
    scan_duration_limit: float = Field(0.0, description="限制掃描影片的前 N 秒，0.0 表示不限制")
    cookies_content: str | None = Field(None, description="YouTube Cookie 檔案內容，用以避免 YouTube Bot 阻擋驗證")
    video_title: str | None = Field(None, description="可選的影片標題，若提供則優先使用")
    video_duration: float | None = Field(None, description="可選的影片長度 (秒)，若提供則優先使用")
    debug: bool | None = Field(None, description="是否啟用除錯模式，保留 Wipe 判斷過程的圖片與日誌")
    black_pix_th: float | None = Field(None, description="可選的黑屏偵測像素閾值 (0.0~1.0)")
    black_duration: float | None = Field(None, description="可選的最小黑屏持續時間 (秒)")

# 單個 Wipe 事件的輸出模型
class WipeEvent(BaseModel):
    wipe_number: int
    black_screen_start: float
    black_screen_end: float
    restart_word_detected_at: float
    similarity_score: float

# 偵測結果的輸出模型
class AnalyzeResponse(BaseModel):
    status: str
    video_title: str
    video_duration_seconds: float
    wipes: list[WipeEvent]

def parse_ydl_info(info: dict) -> dict:
    """
    從 yt-dlp 回傳的 info 中提取直鏈與基本資訊。
    """
    # 檢查是否為剛結束正在後台轉檔的直播
    live_status = info.get('live_status')
    if live_status == 'post_live':
        duration = info.get('duration', 0.0)
        # 估算轉檔總時間 (影片長度的 15% 左右，最少 10 分鐘，最多 120 分鐘)
        total_est_min = max(10, min(120, int(duration * 0.15 / 60)))
        
        # 嘗試取得直播結束時間，並扣除已過去的時間以進行動態倒數
        start_ts = info.get('release_timestamp') or info.get('timestamp')
        if start_ts:
            import time as py_time
            end_ts = start_ts + duration
            elapsed_sec = py_time.time() - end_ts
            if elapsed_sec > 0:
                remaining_min = int(total_est_min - (elapsed_sec / 60))
                remaining_min = max(1, remaining_min)
            else:
                remaining_min = total_est_min
        else:
            remaining_min = total_est_min
            
        if remaining_min > 1:
            raise ValueError(f"該影片為剛結束的直播（狀態：轉檔處理中）。YouTube 預計需要約 {remaining_min} 分鐘進行後台處理以產生正常影片格式，請稍候再試。")
        else:
            raise ValueError("該影片為剛結束的直播（狀態：後台轉檔處理已接近尾聲）。預計在 1~2 分鐘內即可完成，請稍候再次嘗試。")

    stream_url = info.get('url')
    if not stream_url and 'requested_formats' in info:
        for f in info['requested_formats']:
            if f.get('vcodec') != 'none' and f.get('url'):
                stream_url = f['url']
                break
                
    if stream_url and ("manifest/dash" in stream_url or "manifest/dash" in info.get('url', '') or stream_url.endswith(".mpd")):
        stream_url = None

    if not stream_url:
        raise ValueError("找不到可用的視訊串流網址。這可能是因為該影片為剛結束的直播，YouTube 正在進行後台轉檔處理（通常需要一些時間才能產生正常非 DASH 格式影片），請稍候再試。")
        
    return {
        "stream_url": stream_url,
        "title": info.get('title', 'Unknown Title'),
        "duration": info.get('duration', 0.0),
        "width": info.get('width', 640),
        "height": info.get('height', 360),
    }

def get_youtube_video_info(youtube_url: str, cookies_path: str | None = None) -> dict:
    """
    使用 yt-dlp 取得影片的直鏈網址、標題與尺寸資訊。
    採用雙軌制：有 Cookie 時使用高速直連，無 Cookie 時使用住宅代理。
    """
    # 階段二選項：不帶 Cookie，限制 ios/android 避開 bot 檢測，並加入住宅代理
    ydl_opts_no_cookie = {
        'format': 'bestvideo[height<=360][protocol*=m3u8]/best[height<=360][protocol*=m3u8]/bestvideo[height<=360][protocol!*=dash]/worstvideo/worst',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'client': ['ios', 'android'],
                'construct_dash': False
            }
        }
    }
    
    # 階段一選項：帶 Cookie，使用與階段二相同的 ios/android 客戶端以確保取得穩定的 m3u8 格式，防止 Requested format is not available 錯誤
    ydl_opts_with_cookie = {
        'format': 'bestvideo[height<=360][protocol*=m3u8]/best[height<=360][protocol*=m3u8]/bestvideo[height<=360][protocol!*=dash]/worstvideo/worst',
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'client': ['ios', 'android'],
                'construct_dash': False
            }
        }
    }
    
    # 僅在階段二無 Cookie fallback 時進行直連解析，已移除代理
        
    if cookies_path:
        ydl_opts_with_cookie['cookiefile'] = cookies_path
    elif os.path.exists("cookies.txt"):
        ydl_opts_with_cookie['cookiefile'] = "cookies.txt"
        
    # 如果有提供或存在 cookie，優先執行階段一 (直連)
    if cookies_path or os.path.exists("cookies.txt"):
        try:
            print("階段一：嘗試使用 Cookie 進行影片直連解析...")
            with YoutubeDL(ydl_opts_with_cookie) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
                print("階段一使用 Cookie 直連解析成功！")
                res = parse_ydl_info(info)
                return res
        except Exception as e:
            err_msg = str(e)
            if "轉檔" in err_msg or "找不到可用的" in err_msg:
                raise e
            print(f"階段一帶 Cookie 解析失敗: {e}。嘗試階段二 Fallback...")
    # 階段二：無 Cookie 解析 (使用 Proxy Fallback)
    try:
        print("階段二：不帶 Cookie 進行 Fallback 代理解析...")
        with YoutubeDL(ydl_opts_no_cookie) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            res = parse_ydl_info(info)
            return res
    except Exception as e2:
        err_msg = str(e2)
        if "processing" in err_msg.lower() or "live stream" in err_msg.lower() or "post-live" in err_msg.lower():
            friendly_msg = "無法解析 YouTube 影片資訊：該影片可能為剛結束的直播，YouTube 正在進行後台轉檔處理（通常需要一些時間才能產生正常影片檔），請稍候再試。"
        elif "找不到可用的視訊串流網址" in err_msg:
            friendly_msg = err_msg
        else:
            friendly_msg = f"無法解析 YouTube 影片資訊: {err_msg}"
        raise HTTPException(status_code=400, detail=friendly_msg)


def run_black_detection(
    stream_url: str,
    video_w: int,
    video_h: int,
    req: AnalyzeRequest,
    duration: float = 0.0,
    min_duration: float = 2.0,
    pix_th: float = 0.15
) -> list[dict]:
    """
    使用 FFmpeg blackdetect 快速掃描整部影片，尋找持續時間 >= min_duration 秒的全黑片段。
    """
    # 優先使用請求中自訂的黑屏偵測參數
    actual_pix_th = req.black_pix_th if req.black_pix_th is not None else pix_th
    actual_min_duration = req.black_duration if req.black_duration is not None else min_duration

    crop_x = int(video_w * req.x_min)
    crop_y = int(video_h * req.y_min)
    crop_w = int(video_w * (req.x_max - req.x_min))
    crop_h = int(video_h * (req.y_max - req.y_min))
    
    crop_x = (crop_x // 2) * 2
    crop_y = (crop_y // 2) * 2
    crop_w = (crop_w // 2) * 2
    crop_h = (crop_h // 2) * 2

    is_network = stream_url.startswith("http://") or stream_url.startswith("https://")
    cmd = [
        'ffmpeg',
        '-loglevel', 'warning',
    ]
    if is_network:
        cmd.extend([
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-rw_timeout', '15000000',
        ])
    cmd.extend([
        '-i', stream_url,
    ])
    if req.scan_duration_limit > 0.0:
        cmd.extend(['-t', str(req.scan_duration_limit)])
    cmd.extend([
        '-vf', f'crop={crop_w}:{crop_h}:{crop_x}:{crop_y},fps=2,blackdetect=d={actual_min_duration}:pix_th={actual_pix_th}',
        '-an',
        '-f', 'null',
        '-'
    ])
    
    # 啟動 FFmpeg 子進程，讀取其 stderr 輸出
    env = os.environ.copy()
    if "http_proxy" in env: del env["http_proxy"]
    if "https_proxy" in env: del env["https_proxy"]
    import threading
    print(f"[run_black_detection] 啟動 FFmpeg 命令: {' '.join(cmd)}")
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore', env=env)
    
    # 估算超時秒數：基礎 180 秒，每 1 小時 (3600 秒) 影片額外給予 120 秒
    timeout_sec = 180.0
    actual_len = duration
    if req.scan_duration_limit > 0.0:
        actual_len = min(duration, req.scan_duration_limit)
    if actual_len > 0.0:
        timeout_sec = max(180.0, 180.0 + (actual_len / 3600.0) * 120.0)

    # 啟動超時定時器，防止第一階段 FFmpeg 執行超時卡死
    def force_kill_black():
        try:
            print(f"[run_black_detection] 【超時警告】偵測到第一階段 FFmpeg 執行超時 ({timeout_sec:.1f} 秒)，強行 kill 進程...")
            process.kill()
        except Exception:
            pass
    timer = threading.Timer(timeout_sec, force_kill_black)
    timer.start()
    
    try:
        black_intervals = []
        # 匹配範例：[blackdetect @ 0x...] black_start:10.5 black_end:15.5 black_duration:5.0
        pattern = re.compile(r'black_start:([\d\.]+)\s+black_end:([\d\.]+)\s+black_duration:([\d\.]+)')
        
        all_stderr_lines = []
        reconnect_fail_count = 0
        while True:
            line = process.stderr.readline()
            if not line:
                break
            line_str = line.strip()
            all_stderr_lines.append(line)
            if len(all_stderr_lines) > 30:
                all_stderr_lines.pop(0)
                
            # 僅輸出與黑屏偵測或連線錯誤相關的重要日誌，避免大量 Late SEI 警告阻塞 I/O
            is_important = "black_start" in line_str or any(k in line_str.lower() for k in ["http error", "forbidden", "reconnect failed"])
            if is_important:
                print(f"[FFmpeg Blackdetect] {line_str}", flush=True)
            
            # 偵測是否被 YouTube 阻擋或重連失敗，主動終止防卡死
            if "http error 403" in line.lower() or "403 forbidden" in line.lower() or "reconnect failed" in line.lower():
                reconnect_fail_count += 1
                if reconnect_fail_count >= 5:
                    try:
                        process.kill()
                    except Exception:
                        pass
                    process.wait()
                    raise HTTPException(
                        status_code=403,
                        detail="與 YouTube 影片伺服器的連線遭拒絕 (HTTP 403 Forbidden)。\n請在 mini-pc 本地提供有效的 cookies.txt 以避開限制。"
                    )
            match = pattern.search(line)
            if match:
                start = float(match.group(1))
                end = float(match.group(2))
                duration = float(match.group(3))
                
                # FFXIV 的滅團黑屏一般落在 4~10 秒之間，因此過濾過長或過短的黑屏以防誤判
                if actual_min_duration <= duration <= 12.0:
                    black_intervals.append({
                        'start': start,
                        'end': end,
                        'duration': duration
                    })
                    
        process.wait()
        if process.returncode != 0:
            # 排除 FFmpeg 啟動宣告（banner）的行以防日誌內容被截斷
            filtered_lines = [
                l for l in all_stderr_lines 
                if not any(k in l for k in ["ffmpeg version", "built with", "configuration:", "libavutil", "libavcodec", "libavformat", "libavdevice", "libavfilter", "libswscale", "libswresample", "libpostproc"])
            ]
            last_logs = "".join(filtered_lines[-15:])
            print(f"[run_black_detection] FFmpeg 異常退出 (code: {process.returncode})。最後日誌:\n{last_logs}")
            raise HTTPException(
                status_code=500,
                detail=f"第一階段 FFmpeg 黑屏偵測失敗 (Exit Code: {process.returncode})，請確認代理或直鏈是否可用。最後日誌:\n{last_logs}"
            )
        return black_intervals
    finally:
        timer.cancel()
        try:
            process.kill()
        except Exception:
            pass

def verify_restart_text(
    stream_url: str,
    video_w: int,
    video_h: int,
    start_time: float,
    template_img: np.ndarray,
    req: AnalyzeRequest,
    is_debug: bool = False
) -> tuple[bool, float, float]:
    """
    在黑屏結束後 30 秒的區間內，使用 FFmpeg 串流裁切中央偵測區並進行多尺度模板匹配，尋找 RESTART 字樣。
    """
    # 計算裁切區域坐標 (動態適應解析度)
    crop_x = int(video_w * req.x_min)
    crop_y = int(video_h * req.y_min)
    crop_w = int(video_w * (req.x_max - req.x_min))
    crop_h = int(video_h * (req.y_max - req.y_min))
    
    # 確保裁切坐標為偶數，符合 FFmpeg 的 crop 濾鏡要求
    crop_x = (crop_x // 2) * 2
    crop_y = (crop_y // 2) * 2
    crop_w = (crop_w // 2) * 2
    crop_h = (crop_h // 2) * 2

    target_w = crop_w
    target_h = int(crop_h * 0.91)
    
    # 調整模板大小以符合目前的影片解析度
    resized_template = cv2.resize(template_img, (target_w, target_h))
    
    # 建立多個尺度 (0.9, 1.0, 1.1) 以應對些微的比例差異
    scales = [0.9, 1.0, 1.1]
    
    # 使用 FFmpeg 只讀取特定時間段 [start_time, start_time + 30]，每秒 1 幀，並自動裁切
    is_network = stream_url.startswith("http://") or stream_url.startswith("https://")
    ffmpeg_cmd = [
        'ffmpeg',
        '-loglevel', 'error', # 減少 stderr 的輸出量，防微杜漸
        '-ss', str(start_time),
    ]
    if is_network:
        ffmpeg_cmd.extend([
            '-reconnect', '1',
            '-reconnect_streamed', '1',
            '-reconnect_delay_max', '5',
            '-rw_timeout', '10000000', # 10秒 rw_timeout
        ])
    ffmpeg_cmd.extend([
        '-i', stream_url,
        '-t', '30',
        '-filter:v', f'crop={crop_w}:{crop_h}:{crop_x}:{crop_y},fps=1',
        '-f', 'image2pipe',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'bgr24',
        'pipe:1'
    ])
    
    frame_size = crop_w * crop_h * 3
    env = os.environ.copy()
    if "http_proxy" in env: del env["http_proxy"]
    if "https_proxy" in env: del env["https_proxy"]
    import threading
    
    print(f"[verify_restart_text] 正在啟動 FFmpeg，時間點: {start_time}s...")
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_size * 5, env=env)
    print(f"[verify_restart_text] FFmpeg 已啟動，PID: {process.pid}")
    
    # 啟動 15 秒超時定時器，防止網路連線卡住導致 stdout.read 阻塞
    def force_kill():
        try:
            print(f"[verify_restart_text] 【超時警告】偵測到影片段落 {start_time}s 的畫面下載超時，強行 kill 進程...", flush=True)
            process.kill()
        except Exception as e:
            print(f"[verify_restart_text] 強殺進程失敗: {e}", flush=True)
    timer = threading.Timer(15.0, force_kill)
    timer.start()
    print(f"[verify_restart_text] 15秒超時定時器已啟動。")
    
    match_found = False
    best_score = 0.0
    detected_at = -1.0
    
    try:
        frame_idx = 0
        print(f"[verify_restart_text] 開始讀取畫面幀...")
        while True:
            raw_frame = process.stdout.read(frame_size)
            if len(raw_frame) != frame_size:
                print(f"[verify_restart_text] 讀取結束或中斷，已讀取 {frame_idx} 幀 (最後大小: {len(raw_frame)})")
                break
            
            # 每 5 幀印一次日誌，提供偵錯資訊
            if frame_idx % 5 == 0:
                print(f"[verify_restart_text] 正在處理第 {frame_idx} 幀...")
                
            frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((crop_h, crop_w, 3))
            
            # HSV 金色過濾
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            lower_gold = np.array([15, 80, 150])
            upper_gold = np.array([28, 255, 255])
            mask_frame = cv2.inRange(hsv, lower_gold, upper_gold)
            gold_pixels = cv2.countNonZero(mask_frame)
            
            # 動態計算金色像素門檻 (大於 crop 區域面積 of 1.3%)
            pixel_threshold = int(crop_w * crop_h * 0.013)
            
            if is_debug:
                print(f"[Debug] 時間點 {start_time}s 第 {frame_idx} 幀: 金色像素數={gold_pixels}, 門檻值={pixel_threshold}")
                
            if gold_pixels >= pixel_threshold:
                if is_debug:
                    cv2.imwrite(f"debug_wipes/wipe_{start_time}_f{frame_idx}_orig.png", frame)
                    cv2.imwrite(f"debug_wipes/wipe_{start_time}_f{frame_idx}_mask.png", mask_frame)
                    
                # 進行多尺度遮罩模板匹配
                for scale in scales:
                    sw = int(target_w * scale)
                    sh = int(target_h * scale)
                    
                    # 防止超出邊界
                    if sw > crop_w or sh > crop_h:
                        continue
                        
                    scaled_tpl = cv2.resize(resized_template, (sw, sh))
                    mask_tpl = cv2.inRange(cv2.cvtColor(scaled_tpl, cv2.COLOR_BGR2HSV), lower_gold, upper_gold)
                    
                    res = cv2.matchTemplate(mask_frame, mask_tpl, cv2.TM_CCOEFF_NORMED)
                    _, max_val, _, _ = cv2.minMaxLoc(res)
                    
                    if is_debug:
                        print(f"[Debug] 時間點 {start_time}s 第 {frame_idx} 幀 (尺度 {scale}): 比對得分={max_val:.4f}")
                        cv2.imwrite(f"debug_wipes/wipe_{start_time}_f{frame_idx}_tpl_s{scale}.png", mask_tpl)
                        
                    if max_val > best_score:
                        best_score = max_val
                        
                    # 遮罩匹配分數以 0.45 作為可靠匹配閥值
                    actual_threshold = 0.45 if req.threshold == 0.65 else req.threshold
                    if max_val >= actual_threshold:
                        match_found = True
                        detected_at = start_time + frame_idx
                        print(f"[verify_restart_text] 第 {frame_idx} 幀匹配成功！分數: {max_val:.2f} (閥值: {actual_threshold})")
                        break
                        
            if match_found:
                break
            frame_idx += 1
    finally:
        print(f"[verify_restart_text] 進入 finally 區塊，開始回收資源...")
        timer.cancel()
        print(f"[verify_restart_text] 定時器已取消。")
        try:
            print(f"[verify_restart_text] 強制殺死 FFmpeg 進程 (PID: {process.pid})...")
            process.kill()
        except Exception:
            pass
        print(f"[verify_restart_text] 正在等待進程結束 (process.wait)...")
        process.wait()
        print(f"[verify_restart_text] FFmpeg 進程已結束，Exit Code: {process.returncode}")
        
    return match_found, detected_at, best_score

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_video(request: AnalyzeRequest):
    # 偵測是否啟用除錯模式
    is_debug = False
    if request.debug is True:
        is_debug = True
    elif os.environ.get("DEBUG_MODE", "").lower() in ("true", "1"):
        is_debug = True
    elif os.path.exists(".debug"):
        is_debug = True

    if is_debug:
        print("除錯模式已啟用，將會保留 Wipe 判斷過程的圖片與日誌。")
        debug_dir = "debug_wipes"
        os.makedirs(debug_dir, exist_ok=True)
        for f in os.listdir(debug_dir):
            if f.endswith(".png"):
                try:
                    os.remove(os.path.join(debug_dir, f))
                except Exception:
                    pass

    # 0. 偵測 Node.js 環境狀態
    try:
        node_ver = subprocess.check_output(["node", "-v"], stderr=subprocess.DEVNULL).decode().strip()
        print(f"Node.js 執行環境偵測成功，版本: {node_ver}")
    except Exception as e:
        print(f"未偵測到 Node.js 執行環境: {e}")

    # 1. 取得並驗證模板圖片
    template_path = request.template_name
    gcs_bucket = os.environ.get("GCS_BUCKET_NAME")
    
    # 如果本地找不到模板，且有配置 GCS_BUCKET_NAME，嘗試從 GCS 下載至 /tmp
    if not os.path.exists(template_path):
        if gcs_bucket:
            temp_path = os.path.join("/tmp", template_path)
            print(f"本地找不到模板 [{template_path}]，嘗試自 GCS Bucket [{gcs_bucket}] 下載...")
            if download_from_gcs(gcs_bucket, template_path, temp_path):
                template_path = temp_path

    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"找不到指定的模板圖片: {template_path}，本地或 GCS 均無此檔案。")
        
    template_img = cv2.imread(template_path)
    if template_img is None:
        raise HTTPException(status_code=400, detail=f"無法成功解碼圖片檔案: {template_path}")
        
    # 處理動態傳入的 Cookie
    cookies_path = None
    if request.cookies_content:
        import tempfile
        temp_cookie_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt', encoding='utf-8')
        temp_cookie_file.write(request.cookies_content)
        temp_cookie_file.close()
        cookies_path = temp_cookie_file.name
    elif gcs_bucket:
        # 如果請求沒傳，但有設定 GCS_BUCKET_NAME，嘗試從 GCS 下載 cookies.txt 到 /tmp
        dest_cookie_path = os.path.join("/tmp", "cookies.txt")
        print(f"嘗試自 GCS Bucket [{gcs_bucket}] 下載 cookies.txt...")
        if download_from_gcs(gcs_bucket, "cookies.txt", dest_cookie_path):
            cookies_path = dest_cookie_path
        
    # 支援直接分析 GCS Bucket 中的影片檔案 (gs://)
    if request.youtube_url.startswith("gs://"):
        print(f"偵測到 GCS 儲存桶影片路徑: {request.youtube_url}，正在為其產生 Signed URL...")
        gs_match = re.match(r"gs://([^/]+)/(.+)", request.youtube_url)
        if not gs_match:
            raise HTTPException(status_code=400, detail="無效的 GCS 影片路徑。格式應為：gs://bucket_name/path/to/video.mp4")
        
        tgt_bucket = gs_match.group(1)
        tgt_blob = gs_match.group(2)
        
        try:
            client = storage.Client()
            bucket = client.bucket(tgt_bucket)
            blob = bucket.blob(tgt_blob)
            if not blob.exists():
                raise HTTPException(status_code=404, detail=f"儲存桶中找不到此影片檔: {request.youtube_url}")
                
            import datetime
            # 產生 1 小時有效的簽章直鏈網址供 FFmpeg 直接讀取
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=datetime.timedelta(hours=1),
                method="GET"
            )
            stream_url = signed_url
            video_w = 640  # GCS 直鏈影片先提供預設尺寸
            video_h = 360
            duration = 0.0
            title = tgt_blob.split("/")[-1]
            print(f"成功為 GCS 影片產生 Signed URL。檔名: {title}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"產生 GCS Signed URL 失敗: {str(e)}")
            
    elif is_direct_stream_url(request.youtube_url):
        print("偵測到傳入的已是視訊直鏈，跳過 yt-dlp 解析步驟。")
        stream_url = request.youtube_url
        if os.path.exists(stream_url):
            info = get_local_video_info(stream_url)
            video_w = info["width"]
            video_h = info["height"]
            duration = info["duration"]
            title = os.path.basename(stream_url)
            print(f"成功自本地影片獲取屬性: 時長: {duration}秒, 解析度: {video_w}x{video_h}")
        else:
            video_w = 640
            video_h = 360
            duration = 0.0
            title = "Direct Video Stream"
            
        if request.video_title:
            title = request.video_title
        if request.video_duration is not None and request.video_duration > 0.0:
            duration = request.video_duration
            
        if gcs_bucket and template_path.startswith("/tmp") and os.path.exists(template_path):
            try:
                os.remove(template_path)
            except Exception:
                pass
    else:
        try:
            # 2. 獲取 YouTube 影片直鏈與中介資料
            print(f"正在解析影片: {request.youtube_url}")
            video_info = get_youtube_video_info(request.youtube_url, cookies_path=cookies_path)
            stream_url = video_info['stream_url']
            video_w = video_info['width']
            video_h = video_info['height']
            duration = video_info['duration']
            title = video_info['title']
        finally:
            # 確保清理 GCS 下載到 /tmp 的臨時模板圖片
            if gcs_bucket and template_path.startswith("/tmp") and os.path.exists(template_path):
                try:
                    os.remove(template_path)
                except Exception:
                    pass
    
    print(f"解析成功！標題: {title}，時長: {duration}秒，解析度: {video_w}x{video_h}")
    
    # 建立臨時影片下載機制 (僅針對 YouTube 影片)
    temp_video_path = None
    if not request.youtube_url.startswith("gs://") and not is_direct_stream_url(request.youtube_url):
        try:
            print("正在下載 YouTube 影片至本地以進行高速分析...")
            import tempfile
            import time as py_time
            temp_dir = tempfile.gettempdir()
            temp_file_name = f"ffxiv_ana_temp_{int(py_time.time())}.mp4"
            temp_video_path = os.path.join(temp_dir, temp_file_name)
            
            # 使用與解析相同的 ydl_opts 下載影片
            ydl_opts_download = {
                'format': 'bestvideo[height<=360][protocol*=m3u8]/best[height<=360][protocol*=m3u8]/bestvideo[height<=360][protocol!*=dash]/worstvideo/worst',
                'quiet': True,
                'no_warnings': True,
                'outtmpl': temp_video_path,
                'extractor_args': {
                    'youtube': {
                        'client': ['ios', 'android'],
                        'construct_dash': False
                    }
                }
            }
            if cookies_path:
                ydl_opts_download['cookiefile'] = cookies_path
            elif os.path.exists("cookies.txt"):
                ydl_opts_download['cookiefile'] = "cookies.txt"
                
            with YoutubeDL(ydl_opts_download) as ydl:
                ydl.download([request.youtube_url])
                
            if os.path.exists(temp_video_path) and os.path.getsize(temp_video_path) > 0:
                print("影片下載完成，切換分析路徑至本地檔案！")
                stream_url = temp_video_path
                # 重新讀取本地下載影片的真實解析度，防止解析度與直鏈不一致導致裁切偏離
                local_info = get_local_video_info(stream_url)
                video_w = local_info["width"]
                video_h = local_info["height"]
                print(f"本地暫存影片真實尺寸為: {video_w}x{video_h}")
            else:
                print("影片下載失敗，退回流式解析模式。")
                temp_video_path = None
        except Exception as e_dl:
            print(f"本地下載嘗試失敗 ({e_dl})，退回流式解析模式。")
            temp_video_path = None

    try:
        if is_debug:
            try:
                print(f"[Debug] 嘗試讀取影片第一幀...")
                cap = cv2.VideoCapture(stream_url)
                if cap.isOpened():
                    ret, frame_0 = cap.read()
                    if ret and frame_0 is not None:
                        cv2.imwrite("debug_wipes/first_frame.png", frame_0)
                        print(f"[Debug] 成功儲存第一幀畫面至 debug_wipes/first_frame.png")
                    else:
                        print(f"[Debug] 無法讀取影片第一幀畫面")
                    cap.release()
                else:
                    print(f"[Debug] 無法以 OpenCV 開啟 stream_url: {stream_url}")
            except Exception as e_debug:
                print(f"[Debug] 儲存第一幀失敗: {e_debug}")

        # 3. 第一階段：快速全黑偵測 (FFmpeg blackdetect)
        print("開始執行全黑影格偵測...")
        black_intervals = run_black_detection(
            stream_url=stream_url,
            video_w=video_w,
            video_h=video_h,
            req=request,
            duration=duration
        )
        print(f"共偵測到 {len(black_intervals)} 個潛在黑屏區間。")
        
        # 4. 第二階段：對每個黑屏後區間進行 RESTART 文字驗證
        wipes = []
        wipe_count = 0
        
        for idx, interval in enumerate(black_intervals):
            black_end = interval['end']
            print(f"[{idx+1}/{len(black_intervals)}] 正在驗證時間點 {black_end}s 後的畫面...")
            
            match_found, detected_at, score = verify_restart_text(
                stream_url=stream_url,
                video_w=video_w,
                video_h=video_h,
                start_time=black_end,
                template_img=template_img,
                req=request,
                is_debug=is_debug
            )
            
            if match_found:
                wipe_count += 1
                wipes.append(WipeEvent(
                    wipe_number=wipe_count,
                    black_screen_start=interval['start'],
                    black_screen_end=interval['end'],
                    restart_word_detected_at=detected_at,
                    similarity_score=float(score)
                ))
                print(f"-> 偵測到 Wipe #{wipe_count}！時間: {detected_at}s (相似度: {score:.2f})")
            else:
                print(f"-> 驗證未通過，最高相似度為: {score:.2f}")
                
        return AnalyzeResponse(
            status="success",
            video_title=title,
            video_duration_seconds=duration,
            wipes=wipes
        )
    finally:
        # 確保清理本地臨時影片檔
        if temp_video_path and os.path.exists(temp_video_path):
            try:
                os.remove(temp_video_path)
                print("成功清理本地臨時影片檔。")
            except Exception as e_clean:
                print(f"清理本地臨時影片檔失敗: {e_clean}")
        # 確保清理臨時 Cookie 檔
        if cookies_path and os.path.exists(cookies_path):
            try:
                os.remove(cookies_path)
                print("成功清理臨時 Cookie 檔。")
            except Exception as e_clean:
                print(f"清理臨時 Cookie 檔失敗: {e_clean}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
