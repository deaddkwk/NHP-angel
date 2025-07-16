import discord
from discord import app_commands, Embed
from discord.ext import commands
import os, copy
from firebase_manager import save_player, get_player, delete_player, get_all_players, player_exists
from keep_alive import keep_alive

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

keep_alive()  # Render 절전 모드 방지용 웹서버 실행

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

@bot.event
async def on_ready():
    await tree.sync()
    print(f"✅ 봇이 준비되었습니다: {bot.user}")

def format_exotic(entry: str) -> str:
    if entry.startswith("익조틱:"):
        content = entry.replace("익조틱:", "").strip()
        return f"🟦 **익조틱: {content}**"
    return entry

@tree.command(name="용병삭제", description="콜사인에 해당하는 용병을 삭제합니다. (관리자 전용)")
@app_commands.describe(call_sign="삭제할 용병의 콜사인")
async def 용병삭제(interaction: discord.Interaction, call_sign: str):
    user_id = str(interaction.user.id)
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message(f"❌ `{call_sign}` 이라는 콜사인은 존재하지 않습니다.", ephemeral=True)
        return
    if data.get("owner") != user_id and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🔒 당신은 이 용병을 삭제할 권한이 없습니다.", ephemeral=True)
        return
    delete_player(call_sign)
    await interaction.response.send_message(f"🗑️ `{call_sign}` 용병과 시트가 완전히 삭제되었습니다.")

@tree.command(name="용병등록", description="새로운 용병 콜사인을 등록합니다.")
@app_commands.describe(call_sign="등록할 용병의 콜사인")
async def 용병등록(interaction: discord.Interaction, call_sign: str):
    user_id = str(interaction.user.id)
    if player_exists(call_sign):
        await interaction.response.send_message(f"❌ `{call_sign}` 은(는) 이미 존재하는 콜사인입니다.", ephemeral=True)
        return
    player_data = {
        "owner": user_id,
        "만나": 0,
        "막간티켓": 0,
        "items": [],
        "sheet": copy.deepcopy(DEFAULT_SHEET)
    }
    save_player(call_sign, player_data)
    await interaction.response.send_message(f"✅ `{call_sign}` 용병이 성공적으로 등록되었습니다.")

@tree.command(name="개인정보", description="자신의 용병 정보를 확인합니다.")
async def 개인정보(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    all_data = get_all_players()
    for call_sign, info in all_data.items():
        if info.get("owner") == user_id:
            embed = Embed(title=f"📘 용병 정보: {call_sign}", color=0x00ffcc)
            embed.add_field(name="💰 만나", value=f"{info.get('만나', 0)} 만나", inline=False)
            embed.add_field(name="🎟️ 막간 티켓", value=f"{info.get('막간티켓', 0)}장", inline=False)
            embed.add_field(name="📦 아이템", value=", ".join(info.get("items", [])) or "없음", inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
    await interaction.response.send_message("❌ 당신은 아직 용병을 등록하지 않았습니다.", ephemeral=True)

@tree.command(name="용병정보", description="특정 용병의 정보를 확인합니다.")
@app_commands.describe(call_sign="확인할 용병의 콜사인")
async def 용병정보(interaction: discord.Interaction, call_sign: str):
    info = get_player(call_sign)
    if not info:
        await interaction.response.send_message(f"❌ `{call_sign}` 이라는 콜사인은 존재하지 않습니다.", ephemeral=True)
        return
    embed = Embed(title=f"📘 용병 정보: {call_sign}", color=0x00ffcc)
    embed.add_field(name="💰 만나", value=f"{info.get('만나', 0)} 만나", inline=False)
    embed.add_field(name="🎟️ 막간 티켓", value=f"{info.get('막간티켓', 0)}장", inline=False)
    embed.add_field(name="📦 아이템", value=", ".join(info.get("items", [])) or "없음", inline=False)
    owner = await bot.fetch_user(int(info["owner"]))
    embed.set_footer(text=f"소유자: {owner.name}")
    await interaction.response.send_message(embed=embed)

@tree.command(name="용병시트", description="특정 용병의 시트를 확인합니다.")
@app_commands.describe(call_sign="조회할 용병의 콜사인")
async def 용병시트(interaction: discord.Interaction, call_sign: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return
    sheet = data.get("sheet", DEFAULT_SHEET)
    embed = Embed(title=f"📙 용병 시트: {call_sign}", color=0x3399ff)
    embed.add_field(name="🛡️ 메카 라이선스", value="\n".join(map(format_exotic, sheet.get("license", []))) or "없음", inline=False)
    embed.add_field(name="🎯 스킬 트리거", value="\n".join(map(format_exotic, sheet.get("skills", []))) or "없음", inline=False)
    embed.add_field(name="📚 재능", value="\n".join(map(format_exotic, sheet.get("talents", []))) or "없음", inline=False)
    hase = sheet.get("hase", {})
    embed.add_field(name="🔢 HASE", value=f"HULL: {hase.get('HULL', 0)}, AGL: {hase.get('AGL', 0)}, SYS: {hase.get('SYS', 0)}, ENG: {hase.get('ENG', 0)}", inline=False)
    embed.add_field(name="💠 코어 보너스", value=sheet.get("core_bonus", "없음"), inline=False)
    growth = sheet.get("growth_cost", {})
    embed.set_footer(text=f"성장에 소모한 만나 총합: {growth.get('총합', 0)} 만나")
    await interaction.response.send_message(embed=embed)

@tree.command(name="시트수정", description="시트 항목을 수정합니다. (쉼표로 구분)")
@app_commands.describe(call_sign="대상 콜사인", field="수정할 항목명", 내용="쉼표로 구분된 내용")
async def 시트수정(interaction: discord.Interaction, call_sign: str, field: str, 내용: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return
    sheet = data.get("sheet", DEFAULT_SHEET)
    entries = [e.strip() for e in 내용.split(",") if e.strip()]
    converted = [f"익조틱: {e[1:].strip()}" if e.startswith("!") else e for e in entries]
    if field in ["license", "skills", "talents"]:
        sheet[field] = converted
    elif field == "core_bonus":
        sheet[field] = 내용.strip()
    elif field == "hase":
        try:
            parts = list(map(int, entries))
            if len(parts) == 4:
                sheet["hase"] = {"HULL": parts[0], "AGL": parts[1], "SYS": parts[2], "ENG": parts[3]}
        except:
            await interaction.response.send_message("❌ HASE는 숫자 4개를 쉼표로 구분해 주세요.", ephemeral=True)
            return
    elif field == "growth":
        try:
            parts = list(map(int, entries))
            sheet["growth_cost"] = {"라이선스": parts[0], "재능": parts[1], "스킬": parts[2], "총합": sum(parts)}
        except:
            await interaction.response.send_message("❌ 성장 비용은 숫자 3개를 쉼표로 구분해 주세요.", ephemeral=True)
            return
    data["sheet"] = sheet
    save_player(call_sign, data)
    await interaction.response.send_message(f"✅ `{call_sign}` 시트의 `{field}` 항목이 수정되었습니다.")

bot.run(os.environ['DISCORD_TOKEN'])