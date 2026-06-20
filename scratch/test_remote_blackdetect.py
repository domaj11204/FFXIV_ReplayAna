import yt_dlp
import subprocess
import re
import sys
import os

def main():
    youtube_url = "https://www.youtube.com/watch?v=zG68yxff90s"
    print("1. 正在解析影片 metadata...")
    
    # 帶 Cookie 且指定與階段二相同的 ios/android 客戶端
    ydl_opts = {
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
    
    # 如果本地有 cookies.txt 則載入
    if os.path.exists("cookies.txt"):
        ydl_opts["cookiefile"] = "cookies.txt"
        print("載入本地 cookies.txt")
        
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(youtube_url, download=False)
        print("標題:", info.get("title"))
        print("時長:", info.get("duration"))
        video_w = info.get("width", 640)
        video_h = info.get("height", 360)
        print(f"解析度: {video_w}x{video_h}")
        
    temp_video_path = "temp_test_video.mp4"
    if os.path.exists(temp_video_path):
        os.remove(temp_video_path)
        
    print("2. 正在下載前 300 秒影片 (以防過大)...")
    ydl_opts_download = {
        'format': 'bestvideo[height<=360][protocol*=m3u8]/best[height<=360][protocol*=m3u8]/bestvideo[height<=360][protocol!*=dash]/worstvideo/worst',
        'quiet': True,
        'no_warnings': True,
        'outtmpl': temp_video_path
    }
    if os.path.exists("cookies.txt"):
        ydl_opts_download["cookiefile"] = "cookies.txt"
        
    # 限時下載前 300 秒，直接用 download 加上 postprocessor 或是 yt-dlp 的 --download-sections
    # 這裡我們為了省時，可以直接抓取 m3u8，但我們用 ydl 下載
    # 為了簡化，我們下載整部影片看看？這部影片 4961 秒，300MiB 大概 30 秒下載完。我們直接下載整部！
    with yt_dlp.YoutubeDL(ydl_opts_download) as ydl:
        ydl.download([youtube_url])
        
    print("下載完成，檔案大小:", os.path.getsize(temp_video_path))
    
    print("3. 執行 FFmpeg 黑屏偵測...")
    crop_x = int(video_w * 0.30)
    crop_y = int(video_h * 0.25)
    crop_w = int(video_w * 0.40)
    crop_h = int(video_h * 0.25)
    crop_x = (crop_x // 2) * 2
    crop_y = (crop_y // 2) * 2
    crop_w = (crop_w // 2) * 2
    crop_h = (crop_h // 2) * 2
    
    cmd = [
        'ffmpeg',
        '-loglevel', 'info',  # 改用 info 取得更多日誌
        '-i', temp_video_path,
        '-vf', f'crop={crop_w}:{crop_h}:{crop_x}:{crop_y},fps=2,blackdetect=d=3.0:pix_th=0.15',
        '-an',
        '-f', 'null',
        '-'
    ]
    
    process = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
    
    print("FFmpeg 執行中...")
    while True:
        line = process.stderr.readline()
        if not line:
            break
        line_strip = line.strip()
        if "blackdetect" in line_strip or "Parsed_blackdetect" in line_strip or "error" in line_strip.lower() or "warning" in line_strip.lower():
            print("FFMPEG LOG:", line_strip)
            
    process.wait()
    print("FFmpeg 執行結束，Exit Code:", process.returncode)
    
    if os.path.exists(temp_video_path):
        os.remove(temp_video_path)

if __name__ == "__main__":
    main()
