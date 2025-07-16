import discord
from discord.ext import commands
from discord import app_commands
import os
import json
from dotenv import load_dotenv

# 환경 변수 로딩
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# 인텐트 설정
intents = discord.Intents.default()
intents.message_content = True

# 봇 초기화
bot = commands.Bot(command_prefix='!', intents=intents)
tree = bot.tree

# 데이터 파일 경로
DATA_FILE = "data/players.json"

# 데이터 로딩 함수
def load_data():
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)
        return {}

# 데이터 저장 함수
def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# 봇이 온라인 될 때
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ 봇 로그인 완료: {bot.user}")

# !용병등록 콜사인
@bot.command()
async def 용병등록(ctx, call_sign: str):
    data = load_data()

    if call_sign in data:
        await ctx.send(f"콜사인 `{call_sign}` 은(는) 이미 등록되어 있습니다.")
        return

    # 등록
    data[call_sign] = {
        "owner": str(ctx.author.id),
        "만나": 0,
        "막간티켓": 0,
        "items": []
    }
    save_data(data)
    await ctx.send(f"{ctx.author.mention} 님의 콜사인 `{call_sign}` 이(가) 등록되었습니다!")

# /용병정보 [콜사인 (선택)]
@tree.command(name="용병정보", description="자신 또는 다른 용병의 정보를 확인합니다.")
@app_commands.describe(call_sign="확인할 용병의 콜사인 (생략 시 본인 소유 용병)")
async def 용병정보(interaction: discord.Interaction, call_sign: str = None):
    user_id = str(interaction.user.id)
    data = load_data()

    # 본인 소유 검색
    if call_sign is None:
        owned = [name for name, info in data.items() if info["owner"] == user_id]
        if not owned:
            await interaction.response.send_message("등록된 용병이 없습니다. 먼저 `!용병등록 콜사인` 으로 등록하세요.", ephemeral=True)
            return
        call_sign = owned[0]  # 첫 번째 콜사인 자동 선택

    # 콜사인 확인
    if call_sign not in data:
        await interaction.response.send_message(f"콜사인 `{call_sign}` 은(는) 등록되어 있지 않습니다.", ephemeral=True)
        return

    profile = data[call_sign]
    is_owner = profile["owner"] == user_id

    response = (
        f"📄 **용병 `{call_sign}` 정보**\n"
        f"💰 만나: {profile['만나']}\n"
        f"🎟️ 막간 티켓: {profile['막간티켓']}\n"
        f"🎒 소지품: {', '.join(profile['items']) or '없음'}\n"
    )

    if is_owner:
        response += f"🔒 (당신이 소유한 콜사인입니다)"

    await interaction.response.send_message(response)

# !만나지급 콜사인 금액
@bot.command()
@commands.has_permissions(administrator=True)
async def 만나지급(ctx, call_sign: str, amount: int):
    data = load_data()

    if call_sign not in data:
        await ctx.send(f"콜사인 `{call_sign}` 은(는) 등록되어 있지 않습니다.")
        return

    data[call_sign]["만나"] += amount
    save_data(data)
    await ctx.send(f"콜사인 `{call_sign}` 에게 만나 {amount} 지급 완료!")

# !막간지급 콜사인 수량
@bot.command()
@commands.has_permissions(administrator=True)
async def 막간지급(ctx, call_sign: str, amount: int):
    data = load_data()

    if call_sign not in data:
        await ctx.send(f"콜사인 `{call_sign}` 은(는) 등록되어 있지 않습니다.")
        return

    data[call_sign]["막간티켓"] += amount
    save_data(data)
    await ctx.send(f"콜사인 `{call_sign}` 에게 막간 티켓 {amount}장 지급 완료!")

# ──────────────────────────────
# Render 서버 포트 열기 (Render가 봇 종료하지 않게)
# ──────────────────────────────
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

class KeepAliveHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_server():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), KeepAliveHandler)
    server.serve_forever()

threading.Thread(target=run_server).start()

# 봇 토큰 직접 입력 or 환경 변수로 처리
bot.run(os.getenv("DISCORD_BOT_TOKEN"))