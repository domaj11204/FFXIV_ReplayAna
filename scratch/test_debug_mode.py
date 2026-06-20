import os
import json
import time
import urllib.request
import urllib.error

def main():
    print("開始測試 Debug Mode (使用 urllib)...")
    url = "http://localhost:8080/analyze"
    
    # 讀取本地的 Cookie 內容以防 Bot 檢測
    cookies_content = None
    cookie_paths = ["www.youtube.com_cookies.txt", "cookies.txt"]
    for path in cookie_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cookies_content = f.read()
                    print(f"已讀取本地 Cookie: {path}")
                    break
            except Exception as e:
                print(f"讀取 {path} 失敗: {e}")

    payload = {
        "youtube_url": "https://www.youtube.com/watch?v=zG68yxff90s",
        "template_name": "restart_template.png",
        "threshold": 0.65,
        "x_min": 0.30,
        "x_max": 0.70,
        "y_min": 0.25,
        "y_max": 0.50,
        "scan_duration_limit": 0.0,  # 掃描整部影片以捕捉所有 Wipe 點
        "debug": True
    }
    if cookies_content:
        payload["cookies_content"] = cookies_content

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')

    print(f"發送請求到 {url}...")
    try:
        start_time = time.time()
        # 設置 300 秒 timeout
        with urllib.request.urlopen(req, timeout=300) as response:
            res_body = response.read().decode('utf-8')
            status_code = response.status
        elapsed = time.time() - start_time
        print(f"請求完成，耗時 {elapsed:.2f} 秒，狀態碼: {status_code}")
        
        if status_code == 200:
            result = json.loads(res_body)
            print("分析結果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"請求失敗: {res_body}")
            
    except urllib.error.HTTPError as e:
        print(f"HTTP 錯誤: {e.code} {e.reason}")
        print(e.read().decode('utf-8'))
    except urllib.error.URLError as e:
        print(f"連線錯誤: {e.reason}")
    except Exception as e:
        print(f"發生異常: {e}")
        
    # 檢查 debug_wipes 目錄
    debug_dir = "debug_wipes"
    if os.path.exists(debug_dir):
        files = os.listdir(debug_dir)
        print(f"\n{debug_dir}/ 目錄下的檔案列表:")
        for f in sorted(files):
            fpath = os.path.join(debug_dir, f)
            print(f" - {f} ({os.path.getsize(fpath)} bytes)")
        if not files:
            print(" -> 警告: 目錄是空的，沒有產生 any 圖片。")
    else:
        print(f"\n -> 錯誤: {debug_dir} 目錄未被建立。")

if __name__ == "__main__":
    main()
