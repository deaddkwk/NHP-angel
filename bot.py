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
tree = bot.tree  # 슬래시 명령어 등록용

# 데이터 파일 경로
DATA_FILE = "data/players.json"

# 데이터 로딩 함수
def load_data():
    if not os.path.exists("data"):
        os.makedirs("data")
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump({}, f)
    with open(DATA_FILE, "r") as f:
        return json.load(f)

# 데이터 저장 함수
def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

# 봇이 온라인 될 때 실행
@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ 봇 로그인 완료: {bot.user}")

# !용병등록 - 플레이어 등록
@bot.command()
async def 용병등록(ctx):
    user_id = str(ctx.author.id)
    data = load_data()

    if user_id in data:
        await ctx.send("이미 용병으로 등록되어 있습니다!")
        return

    data[user_id] = {
        "name": ctx.author.name,
        "만나": 0,
        "막간티켓": 0,
        "items": []
    }
    save_data(data)
    await ctx.send(f"{ctx.author.name} 님이 용병으로 등록되었습니다!")

# /개인정보 - 슬래시 명령어
@tree.command(name="개인정보", description="자신의 만나 및 막간 티켓 정보를 확인합니다.")
async def 개인정보(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    data = load_data()

    if user_id not in data:
        await interaction.response.send_message("먼저 `!용병등록`을 사용해 등록해주세요.", ephemeral=True)
        return

    profile = data[user_id]
    await interaction.response.send_message(
        f"📄 **{profile['name']}님의 정보**\n"
        f"💰 만나: {profile['만나']}\n"
        f"🎟️ 막간 티켓: {profile['막간티켓']}\n"
        f"🎒 소지품: {', '.join(profile['items']) or '없음'}"
    )

# !만나지급 - 관리자 전용
@bot.command()
@commands.has_permissions(administrator=True)
async def 만나지급(ctx, member: discord.Member, amount: int):
    user_id = str(member.id)
    data = load_data()

    if user_id not in data:
        await ctx.send("해당 유저는 아직 용병으로 등록되지 않았습니다.")
        return

    data[user_id]["만나"] += amount
    save_data(data)
    await ctx.send(f"{member.name}님에게 만나 {amount} 지급 완료!")

# !막간지급 - 관리자 전용
@bot.command()
@commands.has_permissions(administrator=True)
async def 막간지급(ctx, member: discord.Member, amount: int):
    user_id = str(member.id)
    data = load_data()

    if user_id not in data:
        await ctx.send("해당 유저는 아직 용병으로 등록되지 않았습니다.")
        return

    data[user_id]["막간티켓"] += amount
    save_data(data)
    await ctx.send(f"{member.name}님에게 막간 티켓 {amount}장 지급 완료!")

# ──────────────────────────────
# RENDER 서버를 속이기 위한 포트 열기
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