# -*- coding: utf-8 -*-
"""
Discord Bot (기준판)
- discord.py v2 슬래시 명령어 중심
- Render Web Service에서 keep-alive용 웹서버 $PORT 바인딩
- Firebase Realtime Database 래퍼(firebase_manager.py) 사용
- 통화 단위: 만나 (모든 구매/보상에서 사용)
- 막간 티켓: 전면 폐기됨
- 인벤토리: 전 명령어 딕셔너리 구조로 일원화
- 자동완성: 콜사인/필드/익조틱 항목/막간 장소
- 익조틱 상점: exotic_shop.txt 파일 기반 (이름|가격|설명)

필요 환경변수/시크릿 파일:
- DISCORD_TOKEN
- (firebase_manager.py 내부에서 사용) FIREBASE_CREDENTIALS_PATH, FIREBASE_DATABASE_URL 등

필요 파일(같은 폴더):
- exotic_shop.txt
- intermission_places.txt

주의: 본 파일은 Cog 미사용 단일 파일 구조입니다.
"""

from __future__ import annotations

import os
import re
import copy
import json
import time
import asyncio
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta

import discord
from discord import app_commands
from discord import Embed

# keep-alive용 aiohttp 서버
from aiohttp import web

# Firebase 래퍼(프로젝트에 포함되어 있어야 함)
# 예상 함수 시그니처:
#   get_player(call_sign: str) -> Optional[dict]
#   save_player(call_sign: str, data: dict) -> None
#   delete_player(call_sign: str) -> None
try:
    from firebase_manager import get_player, save_player, delete_player  # type: ignore
except Exception as e:  # 개발 환경에서 임시 대체(실서비스에서는 반드시 모듈 제공)
    print("[WARN] firebase_manager import 실패 — 임시 메모리 저장소 사용:", e)
    _MEM_DB: Dict[str, dict] = {}

    def get_player(call_sign: str) -> Optional[dict]:
        return copy.deepcopy(_MEM_DB.get(call_sign))

    def save_player(call_sign: str, data: dict) -> None:
        _MEM_DB[call_sign] = copy.deepcopy(data)

    def delete_player(call_sign: str) -> None:
        _MEM_DB.pop(call_sign, None)

# 선택적으로 전체 플레이어 리스트를 제공하는 함수가 있을 수 있음
try:
    from firebase_manager import list_players  # type: ignore
except Exception:
    list_players = None  # 없어도 동작하도록 처리

# ----------------------------------------------------------------------------
# 상수/유틸
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXOTIC_SHOP_PATH = os.path.join(BASE_DIR, 'exotic_shop.txt')
INTERMISSION_PLACES_PATH = os.path.join(BASE_DIR, 'intermission_places.txt')

KST = timezone(timedelta(hours=9))

FIELD_CHOICES = ["license", "skills", "talents", "core_bonus", "hase", "growth"]

SHOP_ITEMS = {
    # 성장 반영 그룹 (라이선스/재능/스킬)
    "메크 라이선스": {"cost": 500, "growth_key": "라이선스"},
    "재능": {"cost": 300, "growth_key": "재능"},
    "교육": {"cost": 200, "growth_key": "스킬"},  # 스킬 성장으로 집계
    # 성장 미반영 그룹
    "메크 라이선스 교체": {"cost": 200},
    "재능 교체": {"cost": 300},
    "메크 스킬 초기화": {"cost": 150},
    "코어 보너스 교체": {"cost": 300},
    "1랭크 라이선스 임무 해금": {"cost": 100},
    "2랭크 라이선스 임무 해금": {"cost": 200},
    "3랭크 라이선스 임무 해금": {"cost": 300},
}

DEFAULT_SHEET = {
    "license": [],
    "skills": [],
    "talents": [],
    "hase": {"HULL": 0, "AGL": 0, "SYS": 0, "ENG": 0},
    "core_bonus": "없음",
    "growth_cost": {"라이선스": 0, "재능": 0, "스킬": 0, "총합": 0}
}

CALLSIGN_CACHE: set[str] = set()  # 등록/삭제 시 보조 인덱스

# ----------------------------------------------------------------------------
# 도우미 함수
# ----------------------------------------------------------------------------

def _format_inventory_dict(inv: Dict[str, int]) -> str:
    if not inv:
        return "없음"
    return "\n".join(f"{k} ×{v}" for k, v in inv.items())

def _ensure_sheet_structure(data: dict) -> None:
    """sheet 구조가 없거나 부족하면 DEFAULT_SHEET 기준으로 보강"""
    if "sheet" not in data or not isinstance(data["sheet"], dict):
        data["sheet"] = copy.deepcopy(DEFAULT_SHEET)
        return
    sheet = data["sheet"]
    # 필드 보강
    if "license" not in sheet or not isinstance(sheet["license"], list):
        sheet["license"] = []
    if "skills" not in sheet or not isinstance(sheet["skills"], list):
        sheet["skills"] = []
    if "talents" not in sheet or not isinstance(sheet["talents"], list):
        sheet["talents"] = []
    if "hase" not in sheet or not isinstance(sheet["hase"], dict):
        sheet["hase"] = {"HULL": 0, "AGL": 0, "SYS": 0, "ENG": 0}
    else:
        for k in ("HULL", "AGL", "SYS", "ENG"):
            sheet["hase"].setdefault(k, 0)
    if "core_bonus" not in sheet:
        sheet["core_bonus"] = "없음"
    if "growth_cost" not in sheet or not isinstance(sheet["growth_cost"], dict):
        sheet["growth_cost"] = {"라이선스": 0, "재능": 0, "스킬": 0, "총합": 0}
    else:
        for k in ("라이선스", "재능", "스킬"):
            sheet["growth_cost"].setdefault(k, 0)
        sheet["growth_cost"]["총합"] = (
            sheet["growth_cost"].get("라이선스", 0)
            + sheet["growth_cost"].get("재능", 0)
            + sheet["growth_cost"].get("스킬", 0)
        )

def _apply_exotic_prefix(token: str) -> str:
    token = token.strip()
    if not token:
        return token
    if token.startswith("!"):
        return f"익조틱: {token[1:].strip()}"
    return token

def _parse_ints(payload: str) -> List[int]:
    # "1,2,3,4" 또는 "1 2 3 4" 모두 허용
    parts = re.split(r"[\s,]+", payload.strip()) if payload else []
    out: List[int] = []
    for p in parts:
        if p == "":
            continue
        try:
            out.append(int(p))
        except ValueError:
            pass
    return out

def _recompute_growth_total(sheet: dict) -> None:
    gc = sheet.get("growth_cost", {})
    total = gc.get("라이선스", 0) + gc.get("재능", 0) + gc.get("스킬", 0)
    gc["총합"] = total
    sheet["growth_cost"] = gc

def _load_intermission_places(prefix: str) -> List[str]:
    if not os.path.exists(INTERMISSION_PLACES_PATH):
        return []
    with open(INTERMISSION_PLACES_PATH, "r", encoding="utf-8") as f:
        places = [ln.strip() for ln in f if ln.strip()]
    if not prefix:
        return places[:25]
    pfx = prefix.lower()
    return [p for p in places if pfx in p.lower()][:25]

def _load_exotic_item_names(prefix: str) -> List[str]:
    if not os.path.exists(EXOTIC_SHOP_PATH):
        return []
    names: List[str] = []
    with open(EXOTIC_SHOP_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name = line.split("|")[0].strip()
            if name:
                names.append(name)
    if not prefix:
        return names[:25]
    pfx = prefix.lower()
    return [n for n in names if pfx in n.lower()][:25]

def _fetch_callsigns() -> List[str]:
    # 가능한 경우 래퍼의 list_players() 사용
    try:
        if callable(list_players):
            lst = list_players()  # type: ignore
            if isinstance(lst, list):
                return sorted([str(x) for x in lst])[:1000]
    except Exception:
        pass
    return sorted(CALLSIGN_CACHE)

# ----------------------------------------------------------------------------
# Discord 클라이언트/트리
# ----------------------------------------------------------------------------
intents = discord.Intents.default()
intents.message_content = False
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

SYNCED = False

# ----------------------------------------------------------------------------
# keep-alive 웹서버
# ----------------------------------------------------------------------------
async def start_keepalive() -> None:
    async def handle_root(request: web.Request) -> web.Response:
        return web.Response(text="ok")

    app = web.Application()
    app.router.add_get("/", handle_root)

    runner = web.AppRunner(app)
    await runner.setup()

    port = int(os.environ.get("PORT", os.environ.get("$PORT", 3000)))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"[keep-alive] running on :{port}")

# ----------------------------------------------------------------------------
# 이벤트
# ----------------------------------------------------------------------------
@bot.event
async def on_ready():
    global SYNCED
    if not SYNCED:
        try:
            await tree.sync()
            SYNCED = True
            print(f"[ready] Slash commands synced. Logged in as {bot.user}")
        except Exception as e:
            print("[ready] tree.sync() 실패:", e)
    else:
        print(f"[ready] Logged in as {bot.user}")

# ----------------------------------------------------------------------------
# 자동완성 핸들러
# ----------------------------------------------------------------------------
async def call_sign_autocomplete(interaction: discord.Interaction, current: str):
    names = _fetch_callsigns()
    cur = current.lower()
    out = [n for n in names if cur in n.lower()]
    return [app_commands.Choice(name=n, value=n) for n in out[:25]]

async def field_autocomplete(interaction: discord.Interaction, current: str):
    cur = current.lower()
    return [app_commands.Choice(name=f, value=f) for f in FIELD_CHOICES if cur in f.lower()][:25]

# ----------------------------------------------------------------------------
# 명령어: 용병/프로필
# ----------------------------------------------------------------------------
@tree.command(name="용병등록", description="새 용병 콜사인을 등록하고 기본 시트를 생성합니다.")
@app_commands.describe(call_sign="등록할 콜사인")
async def register(interaction: discord.Interaction, call_sign: str):
    exist = get_player(call_sign)
    if exist:
        await interaction.response.send_message("❌ 이미 존재하는 콜사인입니다.", ephemeral=True)
        return

    data = {
        "owner": str(interaction.user.id),
        "만나": 0,
        "items": {},            # 인벤토리: 딕셔너리 일원화
        "exotic_log": [],       # 익조틱 구매 로그
        "sheet": copy.deepcopy(DEFAULT_SHEET)
    }
    save_player(call_sign, data)
    CALLSIGN_CACHE.add(call_sign)

    embed = Embed(title="✅ 용병 등록 완료", color=0x33cc66)
    embed.add_field(name="콜사인", value=call_sign, inline=True)
    embed.add_field(name="소유자", value=f"<@{interaction.user.id}>", inline=True)
    await interaction.response.send_message(embed=embed)

register.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="용병정보", description="특정 콜사인의 기본 정보를 조회합니다.")
@app_commands.describe(call_sign="조회할 콜사인")
async def info(interaction: discord.Interaction, call_sign: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    _ensure_sheet_structure(data)

    embed = Embed(title=f"📘 용병 정보: {call_sign}", color=0x00ffcc)
    embed.add_field(name="💰 만나", value=f"{data.get('만나', 0)} 만나", inline=False)
    embed.add_field(name="📦 아이템", value=_format_inventory_dict(data.get("items", {})), inline=False)
    owner = data.get("owner")
    if owner:
        embed.set_footer(text=f"소유자: {owner}")
    await interaction.response.send_message(embed=embed)

info.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="개인정보", description="내 소유 용병의 정보를 조회합니다. (개인 응답)")
@app_commands.describe(call_sign="내가 소유한 콜사인")
async def myinfo(interaction: discord.Interaction, call_sign: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    if data.get("owner") != str(interaction.user.id):
        await interaction.response.send_message("🚫 당신은 이 용병의 소유자가 아닙니다.", ephemeral=True)
        return

    _ensure_sheet_structure(data)

    embed = Embed(title=f"📘 용병 정보: {call_sign}", color=0x00ffcc)
    embed.add_field(name="💰 만나", value=f"{data.get('만나', 0)} 만나", inline=False)
    embed.add_field(name="📦 아이템", value=_format_inventory_dict(data.get("items", {})), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

myinfo.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="용병삭제", description="용병과 시트를 삭제합니다. (소유자 또는 관리자)")
@app_commands.describe(call_sign="삭제할 콜사인")
async def delete_cmd(interaction: discord.Interaction, call_sign: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    if not (interaction.user.guild_permissions.administrator or data.get("owner") == str(interaction.user.id)):
        await interaction.response.send_message("🚫 소유자 또는 관리자만 삭제할 수 있습니다.", ephemeral=True)
        return

    delete_player(call_sign)
    CALLSIGN_CACHE.discard(call_sign)
    await interaction.response.send_message(f"🗑️ `{call_sign}` 삭제 완료")

delete_cmd.autocomplete("call_sign")(call_sign_autocomplete)

# ----------------------------------------------------------------------------
# 명령어: 용병 시트
# ----------------------------------------------------------------------------
@tree.command(name="용병시트", description="용병의 시트를 카드로 표시합니다.")
@app_commands.describe(call_sign="조회할 콜사인")
async def sheet_cmd(interaction: discord.Interaction, call_sign: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    _ensure_sheet_structure(data)
    s = data["sheet"]

    def _fmt_list(lst: List[str]) -> str:
        if not lst:
            return "없음"
        out = []
        for x in lst:
            if isinstance(x, str) and x.startswith("익조틱:"):
                out.append(f"💠 {x}")
            else:
                out.append(f"🔹 {x}")
        return "\n".join(out)

    embed = Embed(title=f"🧩 용병 시트: {call_sign}", color=0x7788ff)
    embed.add_field(name="📜 라이선스", value=_fmt_list(s.get("license", [])), inline=False)
    embed.add_field(name="🎯 스킬", value=_fmt_list(s.get("skills", [])), inline=False)
    embed.add_field(name="🌟 재능", value=_fmt_list(s.get("talents", [])), inline=False)

    h = s.get("hase", {})
    embed.add_field(name="🧬 HASE", value=f"HULL {h.get('HULL',0)} / AGL {h.get('AGL',0)} / SYS {h.get('SYS',0)} / ENG {h.get('ENG',0)}", inline=False)

    embed.add_field(name="🧩 코어 보너스", value=s.get("core_bonus", "없음"), inline=False)

    g = s.get("growth_cost", {})
    embed.add_field(
        name="📈 성장(누적 만나)",
        value=f"라이선스: {g.get('라이선스',0)} / 재능: {g.get('재능',0)} / 스킬: {g.get('스킬',0)}\n총합: {g.get('총합',0)}",
        inline=False
    )

    await interaction.response.send_message(embed=embed)

sheet_cmd.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="시트수정", description="용병 시트의 항목을 수정합니다. (소유자 또는 관리자)")
@app_commands.describe(
    call_sign="대상 콜사인",
    field="수정할 필드 (license/skills/talents/core_bonus/hase/growth)",
    value="입력 값 — 리스트는 쉼표 구분, hase는 4개 정수, growth는 3개 정수"
)
async def sheet_edit(interaction: discord.Interaction, call_sign: str, field: str, value: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    if not (interaction.user.guild_permissions.administrator or data.get("owner") == str(interaction.user.id)):
        await interaction.response.send_message("🚫 소유자 또는 관리자만 수정할 수 있습니다.", ephemeral=True)
        return

    _ensure_sheet_structure(data)
    sheet = data["sheet"]

    field = field.strip()
    if field not in FIELD_CHOICES:
        await interaction.response.send_message("❌ field 값이 올바르지 않습니다.", ephemeral=True)
        return

    if field in ("license", "skills", "talents"):
        tokens = [t.strip() for t in re.split(r",", value) if t.strip()]
        tokens = [_apply_exotic_prefix(t) for t in tokens]
        sheet[field] = tokens
    elif field == "core_bonus":
        sheet["core_bonus"] = value.strip() or "없음"
    elif field == "hase":
        nums = _parse_ints(value)
        if len(nums) != 4:
            await interaction.response.send_message("❌ hase 값은 정수 4개가 필요합니다. 예) 2,1,0,0", ephemeral=True)
            return
        sheet["hase"] = {"HULL": nums[0], "AGL": nums[1], "SYS": nums[2], "ENG": nums[3]}
    elif field == "growth":
        nums = _parse_ints(value)
        if len(nums) != 3:
            await interaction.response.send_message("❌ growth 값은 정수 3개(라이선스/재능/스킬)가 필요합니다. 예) 500,300,200", ephemeral=True)
            return
        sheet.setdefault("growth_cost", {"라이선스": 0, "재능": 0, "스킬": 0, "총합": 0})
        sheet["growth_cost"]["라이선스"] = nums[0]
        sheet["growth_cost"]["재능"] = nums[1]
        sheet["growth_cost"]["스킬"] = nums[2]
        _recompute_growth_total(sheet)

    data["sheet"] = sheet
    save_player(call_sign, data)

    await interaction.response.send_message(f"✅ `{call_sign}` 시트 `{field}` 수정 완료")

sheet_edit.autocomplete("call_sign")(call_sign_autocomplete)
sheet_edit.autocomplete("field")(field_autocomplete)

# ----------------------------------------------------------------------------
# 명령어: 상점/구매
# ----------------------------------------------------------------------------
@tree.command(name="상점리스트", description="일반 상점 가격표를 표시합니다. (개인 응답)")
async def shop_list(interaction: discord.Interaction):
    embed = Embed(title="🛒 일반 상점 리스트", color=0x55ccff)
    lines = []
    for name, meta in SHOP_ITEMS.items():
        lines.append(f"• {name} — {meta['cost']} 만나")
    embed.description = "\n".join(lines)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name="일반구매", description="일반 상점에서 항목을 구매합니다. 만나 차감 및 성장비용 반영(해당 항목만)")
@app_commands.describe(call_sign="대상 콜사인", 항목명="구매할 항목명(SHOP_ITEMS 키)")
async def shop_buy(interaction: discord.Interaction, call_sign: str, 항목명: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    meta = SHOP_ITEMS.get(항목명)
    if not meta:
        await interaction.response.send_message("❌ 존재하지 않는 항목명입니다.", ephemeral=True)
        return

    price = int(meta["cost"])  # 보장됨

    cur = int(data.get("만나", 0))
    if cur < price:
        await interaction.response.send_message(f"❌ 만나 부족 (보유 {cur} / 필요 {price})", ephemeral=True)
        return

    data["만나"] = cur - price

    # 성장비용 반영 (메크 라이선스/재능/교육(스킬))
    _ensure_sheet_structure(data)
    sheet = data["sheet"]
    growth_key = meta.get("growth_key")
    if growth_key:
        gc = sheet.get("growth_cost", {})
        gc[growth_key] = int(gc.get(growth_key, 0)) + price
        sheet["growth_cost"] = gc
        _recompute_growth_total(sheet)
        data["sheet"] = sheet

    save_player(call_sign, data)

    embed = Embed(title="✅ 구매 완료", color=0x66ff66)
    embed.add_field(name="용병", value=call_sign, inline=True)
    embed.add_field(name="항목", value=항목명, inline=True)
    embed.add_field(name="차감된 만나", value=str(price), inline=True)
    await interaction.response.send_message(embed=embed)

shop_buy.autocomplete("call_sign")(call_sign_autocomplete)

@shop_buy.autocomplete("항목명")
async def shop_item_ac(interaction: discord.Interaction, current: str):
    cur = current.lower()
    keys = [k for k in SHOP_ITEMS.keys() if cur in k.lower()]
    return [app_commands.Choice(name=k, value=k) for k in keys[:25]]

# ----------------------------------------------------------------------------
# 명령어: 아이템
# ----------------------------------------------------------------------------
@tree.command(name="아이템지급", description="아이템을 지급합니다. (관리자)")
@app_commands.describe(call_sign="대상 콜사인", item_name="아이템 이름", count="지급 수량(기본 1)")
async def give_item(interaction: discord.Interaction, call_sign: str, item_name: str, count: int = 1):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    inv = data.get("items", {})
    if not isinstance(inv, dict):
        inv = {}
    inv[item_name] = int(inv.get(item_name, 0)) + max(1, int(count))
    data["items"] = inv
    save_player(call_sign, data)

    await interaction.response.send_message(f"✅ `{call_sign}`에게 `{item_name}` ×{count} 지급 완료")

give_item.autocomplete("call_sign")(call_sign_autocomplete)

@tree.command(name="아이템삭제", description="아이템 수량을 1 감소(0이면 제거). (관리자)")
@app_commands.describe(call_sign="대상 콜사인", item_name="아이템 이름")
async def remove_item(interaction: discord.Interaction, call_sign: str, item_name: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    inv = data.get("items", {})
    if not isinstance(inv, dict):
        inv = {}

    if item_name not in inv:
        await interaction.response.send_message("❌ 해당 아이템이 없습니다.", ephemeral=True)
        return

    inv[item_name] = int(inv.get(item_name, 0)) - 1
    if inv[item_name] <= 0:
        inv.pop(item_name, None)

    data["items"] = inv
    save_player(call_sign, data)

    await interaction.response.send_message(f"🗑️ `{call_sign}`의 `{item_name}` 1개 제거 완료")

remove_item.autocomplete("call_sign")(call_sign_autocomplete)

# ----------------------------------------------------------------------------
# 명령어: 임무 보상
# ----------------------------------------------------------------------------
@tree.command(name="임무보상지급", description="여러 용병에게 임무 보상을 지급합니다. (관리자)")
@app_commands.describe(콜사인들="쉼표로 구분된 콜사인 목록", 만나="지급할 만나 수")
async def mission_reward(interaction: discord.Interaction, 콜사인들: str, 만나: int = 0):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    call_signs = [c.strip() for c in 콜사인들.split(",") if c.strip()]
    results = []
    for cs in call_signs:
        data = get_player(cs)
        if not data:
            results.append(f"❌ `{cs}`: 존재하지 않음")
            continue
        data["만나"] = int(data.get("만나", 0)) + int(만나)
        save_player(cs, data)
        results.append(f"✅ `{cs}`: {만나} 만나 지급")

    embed = Embed(title="🎁 임무 보상 지급 결과", description="\n".join(results), color=0x66cc99)
    await interaction.response.send_message(embed=embed)

# ----------------------------------------------------------------------------
# 명령어: 막간 (Intermission)
# ----------------------------------------------------------------------------
@tree.command(name="막간", description="어디서 무엇을 하는지 선언을 기록합니다. (티켓 소모 없음)")
@app_commands.describe(call_sign="대상 콜사인", 장소="어디서 행동하는지", 행동="무엇을 하는지")
async def intermission(interaction: discord.Interaction, call_sign: str, 장소: str, 행동: str):
    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    if data.get("owner") != str(interaction.user.id):
        await interaction.response.send_message("🚫 당신은 이 용병의 소유자가 아닙니다.", ephemeral=True)
        return

    embed = Embed(title=f"🎭 막간 행동 선언: {call_sign}", color=0x9999ff)
    embed.add_field(name="📍 장소", value=장소, inline=False)
    embed.add_field(name="📝 행동", value=행동, inline=False)
    await interaction.response.send_message(embed=embed)

intermission.autocomplete("call_sign")(call_sign_autocomplete)

@intermission.autocomplete("장소")
async def intermission_place_ac(interaction: discord.Interaction, current: str):
    places = _load_intermission_places(current)
    return [app_commands.Choice(name=p, value=p) for p in places]

@tree.command(name="막간종료", description="막간 결과를 기록하는 선언용 카드 생성(관리자). 선택적으로 아이템 1개 지급")
@app_commands.describe(call_sign="대상 콜사인", rp="RP 막간 여부", stress="스트레스 소모 값", reward="보상 내용(설명)", item="(선택) 보상 아이템")
async def intermission_end(interaction: discord.Interaction, call_sign: str, rp: bool, stress: int, reward: str, item: Optional[str] = None):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("🚫 관리자만 사용할 수 있습니다.", ephemeral=True)
        return

    data = get_player(call_sign)
    if not data:
        await interaction.response.send_message("❌ 존재하지 않는 콜사인입니다.", ephemeral=True)
        return

    embed = Embed(title=f"🏁 막간 종료: {call_sign}", color=0xffaa66)
    embed.add_field(name="RP 막간", value="예" if rp else "아니오", inline=True)
    embed.add_field(name="스트레스 소모", value=str(stress), inline=True)
    embed.add_field(name="보상", value=reward or "(설명 없음)", inline=False)

    # 선택적 아이템 지급
    if item:
        inv = data.get("items", {})
        if not isinstance(inv, dict):
            inv = {}
        inv[item] = int(inv.get(item, 0)) + 1
        data["items"] = inv
        save_player(call_sign, data)
        embed.add_field(name="지급 아이템", value=item, inline=False)

    await interaction.response.send_message(embed=embed)

intermission_end.autocomplete("call_sign")(call_sign_autocomplete)

# ----------------------------------------------------------------------------
# 명령어: 익조틱 상점 (파일 기반)
# ----------------------------------------------------------------------------
@tree.command(name='익조틱리스트', description='익조틱 상점 항목을 표시합니다. (개인 응답)')
@app_commands.describe(query='페이지 숫자 또는 항목명(부분 입력 가능). 비우면 1페이지')
async def exotic_list(interaction: discord.Interaction, query: Optional[str] = None):
    if not os.path.exists(EXOTIC_SHOP_PATH):
        await interaction.response.send_message('❌ exotic_shop.txt 파일이 없습니다.', ephemeral=True)
        return

    with open(EXOTIC_SHOP_PATH, 'r', encoding='utf-8') as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    # 페이지 모드
    if (not query) or query.isdigit():
        page = int(query) if (query and query.isdigit()) else 1
        page = max(1, page)
        per = 10
        start = (page - 1) * per
        chunk = lines[start:start + per]

        if not chunk:
            await interaction.response.send_message(f"❌ 해당 페이지가 비어 있습니다. (요청: {page})", ephemeral=True)
            return

        embed = Embed(title=f"💠 익조틱 상점 — 페이지 {page}", color=0xcc77ff)
        out = []
        for ln in chunk:
            name, price, *desc = [p.strip() for p in ln.split('|')]
            out.append(f"• **{name}** — {price} 만나")
        embed.description = "\n".join(out)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # 검색 모드 (부분일치 우선, 없으면 정확일치 재시도)
    q = query.strip().lower()
    found = None
    for ln in lines:
        name = ln.split('|')[0].strip()
        if name.lower().startswith(q) or q in name.lower():
            found = ln
            break
    if not found:
        for ln in lines:
            name = ln.split('|')[0].strip()
            if name.lower() == q:
                found = ln
                break

    if not found:
        await interaction.response.send_message("❌ 해당 항목을 찾을 수 없습니다.", ephemeral=True)
        return

    name, price, *desc = [p.strip() for p in found.split('|')]
    embed = Embed(title=f"💠 익조틱 상세 — {name}", color=0xcc77ff)
    embed.add_field(name="가격", value=f"{price} 만나", inline=True)
    if desc:
        embed.add_field(name="설명", value=" ".join(desc), inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@tree.command(name='익조틱구매', description='익조틱 항목을 구매합니다. (시트 미변경, 만나만 차감)')
@app_commands.describe(callsign='용병 콜사인', item='구매할 익조틱 항목 이름')
async def exotic_buy(interaction: discord.Interaction, callsign: str, item: str):
    if not os.path.exists(EXOTIC_SHOP_PATH):
        await interaction.response.send_message('❌ exotic_shop.txt 파일이 없습니다.', ephemeral=True)
        return

    with open(EXOTIC_SHOP_PATH, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]

    selected = None
    for line in lines:
        if line.split("|")[0].strip() == item:
            selected = line
            break

    if not selected:
        await interaction.response.send_message('❌ 해당 항목을 찾을 수 없습니다.', ephemeral=True)
        return

    name, price_str, *desc = [part.strip() for part in selected.split('|')]
    try:
        price = int(price_str)
    except ValueError:
        await interaction.response.send_message('❌ 가격 정보가 잘못되었습니다.', ephemeral=True)
        return

    data = get_player(callsign)
    if not data:
        await interaction.response.send_message(f'❌ `{callsign}` 용병 정보를 찾을 수 없습니다.', ephemeral=True)
        return

    current_manna = int(data.get('만나', 0))
    if current_manna < price:
        await interaction.response.send_message(f'❌ 만나가 부족합니다. (보유: {current_manna} / 필요: {price})', ephemeral=True)
        return

    # 만나 차감 (시트 변경 없음)
    data['만나'] = current_manna - price

    # 구매 로그 기록
    log_entry = {
        "time": datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "item": name,
        "price": price,
        "buyer": str(interaction.user.id)
    }
    logs = data.get("exotic_log", [])
    if not isinstance(logs, list):
        logs = []
    logs.append(log_entry)
    data["exotic_log"] = logs

    save_player(callsign, data)

    embed = discord.Embed(title='💠 익조틱 구매 완료', color=0x66ff66)
    embed.add_field(name='용병', value=callsign, inline=True)
    embed.add_field(name='구매 항목', value=name, inline=True)
    embed.add_field(name='차감된 만나', value=str(price), inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@exotic_buy.autocomplete("callsign")
async def exotic_buy_callsign_ac(interaction: discord.Interaction, current: str):
    return await call_sign_autocomplete(interaction, current)

@exotic_buy.autocomplete("item")
async def exotic_buy_item_ac(interaction: discord.Interaction, current: str):
    names = _load_exotic_item_names(current)
    return [app_commands.Choice(name=n, value=n) for n in names]

# ----------------------------------------------------------------------------
# 로깅/안정화: 로그인 429 백오프 재시도 루프
# ----------------------------------------------------------------------------
async def _start_bot():
    # keep-alive 웹서버 시작
    await start_keepalive()
    # 디스코드 봇 실행
    await bot.start(os.environ['DISCORD_TOKEN'])

if __name__ == "__main__":
    delay = 5
    while True:
        try:
            asyncio.run(_start_bot())
        except discord.HTTPException as e:
            if getattr(e, 'status', None) == 429:
                print(f"[WARN] 로그인 429: {delay}s 후 재시도")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            else:
                raise
        break
