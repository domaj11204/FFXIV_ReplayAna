import sys
import os
import httpx
import json

def test_analyze():
    # 確保切換到專案根目錄
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(project_root)
    
    print("===================================================")
    print("  FFXIV Wipe Analyzer - 本地解析測試腳本")
    print("===================================================")
    
    # 預設測試的影片網址 (一個著名的 FFXIV Wipe 影片)
    default_url = "https://www.youtube.com/watch?v=zG68yxff90s"
    youtube_url = input(f"請輸入要測試的 YouTube 影片網址 [預設: {default_url}]: ").strip()
    if not youtube_url:
        youtube_url = default_url
        
    # 讀取本地的 Cookie 內容以防 Bot 檢測
    cookies_content = None
    cookie_paths = ["www.youtube.com_cookies.txt", "cookies.txt"]
    for path in cookie_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cookies_content = f.read()
                    print(f"已讀取本地 Cookie 檔案: {path}")
                    break
            except Exception as e:
                print(f"讀取 {path} 失敗: {e}")
                
    # 詢問是否啟用除錯模式
    debug_input = input("是否啟用除錯模式以保留 Wipe 判斷圖片? (y/N): ").strip().lower()
    debug_mode = debug_input in ("y", "yes")

    # 詢問是否自訂掃描區間
    custom_range = input("是否設定自訂掃描時間區間? (y/N) [預設: No]: ").strip().lower()
    scan_start_offset = 0.0
    scan_duration_limit = 0.0
    if custom_range in ("y", "yes"):
        try:
            start_in = input("請輸入掃描起始偏移秒數 (秒) [預設 0.0]: ").strip()
            if start_in:
                scan_start_offset = float(start_in)
            limit_in = input("請輸入掃描長度限制 (秒，0.0 為不限制) [預設 0.0]: ").strip()
            if limit_in:
                scan_duration_limit = float(limit_in)
        except ValueError:
            print("輸入格式錯誤，將使用預設區間。")
    else:
        # 預設維持原本的前 10 分鐘限制以節省時間
        scan_duration_limit = 600.0

    # 詢問是否自訂黑屏偵測閥值 (便於本地除錯)
    custom_black = input("是否設定自訂的黑屏偵測參數? (y/N) [預設: No]: ").strip().lower()
    black_pix_th = None
    black_duration = None
    if custom_black in ("y", "yes"):
        try:
            th_in = input("請輸入黑屏像素閾值 (0.0~1.0) [預設 0.15]: ").strip()
            if th_in:
                black_pix_th = float(th_in)
            dur_in = input("請輸入最小黑屏持續時間 (秒) [預設 3.0]: ").strip()
            if dur_in:
                black_duration = float(dur_in)
        except ValueError:
            print("輸入格式錯誤，將使用預設參數。")

    # 準備發送給本地後端 API 的 Payload
    payload = {
        "youtube_url": youtube_url,
        "template_name": "restart_template.png",
        "threshold": 0.65,
        "x_min": 0.30,
        "x_max": 0.70,
        "y_min": 0.25,
        "y_max": 0.50,
        "scan_start_offset": scan_start_offset,
        "scan_duration_limit": scan_duration_limit,
        "debug": debug_mode
    }
    if black_pix_th is not None:
        payload["black_pix_th"] = black_pix_th
    if black_duration is not None:
        payload["black_duration"] = black_duration
    if cookies_content:
        payload["cookies_content"] = cookies_content
        
    print("\n正在向 http://localhost:8080/analyze 發送請求...")
    print("請確保您已先執行 start_backend_win.bat 啟動服務。")
    print("由於需要解析或下載影片，此步驟可能需要 1 到 3 分鐘，請稍候...")
    
    try:
        # 使用 5 分鐘 timeout
        with httpx.Client(timeout=300.0) as client:
            response = client.post("http://localhost:8080/analyze", json=payload)
            
        print(f"\n後端回傳狀態碼: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n分析成功！詳細回傳結果如下：")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"\n分析失敗！後端回傳錯誤：\n{response.text}")
            
    except httpx.ConnectError:
        print("\n錯誤: 連線失敗，請確認本地後端服務已成功啟動於連接埠 8080。")
    except Exception as e:
        print(f"\n執行測試時發生未預期錯誤: {e}")
        
if __name__ == "__main__":
    test_analyze()
    input("\n按任意鍵結束測試...")
