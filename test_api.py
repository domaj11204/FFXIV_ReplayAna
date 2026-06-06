import urllib.request
import json

def main():
    url = "http://127.0.0.1:8080/analyze"
    data = {
        "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rickroll link
        "template_name": "restart_template.png",
        "threshold": 0.65
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        print("正在發送測試請求至 API...")
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            print("API 回傳結果:")
            print(json.dumps(json.loads(res_body), indent=2, ensure_ascii=False))
    except urllib.error.HTTPError as e:
        print(f"HTTP 錯誤 ({e.code}): {e.reason}")
        print(e.read().decode("utf-8"))
    except Exception as e:
        print(f"發生錯誤: {e}")

if __name__ == "__main__":
    main()
