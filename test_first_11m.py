import urllib.request
import json
import time
import sys
import subprocess
import os

def get_gcloud_token(audience):
    try:
        # 尋找本地 .gcloud_config 配置目錄
        env = os.environ.copy()
        local_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gcloud_config")
        if os.path.exists(local_config):
            env["CLOUDSDK_CONFIG"] = local_config
            
        cmd = ["gcloud.cmd", "auth", "print-identity-token", f"--audiences={audience}"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
            return result.stdout.strip()
        except FileNotFoundError:
            # 試試無副檔名的 gcloud
            cmd[0] = "gcloud"
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
            return result.stdout.strip()
    except Exception as e:
        print(f"無法透過 gcloud 獲取 Identity Token ({e})，將不帶身分驗證標頭發送請求。")
        return None

def extract_local_cookies():
    import tempfile
    
    # 建立一個臨時檔案
    temp_txt = tempfile.NamedTemporaryFile(delete=False, suffix=".txt")
    temp_txt.close()
    
    browsers = ['chrome', 'edge', 'firefox']
    for b in browsers:
        try:
            print(f"嘗試自本地 {b} 瀏覽器提取 YouTube 驗證 Cookie...")
            # 優先嘗試 uv run yt-dlp，若失敗再用 python -m yt_dlp
            for runner in [["uv", "run", "yt-dlp"], ["python", "-m", "yt_dlp"]]:
                cmd = runner + ["--cookies-from-browser", b, "--cookies", temp_txt.name, "--skip-download", "https://www.youtube.com/watch?v=zG68yxff90s"]
                res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if res.returncode == 0 and os.path.exists(temp_txt.name) and os.path.getsize(temp_txt.name) > 0:
                    with open(temp_txt.name, 'r', encoding='utf-8') as f:
                        content = f.read()
                    os.remove(temp_txt.name)
                    print(f"成功自 {b} 瀏覽器提取 Cookie！")
                    return content
        except Exception:
            continue
            
    if os.path.exists(temp_txt.name):
        os.remove(temp_txt.name)
    print("無法自本地瀏覽器提取 Cookie，將不帶 Cookie 進行分析。")
    return None

def main():
    # 預設的 Cloud Run 網址
    cloud_run_url = "https://ffxiv-replay-ana-471169883214.asia-east1.run.app/analyze"
    
    # 允許透過環境變數或命令行參數覆蓋
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        url = os.environ.get("API_URL", cloud_run_url)
        
    # 提取本地 Cookie
    cookies_content = None
    if url.startswith("https://") and "run.app" in url:
        cookies_content = extract_local_cookies()
        
    data = {
        "youtube_url": "https://www.youtube.com/live/zG68yxff90s",
        "template_name": "restart_template.png",
        "threshold": 0.65,
        "scan_duration_limit": 660.0 # 限制掃描前 11 分鐘
    }
    if cookies_content:
        data["cookies_content"] = cookies_content
    
    headers = {"Content-Type": "application/json"}
    
    # 如果是 https 且是 Cloud Run 網址，自動獲取 Token
    if url.startswith("https://") and "run.app" in url:
        # 解析出 audience 網址 (即去掉 /analyze)
        audience = url.split("/analyze")[0]
        print(f"偵測到 Cloud Run 網址，嘗試獲取針對 {audience} 的 ID Token...")
        token = get_gcloud_token(audience)
        if token:
            headers["Authorization"] = f"Bearer {token}"
            print("成功獲取 ID Token，已加入 Authorization 標頭。")
            
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        print(f"正在發送測試請求至 API ({url}) (限制分析前 11 分鐘)...")
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
