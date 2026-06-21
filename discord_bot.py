import os
import re
import json
import io
import time
import aiohttp
import discord
import subprocess
import asyncio
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import google.auth.transport.requests
from google.oauth2 import service_account
from google.cloud import storage
from yt_dlp import YoutubeDL

# 載入 .env 檔案
load_dotenv()

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
CLOUD_RUN_URL = os.environ.get("CLOUD_RUN_URL", "https://ffxiv-replay-ana-471169883214.asia-east1.run.app/analyze")
GOOGLE_APPLICATION_CREDENTIALS = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

# 確保必要的環境變數存在
if not DISCORD_BOT_TOKEN:
    print("警告：未設定 DISCORD_BOT_TOKEN 環境變數，機器人可能無法正常啟動。")

def get_oidc_token(audience: str) -> str:
    """
    獲取針對私有 Cloud Run 服務 (audience) 的 GCP OIDC ID Token。
    優先使用服務帳戶金鑰，Fallback 至本地 gcloud 命令行工具。
    """
    # 優先嘗試使用 Service Account 簽發 OIDC Token
    if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
        try:
            creds = service_account.IDTokenCredentials.from_service_account_file(
                GOOGLE_APPLICATION_CREDENTIALS, target_audience=audience
            )
            auth_req = google.auth.transport.requests.Request()
            creds.refresh(auth_req)
            return creds.token
        except Exception as e:
            print(f"使用服務帳戶金鑰獲取 Token 失敗：{e}。將嘗試使用本地 gcloud Fallback...")

    # Fallback：嘗試使用本地的 gcloud 命令行工具獲取
    try:
        env = os.environ.copy()
        # 若有本地 .gcloud_config 目錄則使用
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
        raise RuntimeError(
            f"無法獲取 GCP 身分驗證 Token。請確認已設定 GOOGLE_APPLICATION_CREDENTIALS "
            f"或已在本地透過 gcloud 完成登入。詳細錯誤：{e}"
        )

def format_time(seconds):
    seconds = max(0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    else:
        return f"{m:02d}:{s:02d}"

def build_progress_embed(
    title: str,
    description: str,
    youtube_url: str,
    video_title: str = None,
    est_time_str: str = None,
    game_language: str = "auto",
    threshold: float = 0.65,
    scan_start_offset: float = 0.0,
    scan_duration_limit: float = 0.0,
    x_min: float = 0.30,
    x_max: float = 0.70,
    y_min: float = 0.25,
    y_max: float = 0.50,
    current_status: str = None,
    color: discord.Color = discord.Color.blue()
) -> discord.Embed:
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    if video_title:
        embed.add_field(name="影片名稱", value=f"[{video_title}]({youtube_url})", inline=False)
    else:
        embed.add_field(name="影片網址", value=youtube_url, inline=False)
        
    lang_display = "自動判定" if game_language == "auto" else ("日文 (ja)" if game_language == "ja" else "英文 (en)")
    embed.add_field(name="遊戲語言", value=lang_display, inline=True)
    embed.add_field(name="相似度閾值", value=str(threshold), inline=True)
    
    offset_str = f"{format_time(scan_start_offset)}" if scan_start_offset > 0 else "無 (0s)"
    limit_str = f"{scan_duration_limit} 秒" if scan_duration_limit > 0 else "無限制"
    embed.add_field(name="掃描起始點 / 長度限制", value=f"{offset_str} / {limit_str}", inline=False)
    
    embed.add_field(name="裁切範圍 (X)", value=f"{x_min} ~ {x_max}", inline=True)
    embed.add_field(name="裁切範圍 (Y)", value=f"{y_min} ~ {y_max}", inline=True)
    embed.add_field(name="​", value="　　　　　　　　　　　　　　　*此設定僅影響準確度，不影響分析時長*", inline=False)
    
    if current_status:
        embed.add_field(name="目前狀態", value=current_status, inline=False)
        
    if est_time_str:
        embed.add_field(name="預估分析時間", value=est_time_str, inline=False)
        
    return embed

class TimelineView(discord.ui.View):
    """
    提供互動式按鈕的前端介面元件。
    """
    def __init__(self, wipes: list, video_title: str, video_duration: float):
        super().__init__(timeout=None)  # 按鈕永久有效，直到 bot 重啟
        self.wipes = wipes
        self.video_title = video_title
        self.video_duration = video_duration

    def generate_timeline(self, use_restart_time=False) -> str:
        lines = ["00:00 戰鬥開始 / 影片起點"]
        for w in self.wipes:
            seconds = w.get("restart_word_detected_at") if use_restart_time else w.get("black_screen_start")
            time_str = format_time(seconds)
            label = f"RESTART #{w.get('wipe_number')}" if use_restart_time else f"Wipe #{w.get('wipe_number')}"
            lines.append(f"{time_str} {label}")
        return "\n".join(lines)

    @discord.ui.button(label="複製時間軸 (黑屏點)", style=discord.ButtonStyle.primary)
    async def copy_black(self, interaction: discord.Interaction, button: discord.ui.Button):
        timeline = self.generate_timeline(use_restart_time=False)
        await interaction.response.send_message(
            content=f"**{self.video_title} - 時間軸 (以 Wipe 黑屏為基準)**\n```\n{timeline}\n```",
            ephemeral=True
        )

    @discord.ui.button(label="複製時間軸 (RESTART點)", style=discord.ButtonStyle.success)
    async def copy_restart(self, interaction: discord.Interaction, button: discord.ui.Button):
        timeline = self.generate_timeline(use_restart_time=True)
        await interaction.response.send_message(
            content=f"**{self.video_title} - 時間軸 (以 RESTART 字樣為基準)**\n```\n{timeline}\n```",
            ephemeral=True
        )

    @discord.ui.button(label="下載原始 JSON", style=discord.ButtonStyle.secondary)
    async def download_json(self, interaction: discord.Interaction, button: discord.ui.Button):
        data_str = json.dumps({"wipes": self.wipes, "video_title": self.video_title, "video_duration_seconds": self.video_duration}, indent=2, ensure_ascii=False)
        file = discord.File(fp=io.BytesIO(data_str.encode("utf-8")), filename="analysis_result.json")
        await interaction.response.send_message(
            content="這是原始 JSON 分析結果檔：",
            file=file,
            ephemeral=True
        )

class WipeBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        # 同步 Slash Commands
        await self.tree.sync()

bot = WipeBot()

@bot.event
async def on_ready():
    print(f"🤖 Discord Bot 已啟動並成功連線！")
    print(f"帳號名稱：{bot.user.name} (ID: {bot.user.id})")
    print(f"已註冊 Slash Commands，目前正監聽指令...")
    
    # 啟動時自動從 GCS 儲存桶同步最新的 cookie 到本地保存，以支援 GCS Bridge 本地解析
    try:
        bucket_name = "inspiring-bee-481116-m0-ffxiv-assets"
        def sync_cookie():
            if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
                client = storage.Client.from_service_account_json(GOOGLE_APPLICATION_CREDENTIALS)
            else:
                client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob("cookies.txt")
            if blob.exists():
                blob.download_to_filename("www.youtube.com_cookies.txt")
                print("成功自 GCS 儲存桶同步 cookies.txt 至本地檔案！")
            else:
                print("儲存桶上找不到 cookies.txt，跳過同步。")
        await asyncio.to_thread(sync_cookie)
    except Exception as e:
        print(f"⚠️ 啟動同步 GCS Cookie 失敗：{e}")

async def process_analysis_result(
    result: dict, 
    status_msg: discord.Message,
    game_language: str = "auto",
    threshold: float = 0.65,
    scan_start_offset: float = 0.0,
    scan_duration_limit: float = 0.0,
    x_min: float = 0.30,
    x_max: float = 0.70,
    y_min: float = 0.25,
    y_max: float = 0.50,
    youtube_url: str = ""
):
    video_title = result.get("video_title", "未知的影片")
    video_duration = result.get("video_duration_seconds", 0.0)
    wipes = result.get("wipes", [])
    
    is_warning = result.get("text_verification_failed", False)
    color = discord.Color.orange() if is_warning else discord.Color.green()
    title_str = "分析完成 (文字辨識異常)" if is_warning else "分析完成"
    
    if youtube_url:
        desc_str = f"影片 **[{video_title}]({youtube_url})** 分析完成，但文字辨識出現異常，已自動退回使用黑屏時間判定。" if is_warning else f"影片 **[{video_title}]({youtube_url})** 分析完成。"
    else:
        desc_str = f"影片 **{video_title}** 分析完成，但文字辨識出現異常，已自動退回使用黑屏時間判定。" if is_warning else f"影片 **{video_title}** 分析完成。"
    
    success_embed = discord.Embed(
        title=title_str,
        description=desc_str,
        color=color
    )
    
    if youtube_url:
        success_embed.add_field(name="影片名稱", value=f"[{video_title}]({youtube_url})", inline=False)
    else:
        success_embed.add_field(name="影片名稱", value=video_title, inline=False)
        
    success_embed.add_field(name="影片長度", value=format_time(video_duration), inline=True)
    success_embed.add_field(name="Wipe數", value=f"{len(wipes)} 次", inline=True)
    
    lang_display = "自動判定" if game_language == "auto" else ("日文 (ja)" if game_language == "ja" else "英文 (en)")
    success_embed.add_field(name="遊戲語言", value=lang_display, inline=True)
    success_embed.add_field(name="相似度閾值", value=str(threshold), inline=True)
    
    offset_str = f"{format_time(scan_start_offset)}" if scan_start_offset > 0 else "無 (0s)"
    limit_str = f"{scan_duration_limit} 秒" if scan_duration_limit > 0 else "無限制"
    success_embed.add_field(name="掃描起始點 / 長度限制", value=f"{offset_str} / {limit_str}", inline=False)
    
    # 保留分析設定與說明
    success_embed.add_field(name="裁切範圍 (X)", value=f"{x_min} ~ {x_max}", inline=True)
    success_embed.add_field(name="裁切範圍 (Y)", value=f"{y_min} ~ {y_max}", inline=True)
    success_embed.add_field(name="​", value="　　　　　　　　　　　　　　　*此設定僅影響準確度，不影響分析時長*", inline=False)
    
    if wipes:
        wipes_summary = []
        for w in wipes[:10]:
            time_str = format_time(w.get("black_screen_start"))
            score = w.get("similarity_score", 0.0)
            score_str = "僅黑屏偵測" if score == 0.0 else f"相似度: {score:.2f}"
            wipes_summary.append(f"• **Wipe #{w.get('wipe_number')}**: `{time_str}` ({score_str})")
            
        if len(wipes) > 10:
            wipes_summary.append(f"*...以及其餘 {len(wipes) - 10} 次Wipe*")
            
        success_embed.add_field(name="Wipe時間點摘要", value="\n".join(wipes_summary), inline=False)
    else:
        success_embed.add_field(name="偵測結果", value="未偵測到任何Wipe影格。", inline=False)
        
    view = TimelineView(wipes, video_title, video_duration)
    await status_msg.edit(embed=success_embed, view=view)

@bot.tree.command(name="analyze", description="分析 FFXIV 影片並辨識滅團 (Wipe) 時間點")
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
@app_commands.describe(
    youtube_url="YouTube 影片網址 (例如 https://youtube.com/live/...)",
    game_language="遊戲用戶端語言，預設為自動判定 (auto)",
    threshold="RESTART 模板比對相似度閾值 (預設 0.65)",
    x_min="偵測區域左邊界比例 (0.0 ~ 1.0, 預設 0.30)",
    x_max="偵測區域右邊界比例 (0.0 ~ 1.0, 預設 0.70)",
    y_min="偵測區域上邊界比例 (0.0 ~ 1.0, 預設 0.25)",
    y_max="偵測區域下邊界比例 (0.0 ~ 1.0, 預設 0.50)",
    scan_start_offset="限制掃描的起始時間 (秒，預設 0)",
    scan_duration_limit="限制只分析影片前 N 秒 (0 表示分析整部，預設 0)"
)
@app_commands.choices(game_language=[
    app_commands.Choice(name="自動判定 (auto)", value="auto"),
    app_commands.Choice(name="日文 (ja) - RESTART", value="ja"),
    app_commands.Choice(name="英文 (en) - FORWARD!", value="en")
])
async def analyze(
    interaction: discord.Interaction,
    youtube_url: str,
    game_language: str = "auto",
    threshold: float = 0.65,
    x_min: float = 0.30,
    x_max: float = 0.70,
    y_min: float = 0.25,
    y_max: float = 0.50,
    scan_start_offset: float = 0.0,
    scan_duration_limit: float = 0.0
):
    # 定義動態更新 Embed 欄位的輔助函式
    def update_embed_field(emb: discord.Embed, name: str, value: str, inline: bool = False):
        for idx, field in enumerate(emb.fields):
            if field.name == name:
                emb.set_field_at(idx, name=name, value=value, inline=inline)
                return
        emb.add_field(name=name, value=value, inline=inline)

    # Defer 回應：防超時，允許長達 15 分鐘的處理窗口
    await interaction.response.defer(ephemeral=False)
    
    # 建立初步處理狀態的 Embed (階段一：分析影片資訊中)
    embed = build_progress_embed(
        title="分析影片資訊中",
        description="正在讀取影片資訊與預估處理時間...",
        youtube_url=youtube_url,
        game_language=game_language,
        threshold=threshold,
        scan_start_offset=scan_start_offset,
        scan_duration_limit=scan_duration_limit,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max
    )
    status_msg = await interaction.followup.send(embed=embed)
    
    # 異步快速獲取影片資訊，算出預估下載與分析時間
    video_title = "YouTube 影片"
    video_duration = 0.0
    est_time_str = "無法預估（通常需要 1~3 分鐘）"
    try:
        def get_info():
            ydl_opts = {
                'quiet': True,
                'skip_download': True,
                'extract_flat': True,
                'noplaylist': True,
                'extractor_args': {
                    'youtube': {
                        'client': ['ios', 'android'],
                        'construct_dash': False
                    }
                }
            }
            if os.path.exists("www.youtube.com_cookies.txt"):
                ydl_opts["cookiefile"] = "www.youtube.com_cookies.txt"
            elif os.path.exists("cookies.txt"):
                ydl_opts["cookiefile"] = "cookies.txt"
            with YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(youtube_url, download=False)
        
        info = await asyncio.to_thread(get_info)
        video_title = info.get("title", video_title)
        video_duration = float(info.get("duration", 0.0))
        
        # 計算需要分析的實際長度
        scan_len = video_duration
        if scan_duration_limit > 0.0:
            scan_len = min(video_duration, scan_duration_limit)
            
        # 預估分析耗時公式 (4.5% 的影片時長 + 10 秒基礎耗時)
        est_seconds = int(scan_len * 0.045) + 10
        est_time_str = f"約 {format_time(est_seconds)} (依網路狀況可能有所變動)"
    except Exception as e:
        print(f"快速解析影片資訊失敗：{e}")
        
    # 更新 Embed 以顯示預估耗時與標題 (階段三：WIPE分析中)
    embed = build_progress_embed(
        title="WIPE分析中",
        description=f"正在分析影片：**{video_title}**\n正在分析Wipe時間點，這可能需要幾分鐘的時間，請稍候...",
        youtube_url=youtube_url,
        video_title=video_title,
        est_time_str=est_time_str,
        game_language=game_language,
        threshold=threshold,
        scan_start_offset=scan_start_offset,
        scan_duration_limit=scan_duration_limit,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max
    )
    await status_msg.edit(embed=embed)

    # 1. 取得 GCP ID Token (僅在指向 Cloud Run *.run.app 時需要)
    token = None
    if "run.app" in CLOUD_RUN_URL:
        try:
            audience = CLOUD_RUN_URL.split("/analyze")[0]
            token = get_oidc_token(audience)
        except Exception as e:
            error_embed = discord.Embed(
                title="❌ GCP 身分驗證錯誤",
                description=f"無法取得 GCP 認證 Token。\n請確認伺服器之認證環境或金鑰設定。\n\n**詳細原因：**\n`{str(e)}`",
                color=discord.Color.red()
            )
            await interaction.followup.send(embed=error_embed)
            return

    # 2. 準備 API 請求 (讀取本地最新 Cookie 並塞入 cookies_content 以防被 YouTube 判定為 Bot)
    cookies_content = None
    if os.path.exists("www.youtube.com_cookies.txt"):
        try:
            with open("www.youtube.com_cookies.txt", "r", encoding="utf-8") as f:
                cookies_content = f.read()
        except Exception as e:
            print(f"讀取 www.youtube.com_cookies.txt 失敗：{e}")
    elif os.path.exists("cookies.txt"):
        try:
            with open("cookies.txt", "r", encoding="utf-8") as f:
                cookies_content = f.read()
        except Exception as e:
            print(f"讀取 cookies.txt 失敗：{e}")

    payload = {
        "youtube_url": youtube_url,
        "template_name": "restart_template.png",
        "threshold": threshold,
        "x_min": x_min,
        "x_max": x_max,
        "y_min": y_min,
        "y_max": y_max,
        "scan_start_offset": scan_start_offset,
        "scan_duration_limit": scan_duration_limit,
        "game_language": game_language,
        "video_title": video_title,
        "video_duration": video_duration
    }
    if cookies_content:
        payload["cookies_content"] = cookies_content
    
    headers = {
        "Content-Type": "application/json"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # 2.5 判斷是否地端部署主動使用本地共享下載以顯示進度條
    use_local_shared_download = False
    if "run.app" not in CLOUD_RUN_URL and youtube_url.startswith("http") and os.path.exists("/app/shared_temp"):
        use_local_shared_download = True

    if use_local_shared_download:
        fallback_embed = build_progress_embed(
            title="下載影片中",
            description="正在本地安全下載影片以顯示進度條...",
            youtube_url=youtube_url,
            video_title=video_title,
            est_time_str=est_time_str,
            game_language=game_language,
            threshold=threshold,
            scan_start_offset=scan_start_offset,
            scan_duration_limit=scan_duration_limit,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            current_status="初始化中..."
        )
        await status_msg.edit(embed=fallback_embed)
        
        output_filename = None
        try:
            # 1. 決定臨時檔案路徑於共享目錄
            temp_filename = f"ffxiv_temp_{int(time.time())}.mp4"
            output_filename = os.path.join("/app/shared_temp", temp_filename)
            
            # 2. 本地使用最新 Cookie 下載影片 (最低解析度/體積最小)
            fallback_embed = build_progress_embed(
                title="下載影片中",
                description="正在本地安全下載影片以顯示進度條...",
                youtube_url=youtube_url,
                video_title=video_title,
                est_time_str=est_time_str,
                game_language=game_language,
                threshold=threshold,
                scan_start_offset=scan_start_offset,
                scan_duration_limit=scan_duration_limit,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
                current_status="正在本地提取影片串流中..."
            )
            await status_msg.edit(embed=fallback_embed)
            
            cmd = ["uv", "run", "yt-dlp"]
            if os.path.exists("www.youtube.com_cookies.txt"):
                cmd.extend(["--cookies", "www.youtube.com_cookies.txt"])
            elif os.path.exists("cookies.txt"):
                cmd.extend(["--cookies", "cookies.txt"])
            
            cmd.extend(["--newline", "--progress", "--no-colors", "--no-playlist"])
            cmd.extend(["--extractor-args", "youtube:client=ios,android;construct_dash=false"])
            cmd.extend(["-f", "bestvideo[height<=360]/best[height<=360]/worstvideo/worst", "-o", output_filename, youtube_url])
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL
            )
            
            # 解析 yt-dlp 輸出的進度條 regex
            progress_re = re.compile(
                r"\[download\]\s+([0-9.]+)%\s+of\s+([~0-9.a-zA-Z]+)(?:\s+at\s+([~0-9.a-zA-Z/s]+))?\s+ETA\s+([0-9:]+)"
            )
            finished_re = re.compile(
                r"\[download\]\s+100%\s+of\s+([~0-9.a-zA-Z]+)\s+in\s+([0-9:]+)"
            )

            def make_progress_bar(percent: float, width: int = 10) -> str:
                filled_len = int(round(width * percent / 100))
                bar = "■" * filled_len + "□" * (width - filled_len)
                return f"[{bar}] {percent:.1f}%"

            async def read_progress():
                last_update_time = 0.0
                last_text = ""
                while True:
                    line = await process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode('utf-8', errors='ignore').strip()
                    
                    match = progress_re.search(line_str)
                    if match:
                        percent_str, size_str, speed_str, eta_str = match.groups()
                        percent = float(percent_str)
                        bar_str = make_progress_bar(percent)
                        speed_info = f" | 速度: {speed_str}" if speed_str else ""
                        
                        text = f"正在本地提取影片串流中...\n{bar_str}\n大小: {size_str}{speed_info} | 剩餘時間: {eta_str}"
                        
                        now = time.time()
                        if text != last_text and (now - last_update_time >= 3.0 or percent >= 99.9):
                            try:
                                fallback_embed = build_progress_embed(
                                    title="下載影片中",
                                    description="正在本地安全下載影片以顯示進度條...",
                                    youtube_url=youtube_url,
                                    video_title=video_title,
                                    est_time_str=est_time_str,
                                    game_language=game_language,
                                    threshold=threshold,
                                    scan_start_offset=scan_start_offset,
                                    scan_duration_limit=scan_duration_limit,
                                    x_min=x_min,
                                    x_max=x_max,
                                    y_min=y_min,
                                    y_max=y_max,
                                    current_status=text
                                )
                                await status_msg.edit(embed=fallback_embed)
                                last_update_time = now
                                last_text = text
                            except Exception:
                                pass
                        continue

                    match_fin = finished_re.search(line_str)
                    if match_fin:
                        size_str, duration_str = match_fin.groups()
                        bar_str = make_progress_bar(100.0)
                        text = f"本地提取影片完成！\n{bar_str}\n大小: {size_str} | 總耗時: {duration_str}"
                        try:
                            fallback_embed = build_progress_embed(
                                title="下載影片中",
                                description="正在本地安全下載影片以顯示進度條...",
                                youtube_url=youtube_url,
                                video_title=video_title,
                                est_time_str=est_time_str,
                                game_language=game_language,
                                threshold=threshold,
                                scan_start_offset=scan_start_offset,
                                scan_duration_limit=scan_duration_limit,
                                x_min=x_min,
                                x_max=x_max,
                                y_min=y_min,
                                y_max=y_max,
                                current_status=text
                            )
                            await status_msg.edit(embed=fallback_embed)
                        except Exception:
                            pass
                        break

            progress_task = asyncio.create_task(read_progress())
            try:
                await process.wait()
                await asyncio.wait_for(progress_task, timeout=2.0)
            except Exception:
                pass
            finally:
                progress_task.cancel()
            
            if not os.path.exists(output_filename) or os.path.getsize(output_filename) == 0:
                raise RuntimeError("本地提取影片失敗，檔案未生成或大小為 0。")
                
            # 3. 以共享影片路徑向地端後端請求分析 (階段三：WIPE分析中)
            fallback_embed = build_progress_embed(
                title="WIPE分析中",
                description="影片已下載完成，地端分析引擎正在辨識滅團 (Wipe) 時間點，請稍候...",
                youtube_url=youtube_url,
                video_title=video_title,
                est_time_str=est_time_str,
                game_language=game_language,
                threshold=threshold,
                scan_start_offset=scan_start_offset,
                scan_duration_limit=scan_duration_limit,
                x_min=x_min,
                x_max=x_max,
                y_min=y_min,
                y_max=y_max,
                current_status="🎬 影片下載完成！正在啟動地端 FFXIV WIPE 影像分析引擎..."
            )
            await status_msg.edit(embed=fallback_embed)
            
            payload["youtube_url"] = f"/app/shared_temp/{temp_filename}"
            
            timeout = aiohttp.ClientTimeout(total=900)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(CLOUD_RUN_URL, json=payload, headers=headers) as response2:
                    if response2.status != 200:
                        err_body2 = await response2.text()
                        try:
                            err_json2 = json.loads(err_body2)
                            err_detail2 = err_json2.get("detail", err_body2)
                        except Exception:
                            err_detail2 = err_body2
                        raise RuntimeError(f"地端分析共享影片失敗，狀態碼: {response2.status}，原因: {err_detail2}")
                    result = await response2.json()
            
            # 清理本地影片
            def clean_up_shared():
                try:
                    if os.path.exists(output_filename):
                        os.remove(output_filename)
                except Exception:
                    pass
            asyncio.create_task(asyncio.to_thread(clean_up_shared))

        except Exception as e_shared:
            try:
                if output_filename and os.path.exists(output_filename):
                    os.remove(output_filename)
            except Exception:
                pass
            
            error_embed = discord.Embed(
                title="❌ 地端共享下載分析失敗",
                description=f"執行地端影片下載與分析時發生錯誤：\n`{str(e_shared)}`",
                color=discord.Color.red()
            )
            await status_msg.edit(embed=error_embed)
            return

        await process_analysis_result(
            result=result,
            status_msg=status_msg,
            game_language=game_language,
            threshold=threshold,
            scan_start_offset=scan_start_offset,
            scan_duration_limit=scan_duration_limit,
            x_min=x_min,
            x_max=x_max,
            y_min=y_min,
            y_max=y_max,
            youtube_url=youtube_url
        )
        return

    # 3. 發送 API 請求至 Cloud Run
    api_done = asyncio.Event()
    async def update_api_progress():
        nonlocal embed
        elapsed = 0
        while not api_done.is_set():
            await asyncio.sleep(10)
            elapsed += 10
            try:
                embed = build_progress_embed(
                    title="WIPE分析中",
                    description=f"正在分析影片：**{video_title}**\n正在分析Wipe時間點 (已分析 {elapsed} 秒)，請稍候...",
                    youtube_url=youtube_url,
                    video_title=video_title,
                    est_time_str=est_time_str,
                    game_language=game_language,
                    threshold=threshold,
                    scan_start_offset=scan_start_offset,
                    scan_duration_limit=scan_duration_limit,
                    x_min=x_min,
                    x_max=x_max,
                    y_min=y_min,
                    y_max=y_max
                )
                await status_msg.edit(embed=embed)
            except Exception:
                pass
                
    progress_task = asyncio.create_task(update_api_progress())
    try:
        # 使用 15 分鐘 (900 秒) 的 timeout，支援長影片分析
        timeout = aiohttp.ClientTimeout(total=900)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(CLOUD_RUN_URL, json=payload, headers=headers) as response:
                if response.status != 200:
                    # 立即停止進度計時更新，防範 Embed 被舊進度蓋掉
                    api_done.set()
                    progress_task.cancel()
                    
                    err_body = await response.text()
                    try:
                        err_json = json.loads(err_body)
                        err_detail = err_json.get("detail", err_body)
                    except Exception:
                        err_detail = err_body
                        
                    # 偵測是否被 YouTube Bot 檢測阻擋，且僅在指向雲端 Cloud Run 服務時才啟動 GCS Fallback 橋接（地端不需且無法使用此橋接）
                    # 排除影片本身正在轉檔的情況 (避免轉檔時本地也下載失敗且卡死)
                    if "run.app" in CLOUD_RUN_URL and "轉檔" not in err_detail and ("Sign in to confirm" in err_detail or "bot" in err_detail.lower() or "無法解析 YouTube 影片資訊" in err_detail or "黑屏偵測失敗" in err_detail or "Exit Code" in err_detail):
                        fallback_embed = build_progress_embed(
                            title="啟動GCS轉傳機制",
                            description="偵測到雲端 IP 遭 YouTube 阻擋分析。\n正在啟動 Fallback：在本地安全下載影片並上傳至雲端儲存桶以繞過限制...",
                            youtube_url=youtube_url,
                            video_title=video_title,
                            est_time_str=est_time_str,
                            game_language=game_language,
                            threshold=threshold,
                            scan_start_offset=scan_start_offset,
                            scan_duration_limit=scan_duration_limit,
                            x_min=x_min,
                            x_max=x_max,
                            y_min=y_min,
                            y_max=y_max,
                            current_status="初始化中...",
                            color=discord.Color.orange()
                        )
                        await status_msg.edit(embed=fallback_embed)
                        
                        output_filename = None
                        gcs_blob_name = None
                        try:
                            # 1. 決定臨時檔案路徑
                            import tempfile
                            temp_dir = tempfile.gettempdir()
                            temp_filename = f"ffxiv_temp_{int(time.time())}.mp4"
                            output_filename = os.path.join(temp_dir, temp_filename)
                            
                            # 2. 本地使用最新 Cookie 下載影片 (最低解析度/體積最小)
                            fallback_embed = build_progress_embed(
                                title="啟動GCS轉傳機制",
                                description="偵測到雲端 IP 遭 YouTube 阻擋分析。\n正在啟動 Fallback：在本地安全下載影片並上傳至雲端儲存桶以繞過限制...",
                                youtube_url=youtube_url,
                                video_title=video_title,
                                est_time_str=est_time_str,
                                game_language=game_language,
                                threshold=threshold,
                                scan_start_offset=scan_start_offset,
                                scan_duration_limit=scan_duration_limit,
                                x_min=x_min,
                                x_max=x_max,
                                y_min=y_min,
                                y_max=y_max,
                                current_status="正在本地提取影片串流中...",
                                color=discord.Color.orange()
                            )
                            await status_msg.edit(embed=fallback_embed)
                            
                            cmd = ["uv", "run", "yt-dlp"]
                            if os.path.exists("www.youtube.com_cookies.txt"):
                                cmd.extend(["--cookies", "www.youtube.com_cookies.txt"])
                            elif os.path.exists("cookies.txt"):
                                cmd.extend(["--cookies", "cookies.txt"])
                            
                            cmd.extend(["--newline", "--progress", "--no-colors", "--no-playlist"])
                            cmd.extend(["-f", "bestvideo[height<=360]/best[height<=360]/worstvideo/worst", "-o", output_filename, youtube_url])
                            
                            process = await asyncio.create_subprocess_exec(
                                *cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL
                            )
                            
                            # 解析 yt-dlp 輸出的進度條 regex
                            progress_re = re.compile(
                                r"\[download\]\s+([0-9.]+)%\s+of\s+([~0-9.a-zA-Z]+)(?:\s+at\s+([~0-9.a-zA-Z/s]+))?\s+ETA\s+([0-9:]+)"
                            )
                            finished_re = re.compile(
                                r"\[download\]\s+100%\s+of\s+([~0-9.a-zA-Z]+)\s+in\s+([0-9:]+)"
                            )

                            def make_progress_bar(percent: float, width: int = 10) -> str:
                                filled_len = int(round(width * percent / 100))
                                bar = "■" * filled_len + "□" * (width - filled_len)
                                return f"[{bar}] {percent:.1f}%"

                            async def read_progress():
                                last_update_time = 0.0
                                last_text = ""
                                while True:
                                    line = await process.stdout.readline()
                                    if not line:
                                        break
                                    line_str = line.decode('utf-8', errors='ignore').strip()
                                    
                                    match = progress_re.search(line_str)
                                    if match:
                                        percent_str, size_str, speed_str, eta_str = match.groups()
                                        percent = float(percent_str)
                                        bar_str = make_progress_bar(percent)
                                        speed_info = f" | 速度: {speed_str}" if speed_str else ""
                                        
                                        text = f"正在本地提取影片串流中...\n{bar_str}\n大小: {size_str}{speed_info} | 剩餘時間: {eta_str}"
                                        
                                        now = time.time()
                                        if text != last_text and (now - last_update_time >= 3.0 or percent >= 99.9):
                                            try:
                                                fallback_embed = build_progress_embed(
                                                    title="啟動GCS轉傳機制",
                                                    description="偵測到雲端 IP 遭 YouTube 阻擋分析。\n正在啟動 Fallback：在本地安全下載影片並上傳至雲端儲存桶以繞過限制...",
                                                    youtube_url=youtube_url,
                                                    video_title=video_title,
                                                    est_time_str=est_time_str,
                                                    game_language=game_language,
                                                    threshold=threshold,
                                                    scan_start_offset=scan_start_offset,
                                                    scan_duration_limit=scan_duration_limit,
                                                    x_min=x_min,
                                                    x_max=x_max,
                                                    y_min=y_min,
                                                    y_max=y_max,
                                                    current_status=text,
                                                    color=discord.Color.orange()
                                                )
                                                await status_msg.edit(embed=fallback_embed)
                                                last_update_time = now
                                                last_text = text
                                            except Exception:
                                                pass
                                        continue

                                    match_fin = finished_re.search(line_str)
                                    if match_fin:
                                        size_str, duration_str = match_fin.groups()
                                        bar_str = make_progress_bar(100.0)
                                        text = f"本地提取影片完成！\n{bar_str}\n大小: {size_str} | 總耗時: {duration_str}"
                                        try:
                                            fallback_embed = build_progress_embed(
                                                title="啟動GCS轉傳機制",
                                                description="偵測到雲端 IP 遭 YouTube 阻擋分析。\n正在啟動 Fallback：在本地安全下載影片並上傳至雲端儲存桶以繞過限制...",
                                                youtube_url=youtube_url,
                                                video_title=video_title,
                                                est_time_str=est_time_str,
                                                game_language=game_language,
                                                threshold=threshold,
                                                scan_start_offset=scan_start_offset,
                                                scan_duration_limit=scan_duration_limit,
                                                x_min=x_min,
                                                x_max=x_max,
                                                y_min=y_min,
                                                y_max=y_max,
                                                current_status=text,
                                                color=discord.Color.orange()
                                            )
                                            await status_msg.edit(embed=fallback_embed)
                                        except Exception:
                                            pass
                                        break

                            progress_task = asyncio.create_task(read_progress())
                            try:
                                await process.wait()
                                await asyncio.wait_for(progress_task, timeout=2.0)
                            except Exception:
                                pass
                            finally:
                                progress_task.cancel()
                            
                            if not os.path.exists(output_filename) or os.path.getsize(output_filename) == 0:
                                raise RuntimeError("本地提取影片失敗，檔案未生成或大小為 0。")
                                
                            # 3. 上傳影片至 GCS 儲存桶
                            fallback_embed = build_progress_embed(
                                title="啟動GCS轉傳機制",
                                description="偵測到雲端 IP 遭 YouTube 阻擋分析。\n正在啟動 Fallback：在本地安全下載影片並上傳至雲端儲存桶以繞過限制...",
                                youtube_url=youtube_url,
                                video_title=video_title,
                                est_time_str=est_time_str,
                                game_language=game_language,
                                threshold=threshold,
                                scan_start_offset=scan_start_offset,
                                scan_duration_limit=scan_duration_limit,
                                x_min=x_min,
                                x_max=x_max,
                                y_min=y_min,
                                y_max=y_max,
                                current_status="📤 影片提取成功！正在將影片同步上傳至雲端 GCS 儲存桶...",
                                color=discord.Color.orange()
                            )
                            await status_msg.edit(embed=fallback_embed)
                            
                            bucket_name = "inspiring-bee-481116-m0-ffxiv-assets"
                            gcs_blob_name = f"videos/{temp_filename}"
                            gcs_path = f"gs://{bucket_name}/{gcs_blob_name}"
                            
                            def upload_to_gcs():
                                if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
                                    client = storage.Client.from_service_account_json(GOOGLE_APPLICATION_CREDENTIALS)
                                else:
                                    client = storage.Client()
                                bucket = client.bucket(bucket_name)
                                blob = bucket.blob(gcs_blob_name)
                                blob.upload_from_filename(output_filename, content_type="video/mp4")
                                
                            await asyncio.to_thread(upload_to_gcs)
                            
                            # 4. 以 GCS 影片路徑再次請求 Cloud Run 分析 (階段三：WIPE分析中)
                            fallback_embed = build_progress_embed(
                                title="WIPE分析中",
                                description="影片已成功轉傳，雲端分析引擎正在辨識滅團 (Wipe) 時間點，請稍候...",
                                youtube_url=youtube_url,
                                video_title=video_title,
                                est_time_str=est_time_str,
                                game_language=game_language,
                                threshold=threshold,
                                scan_start_offset=scan_start_offset,
                                scan_duration_limit=scan_duration_limit,
                                x_min=x_min,
                                x_max=x_max,
                                y_min=y_min,
                                y_max=y_max,
                                current_status="🎬 影片同步完成！正在啟動雲端 FFXIV 滅團影像分析引擎..."
                            )
                            await status_msg.edit(embed=fallback_embed)
                            
                            fallback_payload = payload.copy()
                            fallback_payload["youtube_url"] = gcs_path
                            
                            async with session.post(CLOUD_RUN_URL, json=fallback_payload, headers=headers) as response2:
                                if response2.status != 200:
                                    err_body2 = await response2.text()
                                    raise RuntimeError(f"雲端分析 GCS 影片失敗，狀態碼: {response2.status}，原因: {err_body2}")
                                result = await response2.json()
                                
                            # 5. 分析成功後，背景非同步清理 GCS 臨時影片與本地檔案
                            def clean_up():
                                try:
                                    if os.path.exists(output_filename):
                                        os.remove(output_filename)
                                except Exception:
                                    pass
                                try:
                                    if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
                                        client = storage.Client.from_service_account_json(GOOGLE_APPLICATION_CREDENTIALS)
                                    else:
                                        return
                                    bucket = client.bucket(bucket_name)
                                    blob = bucket.blob(gcs_blob_name)
                                    if blob.exists():
                                        blob.delete()
                                        print(f"成功清理 GCS 臨時影片：{gcs_path}")
                                except Exception as e_clean:
                                    print(f"清理 GCS 臨時影片失敗：{e_clean}")
                                    
                            asyncio.create_task(asyncio.to_thread(clean_up))
                            
                        except Exception as e_fallback:
                            # 發生錯誤時清理本地與雲端檔案
                            try:
                                if output_filename and os.path.exists(output_filename):
                                    os.remove(output_filename)
                            except Exception:
                                pass
                            try:
                                if gcs_blob_name:
                                    def delete_gcs():
                                        try:
                                            if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
                                                client = storage.Client.from_service_account_json(GOOGLE_APPLICATION_CREDENTIALS)
                                            else:
                                                return
                                        except Exception:
                                            return
                                        bucket = client.bucket(bucket_name)
                                        blob = bucket.blob(gcs_blob_name)
                                        if blob.exists():
                                            blob.delete()
                                    asyncio.create_task(asyncio.to_thread(delete_gcs))
                            except Exception:
                                pass
                                
                            error_embed = discord.Embed(
                                title="❌ 儲存桶橋接 Fallback 失敗",
                                description=f"執行影片提取與儲存桶橋接時發生錯誤：\n`{str(e_fallback)}`",
                                color=discord.Color.red()
                            )
                            await status_msg.edit(embed=error_embed)
                            return
                            
                    else:
                        error_embed = discord.Embed(
                            title="❌ 分析服務異常",
                            description=f"後端分析伺服器回傳了錯誤代碼 `{response.status}`。",
                            color=discord.Color.red()
                        )
                        # 限制錯誤詳情在 900 個字元內，防止 Discord API 1024 長度報錯
                        truncated_detail = err_detail if len(err_detail) < 900 else err_detail[:900] + "\n...(其餘日誌內容已省略)..."
                        error_embed.add_field(name="錯誤詳情", value=f"```\n{truncated_detail}\n```", inline=False)
                        await status_msg.edit(embed=error_embed)
                        return
                else:
                    result = await response.json()
    except Exception as e:
        error_embed = discord.Embed(
            title="❌ 連線後端服務失敗",
            description=f"與後端分析伺服器連線時發生未預期錯誤：\n`{str(e)}`",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=error_embed)
        return
    finally:
        api_done.set()
        progress_task.cancel()

    # 4. 分析成功，處理結果
    await process_analysis_result(
        result=result,
        status_msg=status_msg,
        game_language=game_language,
        threshold=threshold,
        scan_start_offset=scan_start_offset,
        scan_duration_limit=scan_duration_limit,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        youtube_url=youtube_url
    )

@bot.tree.command(name="update_cookies", description="更新本地與雲端儲存桶中的 YouTube Cookies")
@app_commands.describe(cookie_file="從瀏覽器導出的 cookies.txt 檔案 (純文字 .txt 格式)")
@app_commands.checks.has_permissions(administrator=True)
async def update_cookies(interaction: discord.Interaction, cookie_file: discord.Attachment):
    # 檢查檔案名稱與副檔名
    if not cookie_file.filename.endswith(".txt"):
        await interaction.response.send_message("錯誤：請上傳一個純文字的 .txt 格式 Cookie 檔案。", ephemeral=True)
        return
        
    await interaction.response.defer(ephemeral=True)
    
    try:
        # 1. 讀取附件內容並進行健全解碼 (防範 UTF-8 BOM, UTF-16 等編碼問題)
        content_bytes = await cookie_file.read()
        content_str = None
        for enc in ["utf-8-sig", "utf-16", "big5", "utf-8"]:
            try:
                decoded = content_bytes.decode(enc)
                if "youtube.com" in decoded or "# Netscape" in decoded:
                    content_str = decoded
                    print(f"成功使用 {enc} 編碼解碼上傳的 Cookie 檔案。")
                    break
            except Exception:
                continue
                
        if not content_str:
            try:
                content_str = content_bytes.decode("utf-8", errors="ignore")
            except Exception:
                await interaction.followup.send("錯誤：無法成功解碼上傳的檔案，請確保其為純文字 .txt 格式。", ephemeral=True)
                return
        
        # 2. 檢查是否具有 YouTube Cookie 的基本特徵，確保沒上傳錯檔案
        if "youtube.com" not in content_str:
            await interaction.followup.send("警告：上傳的檔案內容看起來不包含 youtube.com 的 Cookie 資料，請確認您使用的是有效的 cookies.txt 檔案。", ephemeral=True)
            return
            
        # 3. 實時驗證 Cookie
        def verify_cookie():
            import tempfile
            with tempfile.NamedTemporaryFile(delete=False, mode="w", suffix=".txt", encoding="utf-8") as tf:
                tf.write(content_str)
                temp_path = tf.name
            
            ydl_opts = {
                "quiet": True,
                "skip_download": True,
                "cookiefile": temp_path,
            }
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info("https://www.youtube.com/watch?v=zG68yxff90s", download=False)
                return True, ""
            except Exception as e:
                err_msg = str(e)
                # 只有當錯誤中明確包含 Bot 或登入提示時，才判定驗證失敗
                is_bot_or_login = any(k in err_msg.lower() for k in ["confirm you", "bot", "captcha", "robot", "sign in", "login"])
                if is_bot_or_login:
                    return False, err_msg
                # 其他無關錯誤 (如格式解析失敗、網路瞬斷、JS 警告等) 均視為 Cookie 已通過認證
                return True, ""
            finally:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

        cookie_valid, cookie_err = await asyncio.to_thread(verify_cookie)
        if not cookie_valid:
            warn_msg = "上傳的 Cookie 檔案驗證失敗（可能已過期或被瀏覽器安全性輪替而失效）。請重新在瀏覽器中保持登入狀態並導出有效的 cookies.txt 後上傳。"
            if "confirm you" in cookie_err.lower() or "bot" in cookie_err.lower():
                warn_msg = "上傳的 Cookie 驗證失敗，YouTube 依然判定為 Bot（請重新導出有效的 Cookie 檔案上傳，並確認不要在導出後登出帳號或清除瀏覽器記錄）。"
            await interaction.followup.send(f"警告：{warn_msg}\n\n詳細錯誤原因：\n`{cookie_err}`", ephemeral=True)
            return

        # 4. 優先寫入本地 cookies 檔案
        def save_local_cookies():
            with open("cookies.txt", "w", encoding="utf-8") as f:
                f.write(content_str)
            with open("www.youtube.com_cookies.txt", "w", encoding="utf-8") as f:
                f.write(content_str)

        await asyncio.to_thread(save_local_cookies)
            
        # 4. 嘗試同步至雲端 GCS 儲存桶 (具備容錯，無憑證時不中斷)
        bucket_name = "inspiring-bee-481116-m0-ffxiv-assets"
        gcs_success = False
        gcs_error_msg = ""
        try:
            def do_upload():
                if GOOGLE_APPLICATION_CREDENTIALS and os.path.exists(GOOGLE_APPLICATION_CREDENTIALS):
                    client = storage.Client.from_service_account_json(GOOGLE_APPLICATION_CREDENTIALS)
                else:
                    client = storage.Client()
                bucket = client.bucket(bucket_name)
                blob = bucket.blob("cookies.txt")
                blob.upload_from_string(content_str, content_type="text/plain")
                
            await asyncio.to_thread(do_upload)
            gcs_success = True
        except Exception as ge:
            gcs_error_msg = str(ge)
            print(f"同步至 GCS 儲存桶失敗：{ge}")
            
        if gcs_success:
            await interaction.followup.send("YouTube Cookies 已成功更新並同步至雲端與本地儲存！現在您可以重新執行影像分析了。", ephemeral=True)
        else:
            await interaction.followup.send(f"YouTube Cookies 已成功更新至本地！但在同步至雲端時遇到錯誤（可能無 GCP 憑證），但不影響地端使用。雲端錯誤：{gcs_error_msg}", ephemeral=True)
        
    except Exception as e:
        await interaction.followup.send(f"更新 Cookie 失敗，詳細原因：{str(e)}", ephemeral=True)

@update_cookies.error
async def update_cookies_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "⚠️ 您無權限使用此指令。此指令僅限具有伺服器「**管理員 (Administrator)**」權限的人員使用。",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ 執行指令時發生錯誤：{str(error)}",
            ephemeral=True
        )

# 權限不足的錯誤處理
@analyze.error
async def analyze_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "⚠️ 您無權限使用此指令。此指令僅限具有伺服器「**管理員 (Administrator)**」權限的人員使用。",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ 執行指令時發生錯誤：{str(error)}",
            ephemeral=True
        )

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("錯誤：未設定 DISCORD_BOT_TOKEN。請在環境變數或 .env 檔案中填寫。")
    else:
        bot.run(DISCORD_BOT_TOKEN)
