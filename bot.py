from keep_alive import keep_alive
keep_alive()
import discord
from discord import app_commands, Embed
from discord.ext import commands
import json, os, copy

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

data_file = "players.json"

DEFAULT_SHEET = {
    "license": [],
    "skills": [],
    "talents": [],
    "hase": {"HULL": 0, "AGL": 0, "SYS": 0, "ENG": 0},
    "core_bonus": "없음",
    "growth_cost": {
        "라이선스": 0,
        "재능": 0,
        "스킬": 0,
        "총합": 0
    }
}

def load_data():
    if os.path.exists(data_file):
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ 봇이 준비되었습니다: {bot.user}")

# 익조틱 강조 처리 함수
def format_exotic(entry: str) -> str:
    if entry.startswith("익조틱:"):
        content = entry.replace("익조틱:", "").strip()
        return f"🟦 **익조틱: {content}**"
    return entry

# /용병등록
@tree.command(name="용병등록", description="새로운 용병 콜사인을 등록합니다.")
@app_commands.describe(call_sign="등록할 용병의 콜사인")
async def 용병등록(interaction: discord.Interaction, call_sign: str):
    data = load_data()
    user_id = str(interaction.user.id)

    if call_sign in data:
        await interaction.response.send_message(f"❌ `{call_sign}` 은(는) 이미 존재하는 콜사인입니다.", ephemeral=True)
        return

    data[call_sign] = {
        "owner": user_id,
        "만나": 0,
        "막간티켓": 0,
        "items": [],
        "sheet": copy.deepcopy(DEFAULT_SHEET)
    }
    save_data(data)
    await interaction.response.send_message(f"✅ `{call_sign}` 용병이 성공적으로 등록되었습니다.")

# /개인정보
@tree.command(name="개인정보", description="자신의 용병 정보를 확인합니다.")
async def 개인정보(interaction: discord.Interaction):
    data = load_data()
    user_id = str(interaction.user.id)
    for call_sign, info in data.items():
        if info.get("owner") == user_id:
            embed = Embed(title=f"📘 용병 정보: {call_sign}", color=0x00ffcc)
            embed.add_field(name="💰 만나", value=f"{info.get('만나', 0)} 만나", inline=False)
            embed.add_field(name="🎟️ 막간 티켓", value=f"{info.get('막간티켓', 0)}장", inline=False)
            embed.add_field(name="📦 아이템", value=", ".join(info.get("items", [])) or "없음", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    await interaction.response.send_message("❌ 당신은 아직 용병을 등록하지 않았습니다.", ephemeral=True)

# /용병정보
@tree.command(name="용병정보", description="특정 용병의 정보를 확인합니다.")
@app_commands.describe(call_sign="확인할 용병의 콜사인")
async def 용병정보(interaction: discord.Interaction, call_sign: str):
    data = load_data()
    if call_sign not in data:
        await interaction.response.send_message(f"❌ `{call_sign}` 이라는 콜사인은 존재하지 않습니다.", ephemeral=True)
        return
    info = data[call_sign]
    embed = Embed(title=f"📘 용병 정보: {call_sign}", color=0x00ffcc)
    embed.add_field(name="💰 만나", value=f"{info.get('만나', 0)} 만나", inline=False)
    embed.add_field(name="🎟️ 막간 티켓", value=f"{info.get('막간티켓', 0)}장", inline=False)
    embed.add_field(name="📦 아이템", value=", ".join(info.get("items", [])) or "없음", inline=False)
    owner = await bot.fetch_user(int(info["owner"]))
    embed.set_footer(text=f"소유자: {owner.name}")
    await interaction.response.send_message(embed=embed)

# /삭제
@tree.command(name="용병삭제", description="콜사인에 해당하는 용병을 삭제합니다.")
@app_commands.describe(call_sign="삭제할 용병의 콜사인")
async def 용병삭제(interaction: discord.Interaction, call_sign: str):
    data = load_data()
    user_id = str(interaction.user.id)

    if call_sign not in data:
        await interaction.response.send_message(f"❌ `{call_sign}` 이라는 콜사인은 존재하지 않습니다.", ephemeral=True)
        return

    if data[call_sign].get("owner") != user_id and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🔒 당신은 이 용병을 삭제할 권한이 없습니다.", ephemeral=True)
        return

    del data[call_sign]
    save_data(data)
    await interaction.response.send_message(f"🗑️ `{call_sign}` 용병과 시트가 완전히 삭제되었습니다.")

# /용병시트
@tree.command(name="용병시트", description="해당 콜사인의 용병 시트를 조회합니다.")
@app_commands.describe(call_sign="조회할 콜사인 (생략 시 본인 용병 자동 조회)")
async def 용병시트(interaction: discord.Interaction, call_sign: str = None):
    data = load_data()
    user_id = str(interaction.user.id)

    if call_sign is None:
        for name, info in data.items():
            if str(info.get("owner")) == user_id:
                call_sign = name
                break
        else:
            await interaction.response.send_message("❌ 당신은 등록된 용병이 없습니다.", ephemeral=True)
            return

    if call_sign not in data or "sheet" not in data[call_sign]:
        await interaction.response.send_message(f"❌ `{call_sign}`의 시트 정보를 찾을 수 없습니다.", ephemeral=True)
        return

    sheet = data[call_sign]["sheet"]
    embed = Embed(title=f"💠 콜사인: {call_sign} - 용병 시트", color=0x3399ff)
    embed.add_field(name="🛡️ 메카 라이선스", value="\n".join(format_exotic(l) for l in sheet.get("license", [])) or "없음", inline=False)
    embed.add_field(name="🎯 스킬 트리거", value="\n".join(format_exotic(s) for s in sheet.get("skills", [])) or "없음", inline=False)
    embed.add_field(name="🧬 재능", value="\n".join(format_exotic(t) for t in sheet.get("talents", [])) or "없음", inline=False)
    hase = sheet.get("hase", {})
    hase_text = f"HULL: {hase.get('HULL', 0)} | AGL: {hase.get('AGL', 0)} | SYS: {hase.get('SYS', 0)} | ENG: {hase.get('ENG', 0)}"
    embed.add_field(name="🧠 HASE", value=hase_text, inline=False)
    embed.add_field(name="🔰 코어 보너스", value=sheet.get("core_bonus", "없음"), inline=False)
    growth = sheet.get("growth_cost", {})
    growth_text = f"라이선스: {growth.get('라이선스', 0)} 만나\n재능: {growth.get('재능', 0)} 만나\n스킬: {growth.get('스킬', 0)} 만나\n총합: {growth.get('총합', 0)} 만나"
    embed.add_field(name="💸 성장에 사용한 만나 총량", value=growth_text, inline=False)
    await interaction.response.send_message(embed=embed)

# /시트수정
@tree.command(name="시트수정", description="용병 시트의 항목을 수정합니다. 쉼표로 구분된 값을 입력하세요.")
@app_commands.describe(
    call_sign="수정할 용병의 콜사인",
    target="수정 대상 (license, skills, talents, hase, core_bonus, growth_cost 중 하나)",
    content="쉼표로 나눠진 수정 내용 (예: !HORUS 2랭크, MANTICORE 1랭크)"
)
async def 시트수정(interaction: discord.Interaction, call_sign: str, target: str, content: str):
    data = load_data()
    user_id = str(interaction.user.id)

    if call_sign not in data:
        await interaction.response.send_message(f"❌ `{call_sign}` 이라는 콜사인은 존재하지 않습니다.", ephemeral=True)
        return

    if data[call_sign].get("owner") != user_id and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🔒 당신은 이 용병의 시트를 수정할 권한이 없습니다.", ephemeral=True)
        return

    if "sheet" not in data[call_sign]:
        data[call_sign]["sheet"] = copy.deepcopy(DEFAULT_SHEET)

    sheet = data[call_sign]["sheet"]
    target = target.lower()
    parts = [p.strip() for p in content.split(",") if p.strip()]

    def process_entry(entry):
        return f"익조틱: {entry[1:].strip()}" if entry.startswith("!") else entry

    if target in ["license", "skills", "talents"]:
        sheet[target] = [process_entry(p) for p in parts]
    elif target == "hase":
        if len(parts) != 4:
            await interaction.response.send_message("❌ HASE는 4개의 숫자(HULL, AGL, SYS, ENG)가 필요합니다.", ephemeral=True)
            return
        try:
            sheet["hase"] = {"HULL": int(parts[0]), "AGL": int(parts[1]), "SYS": int(parts[2]), "ENG": int(parts[3])}
        except ValueError:
            await interaction.response.send_message("❌ HASE는 반드시 숫자로 입력해야 합니다.", ephemeral=True)
            return
    elif target == "core_bonus":
        sheet["core_bonus"] = content.strip()
    elif target == "growth_cost":
        if len(parts) != 4:
            await interaction.response.send_message("❌ growth_cost는 4개의 숫자(라이선스, 재능, 스킬, 총합)가 필요합니다.", ephemeral=True)
            return
        try:
            sheet["growth_cost"] = {
                "라이선스": int(parts[0]),
                "재능": int(parts[1]),
                "스킬": int(parts[2]),
                "총합": int(parts[3])
            }
        except ValueError:
            await interaction.response.send_message("❌ 성장 비용은 반드시 숫자로 입력해야 합니다.", ephemeral=True)
            return
    else:
        await interaction.response.send_message("❌ 수정 대상은 license, skills, talents, hase, core_bonus, growth_cost 중 하나여야 합니다.", ephemeral=True)
        return

    save_data(data)
    await interaction.response.send_message(f"✅ `{call_sign}`의 `{target}` 항목이 성공적으로 수정되었습니다.", ephemeral=False)

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