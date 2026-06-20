import os
import httpx
import json
import time

def run_tests():
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(project_root)
    
    # 讀取本地 Cookie
    cookies_content = None
    for path in ["www.youtube.com_cookies.txt", "cookies.txt"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cookies_content = f.read()
                    print(f"已讀取 Cookie 檔案: {path}")
                    break
            except Exception as e:
                print(f"讀取 {path} 失敗: {e}")
                
    headers = {"Content-Type": "application/json"}
    
    # ------------------ 測試 1：英端 (FORWARD!) ------------------
    print("\n===================================================")
    print("  測試一：英端影片 (FORWARD!) - 應正確辨識 1:06:06 的 Wipe")
    print("===================================================")
    
    payload_en = {
        "youtube_url": "https://www.youtube.com/live/TDh49Hc47Ss",
        "template_name": "restart_template.png",
        "threshold": 0.45,  # 模板匹配閾值調整為 0.45，符合 FORWARD 的匹配表現
        "x_min": 0.30,
        "x_max": 0.70,
        "y_min": 0.25,
        "y_max": 0.50,
        "scan_start_offset": 3930.0,       # 從 1:05:30 開始
        "scan_duration_limit": 100.0,     # 掃描 100 秒 (包含 1:06:06)
        "game_language": "auto",          # 設定 auto 自動判定
        "black_duration": 2.0,
        "black_pix_th": 0.15,
        "debug": True
    }
    if cookies_content:
        payload_en["cookies_content"] = cookies_content
        
    try:
        with httpx.Client(timeout=300.0) as client:
            print("正在發送英端測試請求...")
            r = client.post("http://localhost:8080/analyze", json=payload_en)
            print(f"狀態碼: {r.status_code}")
            if r.status_code == 200:
                print("分析結果:")
                print(json.dumps(r.json(), indent=2, ensure_ascii=False))
            else:
                print(f"錯誤: {r.text}")
    except Exception as e:
        print(f"發送請求失敗: {e}")
        
    # ------------------ 測試 2：日端 (RESTART) ------------------
    print("\n===================================================")
    print("  測試二：日端影片 (RESTART) - 分析前 10 分鐘")
    print("===================================================")
    
    payload_ja = {
        "youtube_url": "https://youtube.com/live/y9tIAG4UIbo",
        "template_name": "restart_template.png",
        "threshold": 0.45,
        "x_min": 0.30,
        "x_max": 0.70,
        "y_min": 0.25,
        "y_max": 0.50,
        "scan_start_offset": 0.0,
        "scan_duration_limit": 600.0,     # 只掃描前 10 分鐘，加快測試速度
        "game_language": "auto",          # 設定 auto 自動判定
        "black_duration": 2.0,
        "black_pix_th": 0.15,
        "debug": True
    }
    if cookies_content:
        payload_ja["cookies_content"] = cookies_content
        
    try:
        with httpx.Client(timeout=300.0) as client:
            print("正在發送日端測試請求...")
            r = client.post("http://localhost:8080/analyze", json=payload_ja)
            print(f"狀態碼: {r.status_code}")
            if r.status_code == 200:
                print("分析結果:")
                print(json.dumps(r.json(), indent=2, ensure_ascii=False))
            else:
                print(f"錯誤: {r.text}")
    except Exception as e:
        print(f"發送請求失敗: {e}")

if __name__ == "__main__":
    run_tests()
