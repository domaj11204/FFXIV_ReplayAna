import urllib.request
import json
import time

def main():
    url = "http://100.103.205.10:8080/analyze"
    # 使用之前已知的測試影片
    youtube_url = "https://www.youtube.com/watch?v=zG68yxff90s"
    
    data = {
        "youtube_url": youtube_url,
        "template_name": "restart_template.png",
        "threshold": 0.65,
        "x_min": 0.30,
        "x_max": 0.70,
        "y_min": 0.25,
        "y_max": 0.50,
        "scan_duration_limit": 300  # 限制掃描前 300 秒加快速度
    }
    
    headers = {
        "Content-Type": "application/json"
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        print(f"正在向地端 API ({url}) 發送分析請求，影片: {youtube_url}...")
        start = time.time()
        with urllib.request.urlopen(req, timeout=120) as response:
            res_body = response.read().decode("utf-8")
            elapsed = time.time() - start
            print(f"請求成功，總耗時: {elapsed:.2f} 秒")
            result = json.loads(res_body)
            print("分析結果:")
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(f"HTTP 錯誤 ({e.code}): {e.reason}")
        try:
            print(e.read().decode("utf-8"))
        except Exception:
            pass
    except Exception as e:
        print(f"發生未預期錯誤: {e}")

if __name__ == "__main__":
    main()
