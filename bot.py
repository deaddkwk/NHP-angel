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

EXOTIC_SHOP_PATH = './exotic_shop.txt'

FIELD_CHOICES = ["license", "skills", "talents", "core_bonus", "hase", "growth"]

async def field_autocomplete(interaction: discord.Interaction, current: str):
    return [
        app_commands.Choice(name=field, value=field)
        for field in FIELD_CHOICES
        if current.lower() in field.lower()
    ][:25]

SHOP_ITEMS = {
    "메크 라이선스": {"cost": 500, "growth_key": "라이선스"},
    "재능": {"cost": 300, "growth_key": "재능"},
    "교육": {"cost": 200, "growth_key": "스킬"},
    "메크 라이선스 1랭크 교체": {"cost": 200},
    "재능 전체 교체": {"cost": 300},
    "메크 스킬 전체 초기화": {"cost": 150},
    "코어 보너스 1개 교체": {"cost": 300},
    "1랭크 임대": {"cost": 100},
    "2랭크 임대": {"cost": 200},
    "3랭크 임대": {"cost": 300},
}

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

async def call_sign_autocomplete(interaction: discord.Interaction, current: str):
    all_players = get_all_players()
    if not all_players:
        return []
    return [
        app_commands.Choice(name=cs, value=cs)
        for cs in all_players.keys()
        if current.lower() in cs.lower()
    ][:25]

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
용병정보.autocomplete("call_sign")(call_sign_autocomplete)

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
용병시트.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="시트수정", description="시트 항목을 수정합니다. (쉼표로 구분)")
@app_commands.describe(call_sign="대상 콜사인", field="수정할 항목명입니다. license, skills, talents, core_bonus, hase, growth 등으로 수정하세요.", 내용="쉼표를 사용해서 구분해주세요.")
async def 시트수정(interaction: discord.Interaction, call_sign: str, field: str, 내용: str):
    user_id = str(interaction.user.id)
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return
    if not interaction.user.guild_permissions.administrator and data.get("owner") != user_id:
        await interaction.response.send_message("🚫 해당 시트를 수정할 권한이 없습니다.", ephemeral=True)
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
시트수정.autocomplete("call_sign")(call_sign_autocomplete)
시트수정.autocomplete("field")(field_autocomplete)

@tree.command(name="아이템지급", description="용병에게 아이템을 지급합니다. (관리자 전용)")
@app_commands.describe(call_sign="대상 용병 콜사인", items="쉼표로 구분된 아이템 목록")
async def 아이템지급(interaction: discord.Interaction, call_sign: str, items: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return
    item_list = [i.strip() for i in items.split(",") if i.strip()]
    inventory = data.get("items", {})
    if isinstance(inventory, list):  # 기존 리스트라면 딕셔너리로 변환
        inventory_dict = {}
        for i in inventory:
            inventory_dict[i] = inventory_dict.get(i, 0) + 1
        inventory = inventory_dict
    for item in item_list:
        inventory[item] = inventory.get(item, 0) + 1
    data["items"] = inventory
    save_player(call_sign, data)
    embed = Embed(title="📦 아이템 지급 완료!", description=f"{call_sign}에게 다음 아이템이 지급되었습니다:", color=0x99ccff)
    for item in item_list:
        embed.add_field(name=item, value=f"수량: {inventory[item]}", inline=False)
    await interaction.response.send_message(embed=embed)
아이템지급.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="아이템삭제", description="용병에게서 아이템을 하나 제거합니다. (관리자 전용)")
@app_commands.describe(call_sign="대상 용병 콜사인", item="삭제할 아이템 이름")
async def 아이템삭제(interaction: discord.Interaction, call_sign: str, item: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return
    inventory = data.get("items", {})
    if isinstance(inventory, list):
        inventory_dict = {}
        for i in inventory:
            inventory_dict[i] = inventory_dict.get(i, 0) + 1
        inventory = inventory_dict
    if item not in inventory:
        await interaction.response.send_message(f"❌ `{call_sign}`은(는) `{item}`을(를) 가지고 있지 않습니다.", ephemeral=True)
        return
    inventory[item] -= 1
    if inventory[item] <= 0:
        del inventory[item]
    data["items"] = inventory
    save_player(call_sign, data)
    await interaction.response.send_message(f"🗑️ `{call_sign}`에게서 `{item}` 1개를 제거했습니다.")
아이템삭제.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="임무보상지급", description="여러 용병에게 임무 보상을 지급합니다. (관리자 전용)")
@app_commands.describe(콜사인들="쉼표로 구분된 콜사인 목록", 만나="지급할 만나 수", 막간티켓="지급할 막간티켓 수")
async def 임무보상지급(interaction: discord.Interaction, 콜사인들: str, 만나: int = 0, 막간티켓: int = 0):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return
    call_signs = [c.strip() for c in 콜사인들.split(",") if c.strip()]
    results = []
    for call_sign in call_signs:
        data = get_player(call_sign)
        if not data:
            results.append(f"❌ `{call_sign}`: 존재하지 않음")
            continue
        data["만나"] = data.get("만나", 0) + 만나
        data["막간티켓"] = data.get("막간티켓", 0) + 막간티켓
        save_player(call_sign, data)
        results.append(f"✅ `{call_sign}`: {만나} 만나, {막간티켓} 티켓 지급")
    embed = Embed(title="🎁 임무 보상 지급 결과", description="\n".join(results), color=0x66cc99)
    await interaction.response.send_message(embed=embed)

# 상점리스트 명령어
@tree.command(name="상점리스트", description="일반 구매 가능한 항목과 가격을 확인합니다.")
async def 상점리스트(interaction):
    embed = Embed(title="📋 상점 리스트", description="구매 가능한 항목과 가격입니다.", color=0x99ccff)
    embed.add_field(name="📈 성장에 소모되는 항목", value="", inline=False)
    for name, data in SHOP_ITEMS.items():
        if "growth_key" in data:
            embed.add_field(name=f"{data['cost']} 만나", value=name, inline=True)
    embed.add_field(name="\u200b", value="\u200b", inline=False)
    embed.add_field(name="🔄 교체/임대 항목", value="", inline=False)
    for name, data in SHOP_ITEMS.items():
        if "growth_key" not in data:
            embed.add_field(name=f"{data['cost']} 만나", value=name, inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# 일반구매 명령어
@tree.command(name="일반구매", description="용병이 만나를 사용해 항목을 구매합니다.")
@app_commands.describe(call_sign="대상 용병의 콜사인", 항목="구매할 항목 이름")
async def 일반구매(interaction, call_sign: str, 항목: str):
    user_id = str(interaction.user.id)
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return
    if data.get("owner") != user_id and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 본인 소유의 용병만 구매할 수 있습니다.", ephemeral=True)
        return
    항목정보 = SHOP_ITEMS.get(항목)
    if not 항목정보:
        await interaction.response.send_message("❌ 존재하지 않는 항목입니다. `/상점리스트`로 확인해주세요.", ephemeral=True)
        return

    cost = 항목정보["cost"]
    만나 = data.get("만나", 0)
    if 만나 < cost:
        await interaction.response.send_message(f"❌ 만나가 부족합니다. (보유: {만나} / 필요: {cost})", ephemeral=True)
        return

    # 만나 차감
    data["만나"] -= cost

    # 성장 비용 반영
    if "growth_key" in 항목정보:
        sheet = data.get("sheet", {})
        growth = sheet.get("growth_cost", {})
        key = 항목정보["growth_key"]
        growth[key] = growth.get(key, 0) + cost
        growth["총합"] = growth.get("총합", 0) + cost
        sheet["growth_cost"] = growth
        data["sheet"] = sheet

    save_player(call_sign, data)

    embed = Embed(title="💸 일반 구매 완료", color=0x66cc66)
    embed.add_field(name="용병", value=call_sign, inline=True)
    embed.add_field(name="구매 항목", value=항목, inline=True)
    embed.add_field(name="소모한 만나", value=f"{cost} 만나", inline=True)
    await interaction.response.send_message(embed=embed)
일반구매.autocomplete("call_sign")(call_sign_autocomplete)

# 막간 행동 선언 명령어
@tree.command(name="막간", description="막간 티켓을 사용하여 어디서 무엇을 하는지 선언합니다.")
@app_commands.describe(call_sign="대상 용병 콜사인", 장소="어디서 행동하는지", 행동="무엇을 하는지")
async def 막간(interaction: discord.Interaction, call_sign: str, 장소: str, 행동: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return
    if data.get("owner") != str(interaction.user.id):
        await interaction.response.send_message("🚫 당신은 이 용병의 소유자가 아닙니다.", ephemeral=True)
        return
    if data.get("막간티켓", 0) <= 0:
        await interaction.response.send_message("❌ 막간 티켓이 부족합니다.", ephemeral=True)
        return

    data["막간티켓"] -= 1
    save_player(call_sign, data)

    embed = Embed(title=f"🎭 막간 행동 선언: {call_sign}", color=0x9999ff)
    embed.add_field(name="📍 장소", value=장소, inline=False)
    embed.add_field(name="📝 행동", value=행동, inline=False)
    embed.set_footer(text=f"소모된 막간 티켓: 1장")

    await interaction.response.send_message(embed=embed)
막간.autocomplete("call_sign")(call_sign_autocomplete)

# 막간 종료 및 보상 기록 명령어
@tree.command(name="막간종료", description="막간 행동에 대한 결과를 기록합니다.")
@app_commands.describe(
    call_sign="대상 용병 콜사인",
    rp="RP 막간 여부 (예/아니오)",
    stress="스트레스 소모량",
    reward_desc="보상 설명",
    item="지급할 아이템 (선택 사항)"
)
async def 막간종료(interaction: discord.Interaction, call_sign: str, rp: str, stress: int, reward_desc: str, item: str = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    # 아이템 지급
    if item:
        inventory = data.get("items", [])
        inventory.append(item)
        data["items"] = inventory
        save_player(call_sign, data)

    # 기록용 카드 생성
    embed = Embed(title=f"📘 막간 종료 보고서: {call_sign}", color=0x66ccff)
    embed.add_field(name="🎭 RP 막간 여부", value=rp, inline=False)
    embed.add_field(name="💢 스트레스 소모", value=str(stress), inline=False)
    embed.add_field(name="🎁 보상 요약", value=reward_desc, inline=False)

    await interaction.response.send_message(embed=embed)
막간종료.autocomplete("call_sign")(call_sign_autocomplete)
class ExoticShop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # /익조틱리스트 명령어
    @app_commands.command(name='익조틱리스트', description='익조틱 상점의 항목을 확인합니다.')
    @app_commands.describe(query='페이지 번호 또는 항목명')
    async def exotic_list(self, interaction: discord.Interaction, query: str = '1'):
        if not os.path.exists(EXOTIC_SHOP_PATH):
            await interaction.response.send_message('익조틱 상점 리스트 파일이 없습니다.', ephemeral=True)
            return

        with open(EXOTIC_SHOP_PATH, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip() and '|' in line]

        # 항목명 상세 조회
        if not query.isdigit():
            for line in lines:
                name, price, desc = [x.strip() for x in line.split('|', 2)]
                if query in name:
                    embed = discord.Embed(title=f"익조틱 항목: {name}", color=0x9966cc)
                    embed.add_field(name="가격", value=f"{price} 만나", inline=False)
                    embed.add_field(name="설명", value=desc, inline=False)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
            await interaction.response.send_message(f"'{query}'에 해당하는 항목을 찾을 수 없습니다.", ephemeral=True)
            return

        # 페이지 출력
        page = int(query)
        per_page = 10
        start = (page - 1) * per_page
        end = start + per_page

        shown = lines[start:end]
        if not shown:
            await interaction.response.send_message('해당 페이지에 항목이 없습니다.', ephemeral=True)
            return

        embed = discord.Embed(title=f"익조틱 상점 리스트 - 페이지 {page}", color=0x9966cc)
        for line in shown:
            name, price, _ = [x.strip() for x in line.split('|', 2)]
            embed.add_field(name=name, value=f"가격: {price} 만나", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    # /익조틱구매 명령어
    @app_commands.command(name='익조틱구매', description='익조틱 항목을 구매합니다.')
    @app_commands.describe(callsign='용병 콜사인', item_name='구매할 익조틱 항목명')
    async def exotic_buy(self, interaction: discord.Interaction, callsign: str, item_name: str):
        from firebase_admin import firestore
        db = firestore.client()
        doc_ref = db.collection('mercenaries').document(callsign)
        doc = doc_ref.get()

        if not doc.exists:
            await interaction.response.send_message(f"콜사인 '{callsign}' 을 찾을 수 없습니다.", ephemeral=True)
            return

        data = doc.to_dict()
        mana = data.get('만나', 0)

        if not os.path.exists(EXOTIC_SHOP_PATH):
            await interaction.response.send_message('익조틱 상점 리스트 파일이 없습니다.', ephemeral=True)
            return

        with open(EXOTIC_SHOP_PATH, 'r', encoding='utf-8') as f:
            found = False
            for line in f:
                if '|' not in line:
                    continue
                name, price, desc = [x.strip() for x in line.strip().split('|', 2)]
                if item_name in name:
                    found = True
                    price = int(price)
                    if mana < price:
                        await interaction.response.send_message(f"만나가 부족합니다. (보유: {mana}, 필요: {price})", ephemeral=True)
                        return
                    doc_ref.update({'만나': mana - price})
                    embed = discord.Embed(title=f"'{name}' 구매 완료", color=0x33cc99)
                    embed.add_field(name="설명", value=desc, inline=False)
                    embed.add_field(name="차감된 만나", value=f"{price} 만나", inline=True)
                    embed.add_field(name="잔여 만나", value=f"{mana - price} 만나", inline=True)
                    await interaction.response.send_message(embed=embed)
                    break

            if not found:
                await interaction.response.send_message(f"'{item_name}' 항목을 찾을 수 없습니다.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(ExoticShop(bot))

bot.run(os.environ['DISCORD_TOKEN'])