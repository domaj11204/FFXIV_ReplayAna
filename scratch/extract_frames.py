import os
import sys
import subprocess
import cv2
import numpy as np
import urllib.request
import json

def get_youtube_video_info_144p(youtube_url, cookies_path=None):
    from yt_dlp import YoutubeDL
    ydl_opts = {
        'format': 'worstvideo/worst', # 強制最低畫質 144p
        'quiet': True,
        'no_warnings': True,
        'extractor_args': {
            'youtube': {
                'client': ['ios', 'android'],
                'construct_dash': False
            }
        }
    }
    if cookies_path:
        ydl_opts['cookiefile'] = cookies_path
        
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        formats = info.get('formats', [])
        stream_url = None
        for f in formats:
            if f.get('acodec') == 'none' or f.get('vcodec') != 'none':
                stream_url = f.get('url')
        if not stream_url:
            stream_url = info.get('url')
        return {
            'stream_url': stream_url,
            'width': info.get('width', 256),
            'height': info.get('height', 144)
        }

def main():
    print("===================================================")
    print("  FFXIV Wipe Analyzer - 1:06:01 144p 畫質診斷腳本")
    print("===================================================")
    
    youtube_url = "https://www.youtube.com/live/TDh49Hc47Ss"
    start_time = 3958.0  # 1:05:58
    duration = 6.0       # 截取 6 秒 (到 1:06:04)
    fps = 5              # 每秒 5 幀
    
    # 讀取本地 Cookie
    cookies_path = None
    for path in ["cookies.txt", "www.youtube.com_cookies.txt"]:
        if os.path.exists(path):
            cookies_path = path
            print(f"使用 Cookie 檔案: {path}")
            break
            
    try:
        # 1. 解析影片直鏈
        print("正在以 144p 格式解析影片直鏈...")
        info = get_youtube_video_info_144p(youtube_url, cookies_path)
        stream_url = info['stream_url']
        print(f"解析成功！目標解析度: {info['width']}x{info['height']}")
        
        # 建立與清理舊 144p 圖片
        debug_dir = "debug_wipes"
        if os.path.exists(debug_dir):
            for f in os.listdir(debug_dir):
                if f.startswith("diag_orig_144p_") or f.startswith("diag_crop_144p_"):
                    try:
                        os.remove(os.path.join(debug_dir, f))
                    except Exception:
                        pass
        os.makedirs(debug_dir, exist_ok=True)
        
        # 2. 使用 FFmpeg 直接輸出 144p 畫面
        print(f"正在透過 FFmpeg 將 144p 畫面輸出至 {debug_dir} 目錄下...")
        temp_pattern = os.path.join(debug_dir, "diag_orig_temp_144p_%03d.png")
        cmd_orig = [
            'ffmpeg', '-loglevel', 'error',
            '-ss', str(start_time),
            '-i', stream_url,
            '-t', str(duration),
            '-vf', f'fps={fps}',
            temp_pattern
        ]
        
        subprocess.run(cmd_orig, check=True)
        
        # 3. 讀取並分析 144p PNG
        print("\n正在對 144p 畫面進行裁切與亮度分析...")
        temp_files = sorted([f for f in os.listdir(debug_dir) if f.startswith("diag_orig_temp_144p_") and f.endswith(".png")])
        
        for idx, filename in enumerate(temp_files):
            filepath = os.path.join(debug_dir, filename)
            frame = cv2.imread(filepath)
            if frame is None:
                continue
                
            real_h, real_w, _ = frame.shape
            
            # 裁切區域比例保持一致
            crop_x = int(real_w * 0.30)
            crop_y = int(real_h * 0.25)
            crop_w = int(real_w * (0.70 - 0.30))
            crop_h = int(real_h * (0.50 - 0.25))
            
            crop_x = (crop_x // 2) * 2
            crop_y = (crop_y // 2) * 2
            crop_w = (crop_w // 2) * 2
            crop_h = (crop_h // 2) * 2
            
            crop_frame = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
            timestamp_sec = start_time + (idx / fps)
            
            # 儲存 144p 裁切圖片
            crop_filename = f"diag_crop_144p_{timestamp_sec:.2f}s.png"
            cv2.imwrite(os.path.join(debug_dir, crop_filename), crop_frame)
            
            # 儲存 144p 原始全幅圖片
            orig_filename = f"diag_orig_144p_{timestamp_sec:.2f}s.png"
            os.rename(filepath, os.path.join(debug_dir, orig_filename))
            
            # 計算黑像素比例
            gray = cv2.cvtColor(crop_frame, cv2.COLOR_BGR2GRAY)
            black_pixels = np.sum(gray < 38.25)
            total_pixels = crop_w * crop_h
            black_ratio = black_pixels / total_pixels
            
            is_black_frame = black_ratio >= 0.98
            status_str = "【黑屏】" if is_black_frame else "【非黑屏】"
            
            print(f"時間點: {timestamp_sec:.2f}s (1:{int(timestamp_sec//60):02d}:{int(timestamp_sec%60):02d}) | "
                  f"黑像素比例: {black_ratio*100:.2f}% | 判定: {status_str}")
            
        print(f"\n診斷完成！已將 144p 畫面儲存至 {debug_dir}/ 目錄下。")
        print("檔名為:")
        print(f" - 原始全幅 (144p): [diag_orig_144p_3961.00s.png](file:///d:/Proj/ffxiv_rpana/{debug_dir}/diag_orig_144p_3961.00s.png)")
        print(f" - 裁切偵測 (144p): [diag_crop_144p_3961.00s.png](file:///d:/Proj/ffxiv_rpana/{debug_dir}/diag_crop_144p_3961.00s.png)")
        
    except Exception as e:
        print(f"執行診斷失敗: {e}")

if __name__ == "__main__":
    main()
