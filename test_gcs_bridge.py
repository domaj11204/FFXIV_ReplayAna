import urllib.request
import json
import time
import subprocess
import os
import sys
from google.cloud import storage

def get_gcloud_token(audience):
    try:
        env = os.environ.copy()
        local_config = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".gcloud_config")
        if os.path.exists(local_config):
            env["CLOUDSDK_CONFIG"] = local_config
            
        cmd = ["gcloud.cmd", "auth", "print-identity-token", f"--audiences={audience}"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
            return result.stdout.strip()
        except FileNotFoundError:
            cmd[0] = "gcloud"
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, env=env)
            return result.stdout.strip()
    except Exception as e:
        print(f"無法透過 gcloud 獲取 ID Token ({e})。")
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
    bucket_name = "inspiring-bee-481116-m0-ffxiv-assets"
    gcs_blob_name = "videos/test_bridge.mp4"
    gcs_path = f"gs://{bucket_name}/{gcs_blob_name}"
    local_temp_file = "test_bridge_temp.mp4"
    
    # 確保認證環境
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'inspiring-bee-481116-m0-1b2c8b808a2a.json'
    
    print("🚀 GCS 儲存桶橋接 (GCS Bridge) 測試開始...")
    
    # 1. 本地使用最新 Cookie 下載影片的最低畫質 ( worstvideo )
    try:
        print("\n1. 正在本地提取影片串流 (worstvideo)...")
        cookie_arg = []
        if os.path.exists("www.youtube.com_cookies.txt"):
            cookie_arg = ["--cookies", "www.youtube.com_cookies.txt"]
            
        cmd = ["uv", "run", "yt-dlp"] + cookie_arg + ["-f", "worstvideo/worst", "-o", local_temp_file, target_youtube_url]
        start_dl = time.time()
        # 執行下載
        subprocess.run(cmd, check=True)
        print(f"提取成功！耗時: {time.time() - start_dl:.2f} 秒。檔案大小: {os.path.getsize(local_temp_file) / 1024 / 1024:.2f} MB")
    except Exception as e:
        print(f"❌ 影片提取失敗: {e}")
        return
        
    # 2. 將影片上傳至 GCS Bucket
    try:
        print("\n2. 正在將影片同步上傳至 GCS 儲存桶...")
        start_up = time.time()
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_name)
        blob.upload_from_filename(local_temp_file, content_type="video/mp4")
        print(f"同步成功！耗時: {time.time() - start_up:.2f} 秒。")
    except Exception as e:
        print(f"❌ GCS 上傳失敗: {e}")
        # 清理本地臨時檔
        if os.path.exists(local_temp_file):
            os.remove(local_temp_file)
        return
        
    # 3. 呼叫 Cloud Run 進行分析
    result_json = None
    try:
        print("\n3. 正在發送分析請求至雲端 Cloud Run...")
        print("影像分析通常需要大約 30 到 50 秒，請稍候...")
        start_ana = time.time()
        
        audience = cloud_run_url.split("/analyze")[0]
        token = get_gcloud_token(audience)
        if not token:
            print("❌ 無法獲取 Identity Token。")
            return
            
        data = {
            "youtube_url": gcs_path,
            "template_name": "restart_template.png",
            "threshold": 0.65,
            "scan_duration_limit": 0.0
        }
        
        req = urllib.request.Request(
            cloud_run_url,
            data=json.dumps(data).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            },
            method="POST"
        )
        
        with urllib.request.urlopen(req) as response:
            res_body = response.read().decode("utf-8")
            elapsed = time.time() - start_ana
            print(f"分析完成！總分析耗時: {elapsed:.2f} 秒")
            result_json = json.loads(res_body)
            
            # 寫入分析結果至檔案
            output_file = "bridge_analysis_result.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(result_json, f, indent=2, ensure_ascii=False)
            print(f"原始分析結果已儲存至 {output_file}")
            
    except urllib.error.HTTPError as e:
        print(f"❌ HTTP 錯誤 ({e.code}): {e.reason}")
        try:
            print(e.read().decode("utf-8"))
        except Exception:
            pass
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        
    # 4. 清理臨時檔案 (GCS 與 本地)
    print("\n4. 正在執行臨時檔案清理...")
    try:
        if os.path.exists(local_temp_file):
            os.remove(local_temp_file)
            print("本地臨時檔案已清理。")
    except Exception as e:
        print(f"清理本地檔案失敗: {e}")
        
    try:
        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(gcs_blob_name)
        if blob.exists():
            blob.delete()
            print("GCS 雲端臨時檔案已清理。")
    except Exception as e:
        print(f"清理 GCS 臨時檔案失敗: {e}")
        
    # 5. 輸出時間軸結果
    if result_json:
        wipes = result_json.get("wipes", [])
        print("\n==================================================")
        print("📋 YouTube 影片簡介專用時間軸格式 (儲存桶橋接版)")
        print("==================================================")
        print("00:00 戰鬥開始 / 影片起點")
        for w in wipes:
            time_str = format_time(w["black_screen_start"])
            print(f"{time_str} 滅團 #{w['wipe_number']}")
        print("==================================================")

if __name__ == "__main__":
    main()
