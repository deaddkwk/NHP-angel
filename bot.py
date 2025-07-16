import discord
from discord.ext import commands
from dotenv import load_dotenv
load_dotenv()
import os

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'✅ 로그인 성공: {bot.user}')

@bot.command()
async def 안녕(ctx):
    await ctx.send("안녕하세요, 헤븐즈-링의 여러분?")

# 봇 토큰 직접 입력 or 환경 변수로 처리
bot.run(os.getenv("DISCORD_BOT_TOKEN"))