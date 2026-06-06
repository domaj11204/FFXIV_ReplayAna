import urllib.request
import json
import time

def main():
    url = "http://127.0.0.1:8080/analyze"
    data = {
        "youtube_url": "https://www.youtube.com/live/zG68yxff90s",
        "template_name": "restart_template.png",
        "threshold": 0.65,
        "scan_duration_limit": 660.0 # 限制掃描前 11 分鐘
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        print("正在發送測試請求至 API (限制分析前 11 分鐘)...")
        start_time = time.time()
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            elapsed = time.time() - start_time
            print(f"API 回傳結果 (耗時: {elapsed:.2f} 秒):")
            print(json.dumps(json.loads(res_body), indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(f"HTTP 錯誤 ({e.code}): {e.reason}")
        print(e.read().decode("utf-8"))
    except Exception as e:
        print(f"發生錯誤: {e}")

if __name__ == "__main__":
    main()
