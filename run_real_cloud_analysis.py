import urllib.request
import json
import time
import subprocess
import os
import sys

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
                cmd = runner + ["--cookies-from-browser", b, "--cookies", temp_txt.name, "--skip-download", "https://www.youtube.com"]
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

def format_time(seconds):
    seconds = max(0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"

def main():
    cloud_run_url = "https://ffxiv-replay-ana-471169883214.asia-east1.run.app/analyze"
    target_youtube_url = "https://www.youtube.com/watch?v=zG68yxff90s"
    
    # 不傳送 cookies_content，改由雲端 Cloud Run 自動從 GCS 下載已備份的 cookies.txt 進行直連解析
    cookies_content = None
    
    data = {
        "youtube_url": target_youtube_url,
        "template_name": "restart_template.png",
        "threshold": 0.65,
        "scan_duration_limit": 0.0  # 分析整部影片
    }
    
    headers = {"Content-Type": "application/json"}
    
    audience = cloud_run_url.split("/analyze")[0]
    print(f"嘗試獲取針對 {audience} 的 ID Token...")
    token = get_gcloud_token(audience)
    if token:
        headers["Authorization"] = f"Bearer {token}"
        print("成功獲取 ID Token。")
    
    req = urllib.request.Request(
        cloud_run_url,
        data=json.dumps(data).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        print(f"正在發送分析請求至雲端 Cloud Run ({cloud_run_url})，影片: {target_youtube_url}...")
        print("此為完整影片分析，可能需要幾分鐘的時間，請稍候...")
        start_time = time.time()
        
        with urllib.request.urlopen(req, timeout=180) as response:
            res_body = response.read().decode("utf-8")
            elapsed = time.time() - start_time
            print(f"\n分析完成！總共耗時: {elapsed:.2f} 秒")
            
            result_json = json.loads(res_body)
            # 寫入結果至 json 檔案
            output_file = "cloud_analysis_result.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result_json, f, indent=2, ensure_ascii=False)
            print(f"原始分析結果已儲存至 {output_file}")
            
            # 輸出 YouTube 影片簡介時間軸
            wipes = result_json.get("wipes", [])
            print("\n==================================================")
            print("📋 YouTube 影片簡介專用時間軸格式")
            print("==================================================")
            print("00:00 戰鬥開始 / 影片起點")
            for w in wipes:
                time_str = format_time(w["black_screen_start"])
                print(f"{time_str} 滅團 #{w['wipe_number']}")
            print("==================================================")
            
    except urllib.error.HTTPError as e:
        print(f"HTTP 錯誤 ({e.code}): {e.reason}")
        try:
            print(e.read().decode("utf-8"))
        except Exception:
            pass
    except Exception as e:
        print(f"發生錯誤: {e}")

if __name__ == "__main__":
    main()
