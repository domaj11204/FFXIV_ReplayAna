import asyncio
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from main import analyze_video, AnalyzeRequest

async def main():
    print("=== 本地直接分析測試 (不透過 FastAPI) ===")
    
    # 讀取本地 Cookie
    cookies_content = None
    cookie_paths = ["cookies.txt", "www.youtube.com_cookies.txt"]
    for path in cookie_paths:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cookies_content = f.read()
                    print(f"已讀取本地 Cookie: {path}")
                    break
            except Exception as e:
                print(f"讀取 {path} 失敗: {e}")

    req = AnalyzeRequest(
        youtube_url="https://www.youtube.com/live/TDh49Hc47Ss",
        template_name="restart_template.png",
        threshold=0.65,
        x_min=0.30,
        x_max=0.70,
        y_min=0.25,
        y_max=0.50,
        scan_duration_limit=1560.0,  # 掃描前 26 分鐘 (包含 25:50 的 Wipe 點)
        debug=True,
        black_pix_th=0.15,
        black_duration=2.0
    )
    if cookies_content:
        req.cookies_content = cookies_content

    try:
        res = await analyze_video(req)
        print("\n分析成功回傳！結果:")
        print(res.model_dump_json(indent=2))
    except Exception as e:
        print(f"\n分析失敗並拋出異常: {e}")

if __name__ == "__main__":
    asyncio.run(main())
