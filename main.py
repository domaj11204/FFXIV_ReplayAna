import os
import re
import subprocess
import cv2
import numpy as np
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from yt_dlp import YoutubeDL

app = FastAPI(
    title="FFXIV Wipe Analyzer API",
    description="分析 FFXIV 影片並偵測滅團 (Wipe) 時間軸之 API",
    version="1.0.0"
)

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

def get_youtube_video_info(youtube_url: str) -> dict:
    """
    使用 yt-dlp 取得影片的直鏈網址、標題與尺寸資訊。
    為加速處理，優先取得低解析度 (如 360p) 的影片唯視訊串流，以節省下載流量與解碼效能。
    """
    ydl_opts = {
        'format': 'bestvideo[height<=360][protocol*=m3u8]/best[height<=360][protocol*=m3u8]/bestvideo[height<=360]/worstvideo/worst',
        'quiet': True,
        'no_warnings': True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            
            # 優先從單一 url 欄位讀取
            stream_url = info.get('url')
            
            # 若無單一 url (例如合併格式)，從 requested_formats 尋找視訊串流
            if not stream_url and 'requested_formats' in info:
                for f in info['requested_formats']:
                    if f.get('vcodec') != 'none' and f.get('url'):
                        stream_url = f['url']
                        break
                        
            if not stream_url:
                raise ValueError("找不到可用的視訊串流網址。")
                
            return {
                "stream_url": stream_url,
                "title": info.get('title', 'Unknown Title'),
                "duration": info.get('duration', 0.0),
                "width": info.get('width', 640),
                "height": info.get('height', 360),
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"無法解析 YouTube 影片資訊: {str(e)}")


def run_black_detection(
    stream_url: str,
    video_w: int,
    video_h: int,
    req: AnalyzeRequest,
    min_duration: float = 3.0,
    pix_th: float = 0.15
) -> list[dict]:
    """
    使用 FFmpeg blackdetect 快速掃描整部影片，尋找持續時間 >= min_duration 秒的全黑片段。
    為了防止實況主視訊鏡頭或覆蓋 UI (如聊天室、框架) 影響全黑判定，本步驟同樣會裁切至中央感興趣區域再進行偵測。
    """
    crop_x = int(video_w * req.x_min)
    crop_y = int(video_h * req.y_min)
    crop_w = int(video_w * (req.x_max - req.x_min))
    crop_h = int(video_h * (req.y_max - req.y_min))
    
    crop_x = (crop_x // 2) * 2
    crop_y = (crop_y // 2) * 2
    crop_w = (crop_w // 2) * 2
    crop_h = (crop_h // 2) * 2

    cmd = [
        'ffmpeg',
        '-reconnect', '1',
        '-reconnect_streamed', '1',
        '-reconnect_delay_max', '5',
        '-i', stream_url,
    ]
    if req.scan_duration_limit > 0.0:
        cmd.extend(['-t', str(req.scan_duration_limit)])
    cmd.extend([
        '-vf', f'crop={crop_w}:{crop_h}:{crop_x}:{crop_y},fps=2,blackdetect=d={min_duration}:pix_th={pix_th}',
        '-an',
        '-f', 'null',
        '-'
    ])
    
    # 啟動 FFmpeg 子進程，讀取其 stderr 輸出
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
    
    black_intervals = []
    # 匹配範例：[blackdetect @ 0x...] black_start:10.5 black_end:15.5 black_duration:5.0
    pattern = re.compile(r'black_start:([\d\.]+)\s+black_end:([\d\.]+)\s+black_duration:([\d\.]+)')
    
    while True:
        line = process.stderr.readline()
        if not line:
            break
        match = pattern.search(line)
        if match:
            start = float(match.group(1))
            end = float(match.group(2))
            duration = float(match.group(3))
            
            # FFXIV 的滅團黑屏一般落在 4~10 秒之間，因此過濾過長或過短的黑屏以防誤判
            if 3.0 <= duration <= 12.0:
                black_intervals.append({
                    'start': start,
                    'end': end,
                    'duration': duration
                })
                
    process.wait()
    return black_intervals

def verify_restart_text(
    stream_url: str,
    video_w: int,
    video_h: int,
    start_time: float,
    template_img: np.ndarray,
    req: AnalyzeRequest
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

    # 計算模板在該解析度下的預期大小
    # 原始截圖為 1024x575，預設模板大小為 409x131
    # 模板佔原圖寬度比例為 409/1024 = 39.94%
    # 模板佔原圖高度比例為 131/575 = 22.78%
    # 原始 crop 區域高為 575 * 0.25 = 143.75
    # 模板高度佔 crop 高度比例為 131/144 = 91%
    target_w = crop_w
    target_h = int(crop_h * 0.91)
    
    # 調整模板大小以符合目前的影片解析度
    resized_template = cv2.resize(template_img, (target_w, target_h))
    
    # 建立多個尺度 (0.9, 1.0, 1.1) 以應對些微的比例差異
    scales = [0.9, 1.0, 1.1]
    
    # 使用 FFmpeg 只讀取特定時間段 [start_time, start_time + 30]，每秒 1 幀，並自動裁切
    ffmpeg_cmd = [
        'ffmpeg',
        '-ss', str(start_time),
        '-reconnect', '1',
        '-reconnect_streamed', '1',
        '-reconnect_delay_max', '5',
        '-i', stream_url,
        '-t', '30',
        '-filter:v', f'crop={crop_w}:{crop_h}:{crop_x}:{crop_y},fps=1',
        '-f', 'image2pipe',
        '-vcodec', 'rawvideo',
        '-pix_fmt', 'bgr24',
        'pipe:1'
    ]
    
    frame_size = crop_w * crop_h * 3
    process = subprocess.Popen(ffmpeg_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_size * 5)
    
    match_found = False
    best_score = 0.0
    detected_at = -1.0
    
    frame_idx = 0
    while True:
        raw_frame = process.stdout.read(frame_size)
        if len(raw_frame) != frame_size:
            break
        
        frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((crop_h, crop_w, 3))
        
        # HSV 金色過濾
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower_gold = np.array([15, 80, 150])
        upper_gold = np.array([28, 255, 255])
        mask_frame = cv2.inRange(hsv, lower_gold, upper_gold)
        gold_pixels = cv2.countNonZero(mask_frame)
        
        # 動態計算金色像素門檻 (大於 crop 區域面積的 1.3%)
        pixel_threshold = int(crop_w * crop_h * 0.013)
        
        if gold_pixels >= pixel_threshold:
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
                
                if max_val > best_score:
                    best_score = max_val
                    
                # 遮罩匹配分數以 0.45 作為可靠匹配閥值，若 req.threshold 仍為預設的 0.65 則改用 0.45
                actual_threshold = 0.45 if req.threshold == 0.65 else req.threshold
                if max_val >= actual_threshold:
                    match_found = True
                    detected_at = start_time + frame_idx
                    break
                    
        if match_found:
            break
            
        frame_idx += 1
        
    process.terminate()
    process.wait()
    
    return match_found, detected_at, best_score

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_video(request: AnalyzeRequest):
    # 1. 驗證模板圖片是否存在
    template_path = request.template_name
    if not os.path.exists(template_path):
        raise HTTPException(status_code=404, detail=f"找不到指定的模板圖片: {template_path}，請先上傳圖片。")
        
    template_img = cv2.imread(template_path)
    if template_img is None:
        raise HTTPException(status_code=400, detail=f"無法成功解碼圖片檔案: {template_path}")
        
    # 2. 獲取 YouTube 影片直鏈與中介資料
    print(f"正在解析影片: {request.youtube_url}")
    video_info = get_youtube_video_info(request.youtube_url)
    stream_url = video_info['stream_url']
    video_w = video_info['width']
    video_h = video_info['height']
    duration = video_info['duration']
    title = video_info['title']
    
    print(f"解析成功！標題: {title}，時長: {duration}秒，解析度: {video_w}x{video_h}")
    
    # 3. 第一階段：快速全黑偵測 (FFmpeg blackdetect)
    print("開始執行全黑影格偵測...")
    black_intervals = run_black_detection(
        stream_url=stream_url,
        video_w=video_w,
        video_h=video_h,
        req=request
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
            req=request
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=True)
