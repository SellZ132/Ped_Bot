import discord
from discord import app_commands
from discord.ext import commands
from discord.ext import tasks
import asyncio
from flask import Flask
from threading import Thread
from typing import Union
from openai import AsyncOpenAI
import aiohttp
from bs4 import BeautifulSoup
import os
import json
from datetime import datetime

TOKEN = os.getenv("TOKEN_ID")
MY_GUILD_ID = int(os.getenv("MY_GUILD_ID"))

ALLOWED_USERS = [int(user_id) for user_id in os.getenv("ALLOWED_USERS").split(",")]

AI_CHANNEL_ID = int(os.getenv("AI_CHANNEL_ID"))
ASTD_CHANNEL_ID = int(os.getenv("ASTD_CHANNEL_ID")) if os.getenv("ASTD_CHANNEL_ID") else None
astd_message_id = int(os.getenv("ASTD_MESSAGE_ID")) if os.getenv("ASTD_MESSAGE_ID") else None

CONFIG_FILE = "config.json"

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}

def save_config(data: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f)

def get_config():
    c = load_config()
    return (
        c.get("dot_role_channel_id"),
        c.get("dot_role_id"),
        c.get("dot_log_channel_id"),
    )

_cfg = get_config()
DOT_ROLE_CHANNEL_ID = _cfg[0]
DOT_ROLE_ID = _cfg[1]
DOT_LOG_CHANNEL_ID = _cfg[2]

openai_client = AsyncOpenAI(
    api_key=os.environ.get('GROQ_API_KEY', ''),
    base_url="https://api.groq.com/openai/v1"
)

class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="/", intents=intents)

    async def setup_hook(self):
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)
        print("✅ Sync Commands Completed!")

bot = MyBot()

app = Flask('')
@app.route('/')
def home():
    return "I am alive!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if DOT_ROLE_CHANNEL_ID and message.channel.id == DOT_ROLE_CHANNEL_ID and message.content.strip() == ".":
        if DOT_ROLE_ID:
            role = message.guild.get_role(DOT_ROLE_ID)
            if role and role not in message.author.roles:
                try:
                    await message.author.add_roles(role, reason="พิมพ์ . ในห้องรับยศ")
                    if DOT_LOG_CHANNEL_ID:
                        log_channel = bot.get_channel(DOT_LOG_CHANNEL_ID)
                        if log_channel:
                            embed = discord.Embed(
                                title="✅ ให้ยศสำเร็จ",
                                color=discord.Color.green(),
                                timestamp=datetime.now()
                            )
                            embed.add_field(name="สมาชิก", value=f"{message.author.mention} (`{message.author}`)", inline=False)
                            embed.add_field(name="ยศที่ได้รับ", value=role.mention, inline=False)
                            embed.add_field(name="ห้องที่พิมพ์", value=message.channel.mention, inline=False)
                            embed.set_thumbnail(url=message.author.display_avatar.url)
                            await log_channel.send(embed=embed)
                except discord.Forbidden:
                    if DOT_LOG_CHANNEL_ID:
                        log_channel = bot.get_channel(DOT_LOG_CHANNEL_ID)
                        if log_channel:
                            await log_channel.send(f"❌ ไม่สามารถให้ยศ {role.mention} กับ {message.author.mention} ได้ (บอทไม่มีสิทธิ์)")
        return

    if AI_CHANNEL_ID is None or message.channel.id != AI_CHANNEL_ID:
        await bot.process_commands(message)
        return

    async with message.channel.typing():
        try:
            response = await openai_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": "คุณเป็น AI ผู้ช่วยที่ฉลาดและเป็นมิตร ตอบเป็นภาษาไทยเสมอ"},
                    {"role": "user", "content": message.content}
                ]
            )
            reply = response.choices[0].message.content
            await message.reply(reply)
        except Exception as e:
            await message.reply(f"❌ เกิดข้อผิดพลาด: {e}")

    await bot.process_commands(message)

@bot.tree.command(name="setup_ai", description="ตั้งค่าห้อง AI (แสดง ID ห้องปัจจุบัน)")
async def setup_ai(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    global AI_CHANNEL_ID
    AI_CHANNEL_ID = channel.id
    await interaction.response.send_message(f"✅ ตั้งค่าห้อง AI เป็น {channel.mention} แล้วครับ บอทจะตอบทุกข้อความในห้องนี้")

@bot.tree.command(name="remove_ai", description="ปิดระบบ AI ตอบอัตโนมัติ")
async def remove_ai(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    global AI_CHANNEL_ID
    AI_CHANNEL_ID = None
    await interaction.response.send_message("✅ ปิดระบบ AI ตอบอัตโนมัติแล้วครับ บอทจะไม่ตอบในห้องใดๆ จนกว่าจะ /setup_ai ใหม่")

@bot.tree.command(name="add_id", description="เพิ่มคนเข้า Whitelist (เฉพาะคนที่เป็น Admin)")
async def add_id(interaction: discord.Interaction, user_id: str):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    uid = int(user_id)
    if uid not in ALLOWED_USERS:
        ALLOWED_USERS.append(uid)
        await interaction.response.send_message(f"➕ เพิ่ม {user_id} เข้า Whitelist แล้ว")
    else:
        await interaction.response.send_message("มี ID นี้อยู่แล้วครับ")

@bot.tree.command(name="remove_whitelist", description="ลบคนออกจาก Whitelist (เฉพาะคนที่เป็น Admin)")
async def remove_whitelist(interaction: discord.Interaction, user_id: str):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    uid = int(user_id)
    if uid in ALLOWED_USERS:
        ALLOWED_USERS.remove(uid)
        await interaction.response.send_message(f"➖ ลบ {user_id} ออกจาก Whitelist แล้ว")
    else:
        await interaction.response.send_message("ไม่พบ ID นี้ใน Whitelist ครับ")

@bot.tree.command(name="join", description="ให้บอทเข้า Voice Channel ที่เลือก")
async def join(interaction: discord.Interaction, channel: discord.VoiceChannel = None):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    if channel is None:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ เลือกห้องหรือเข้าไปอยู่ใน Voice Channel ก่อนนะครับ", ephemeral=True)
            return
        channel = interaction.user.voice.channel

    if interaction.guild.voice_client:
        await interaction.guild.voice_client.move_to(channel)
    else:
        await channel.connect()

    await interaction.response.send_message(f"🔊 เข้า **{channel.name}** แล้วครับ")

@bot.tree.command(name="leave", description="ให้บอทออกจาก Voice Channel")
async def leave(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    if interaction.guild.voice_client:
        await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("👋 ออกจาก Voice Channel แล้วครับ")
    else:
        await interaction.response.send_message("❌ บอทไม่ได้อยู่ใน Voice Channel ครับ", ephemeral=True)

@bot.tree.command(name="disconnect_all", description="ตัดการเชื่อมต่อทุกคนในห้อง Voice ทันที")
async def disconnect_all(interaction: discord.Interaction, channel: discord.VoiceChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    members = channel.members
    if not members:
        await interaction.response.send_message("❌ ไม่มีคนอยู่ในห้องนี้ครับ", ephemeral=True)
        return

    await interaction.response.send_message(f"⚡ กำลังตัดการเชื่อมต่อทุกคนใน **{channel.name}**...")
    for member in members:
        try:
            await member.move_to(None)
        except:
            continue
    await interaction.followup.send(f"✅ ตัดการเชื่อมต่อ {len(members)} คน ออกจาก **{channel.name}** แล้วครับ")

@bot.tree.command(name="move_all", description="ย้ายทุกคนจากห้อง Voice นึงไปอีกห้อง")
async def move_all(interaction: discord.Interaction, from_channel: discord.VoiceChannel, to_channel: discord.VoiceChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    members = from_channel.members
    if not members:
        await interaction.response.send_message("❌ ไม่มีคนอยู่ในห้องต้นทางครับ", ephemeral=True)
        return

    await interaction.response.send_message(f"🔀 กำลังย้ายทุกคนจาก **{from_channel.name}** ไป **{to_channel.name}**...")
    count = 0
    for member in members:
        try:
            await member.move_to(to_channel)
            count += 1
        except:
            continue
    await interaction.followup.send(f"✅ ย้าย {count} คน ไปที่ **{to_channel.name}** แล้วครับ")

@bot.tree.command(name="mute_all", description="Mute ทุกคนในห้อง Voice ที่เลือก")
async def mute_all(interaction: discord.Interaction, channel: discord.VoiceChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    members = [m for m in channel.members if not m.bot]
    if not members:
        await interaction.response.send_message("❌ ไม่มีคนอยู่ในห้องนี้ครับ", ephemeral=True)
        return

    await interaction.response.send_message(f"🔇 กำลัง Mute ทุกคนใน **{channel.name}**...")
    count = 0
    for member in members:
        try:
            await member.edit(mute=True)
            count += 1
        except:
            continue
    await interaction.followup.send(f"✅ Mute {count} คน ใน **{channel.name}** แล้วครับ")

@bot.tree.command(name="unmute_all", description="Unmute ทุกคนในห้อง Voice ที่เลือก")
async def unmute_all(interaction: discord.Interaction, channel: discord.VoiceChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    members = [m for m in channel.members if not m.bot]
    if not members:
        await interaction.response.send_message("❌ ไม่มีคนอยู่ในห้องนี้ครับ", ephemeral=True)
        return

    await interaction.response.send_message(f"🔊 กำลัง Unmute ทุกคนใน **{channel.name}**...")
    count = 0
    for member in members:
        try:
            await member.edit(mute=False)
            count += 1
        except:
            continue
    await interaction.followup.send(f"✅ Unmute {count} คน ใน **{channel.name}** แล้วครับ")

@bot.tree.command(name="say", description="ให้บอทส่งข้อความในห้องแชทหรือ Voice Chat ที่เลือก")
async def say(interaction: discord.Interaction, channel: Union[discord.TextChannel, discord.VoiceChannel], message: str):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    await channel.send(message)
    await interaction.response.send_message(f"✅ ส่งข้อความไปที่ {channel.mention} แล้วครับ", ephemeral=True)

@bot.tree.command(name="rename", description="เปลี่ยนชื่อ (Nickname) ของสมาชิกในเซิร์ฟเวอร์")
async def rename(interaction: discord.Interaction, member: discord.Member, new_name: str):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    try:
        old_name = member.display_name
        await member.edit(nick=new_name)
        await interaction.response.send_message(f"✅ เปลี่ยนชื่อ **{old_name}** เป็น **{new_name}** แล้วครับ")
    except discord.Forbidden:
        await interaction.response.send_message("❌ บอทไม่มีสิทธิ์เปลี่ยนชื่อคนนี้ครับ", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

@bot.tree.command(name="reset_name", description="รีเซ็ตชื่อของสมาชิกกลับเป็นชื่อเดิม")
async def reset_name(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    try:
        await member.edit(nick=None)
        await interaction.response.send_message(f"✅ รีเซ็ตชื่อของ **{member.name}** แล้วครับ")
    except discord.Forbidden:
        await interaction.response.send_message("❌ บอทไม่มีสิทธิ์เปลี่ยนชื่อคนนี้ครับ", ephemeral=True)

@bot.tree.command(name="avatar", description="ดูรูปโปรไฟล์ของสมาชิก")
async def avatar(interaction: discord.Interaction, member: discord.Member):
    embed = discord.Embed(title=f"รูปโปรไฟล์ของ {member.display_name}", color=discord.Color.blue())
    embed.set_image(url=member.display_avatar.url)
    embed.set_footer(text=f"ID: {member.id}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="callall", description="ส่ง @everyone เรียกทุกคนมา Discord ทันที")
async def callall(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    await interaction.response.send_message("@everyone มาดิสเดี๋ยวนี้ไม่มาดิสโลกจะแตก")

@bot.tree.command(name="dmall", description="ส่งข้อความหาทุกคน")
async def dmall(interaction: discord.Interaction, message: str):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ ไม่มีสิทธิ์!", ephemeral=True)
        return

    await interaction.response.send_message("🚀 กำลังเริ่มส่ง DM...")
    guild = interaction.guild
    for member in guild.members:
        if member.bot: continue
        try:
            await member.send(f"**ประกาศจาก {guild.name}:**\n{message}")
            await asyncio.sleep(0.6)
        except:
            continue
    await interaction.followup.send("🏁 ส่งเสร็จแล้ว!")

@bot.tree.command(name="setup_dot_role", description="ตั้งค่าระบบรับยศอัตโนมัติเมื่อพิมพ์ .")
async def setup_dot_role(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role, log_channel: discord.TextChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    global DOT_ROLE_CHANNEL_ID, DOT_ROLE_ID, DOT_LOG_CHANNEL_ID
    DOT_ROLE_CHANNEL_ID = channel.id
    DOT_ROLE_ID = role.id
    DOT_LOG_CHANNEL_ID = log_channel.id
    save_config({
        "dot_role_channel_id": channel.id,
        "dot_role_id": role.id,
        "dot_log_channel_id": log_channel.id,
    })
    try:
        await interaction.followup.send(
            f"✅ ตั้งค่าระบบรับยศอัตโนมัติแล้วครับ\n"
            f"📢 ห้องรับยศ: {channel.mention}\n"
            f"🏷️ ยศที่จะให้: {role.mention}\n"
            f"📋 ห้อง Log: {log_channel.mention}",
            ephemeral=True
        )
    except Exception:
        pass

@bot.tree.command(name="check_dot_role", description="ดูการตั้งค่าระบบรับยศอัตโนมัติปัจจุบัน")
async def check_dot_role(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    if DOT_ROLE_CHANNEL_ID and DOT_ROLE_ID and DOT_LOG_CHANNEL_ID:
        ch = interaction.guild.get_channel(DOT_ROLE_CHANNEL_ID)
        role = interaction.guild.get_role(DOT_ROLE_ID)
        log_ch = interaction.guild.get_channel(DOT_LOG_CHANNEL_ID)
        await interaction.response.send_message(
            f"✅ ระบบรับยศอัตโนมัติ **เปิดอยู่**\n"
            f"📢 ห้องรับยศ: {ch.mention if ch else DOT_ROLE_CHANNEL_ID}\n"
            f"🏷️ ยศที่จะให้: {role.mention if role else DOT_ROLE_ID}\n"
            f"📋 ห้อง Log: {log_ch.mention if log_ch else DOT_LOG_CHANNEL_ID}",
            ephemeral=True
        )
    else:
        await interaction.response.send_message("❌ ระบบรับยศอัตโนมัติ **ปิดอยู่** ยังไม่ได้ตั้งค่า", ephemeral=True)

@bot.tree.command(name="remove_dot_role", description="ปิดระบบรับยศอัตโนมัติเมื่อพิมพ์ .")
async def remove_dot_role(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    global DOT_ROLE_CHANNEL_ID, DOT_ROLE_ID, DOT_LOG_CHANNEL_ID
    DOT_ROLE_CHANNEL_ID = None
    DOT_ROLE_ID = None
    DOT_LOG_CHANNEL_ID = None
    save_config({})
    try:
        await interaction.followup.send("✅ ปิดระบบรับยศอัตโนมัติแล้วครับ", ephemeral=True)
    except Exception:
        pass

ASTD_UNIVERSE_ID = 4996049426

async def fetch_roblox_players():
    url = f"https://games.roblox.com/v1/games?universeIds={ASTD_UNIVERSE_ID}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    game = data["data"][0]
                    return {
                        "playing": game.get("playing", 0),
                        "visits": game.get("visits", 0),
                        "name": game.get("name", "ASTD")
                    }
    except Exception as e:
        print(f"Roblox API error: {e}")
    return None

async def fetch_astd_data():
    pages = [
        ("Hero Summon", "https://allstartd.fandom.com/wiki/Hero_Summon"),
        ("Special Summons", "https://allstartd.fandom.com/wiki/Special_Summons"),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    result = {}
    try:
        async with aiohttp.ClientSession() as session:
            for label, url in pages:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    units = []
                    tables = soup.select("table.wikitable")
                    for table in tables[:2]:
                        rows = table.select("tbody tr")
                        for row in rows[1:8]:
                            cols = row.find_all("td")
                            if cols:
                                name = cols[0].get_text(strip=True)
                                if name and len(name) > 1:
                                    rate = cols[-1].get_text(strip=True) if len(cols) > 1 else ""
                                    units.append(f"• **{name}** `{rate}`" if rate else f"• **{name}**")
                    if not units:
                        for li in soup.select("ul li")[:8]:
                            text = li.get_text(strip=True)
                            if text:
                                units.append(f"• {text}")
                    if units:
                        result[label] = units
    except Exception as e:
        print(f"ASTD fetch error: {e}")
    return result if result else None

async def build_astd_embed():
    data, roblox = await asyncio.gather(fetch_astd_data(), fetch_roblox_players())
    embed = discord.Embed(
        title="🎮 All Star Tower Defense — ตู้ปัจจุบัน",
        color=discord.Color.gold(),
        url="https://allstartd.fandom.com/wiki/Summons"
    )
    if roblox:
        embed.add_field(
            name="📊 สถิติสด (Roblox)",
            value=f"👥 ผู้เล่นออนไลน์: **{roblox['playing']:,}** คน\n🏆 ยอดเข้าชมทั้งหมด: **{roblox['visits']:,}**",
            inline=False
        )
    if data:
        for label, units in data.items():
            embed.add_field(
                name=f"🎰 {label}",
                value="\n".join(units[:10]) or "ไม่พบข้อมูล",
                inline=False
            )
    else:
        embed.add_field(name="ตู้", value="ไม่สามารถดึงข้อมูลตู้ได้ในขณะนี้", inline=False)
    embed.add_field(
        name="🔗 ลิงก์",
        value="[Hero Summon](https://allstartd.fandom.com/wiki/Hero_Summon) | [Special Summons](https://allstartd.fandom.com/wiki/Special_Summons) | [Wiki](https://allstartd.fandom.com)",
        inline=False
    )
    embed.set_footer(text=f"อัปเดตล่าสุด: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')} น. | อัปเดตทุก 5 นาที")
    return embed

@tasks.loop(minutes=5)
async def astd_auto_update():
    global astd_message_id
    if ASTD_CHANNEL_ID is None:
        return
    channel = bot.get_channel(ASTD_CHANNEL_ID)
    if channel is None:
        return
    embed = await build_astd_embed()
    try:
        if astd_message_id:
            msg = await channel.fetch_message(astd_message_id)
            await msg.edit(embed=embed)
        else:
            msg = await channel.send(embed=embed)
            astd_message_id = msg.id
    except Exception:
        msg = await channel.send(embed=embed)
        astd_message_id = msg.id

@bot.tree.command(name="setup_astd", description="ตั้งค่าห้องโพสต์ข้อมูลตู้ ASTD อัตโนมัติ")
async def setup_astd(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    global ASTD_CHANNEL_ID, astd_message_id
    ASTD_CHANNEL_ID = channel.id
    astd_message_id = None
    await interaction.response.send_message(f"✅ ตั้งค่าห้อง ASTD เป็น {channel.mention} แล้วครับ บอทจะอัปเดตตู้ทุก 5 นาที")
    embed = await build_astd_embed()
    msg = await channel.send(embed=embed)
    astd_message_id = msg.id

@bot.tree.command(name="astd_check", description="เช็คตู้ ASTD ตอนนี้เลย")
async def astd_check(interaction: discord.Interaction):
    await interaction.response.defer()
    embed = await build_astd_embed()
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="remove_astd", description="ปิดระบบอัปเดตตู้ ASTD อัตโนมัติ")
async def remove_astd(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    global ASTD_CHANNEL_ID, astd_message_id
    ASTD_CHANNEL_ID = None
    astd_message_id = None
    await interaction.response.send_message("✅ ปิดระบบอัปเดต ASTD แล้วครับ")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    print(f'🤖 AI Channel ID: {AI_CHANNEL_ID}')
    if not astd_auto_update.is_running():
        astd_auto_update.start()

if __name__ == "__main__":
    keep_alive()
    import time
    while True:
        try:
            bot.run(TOKEN)
        except discord.errors.HTTPException as e:
            if e.status == 429:
                print("⚠️ Rate limited ขณะ login รอ 60 วินาทีแล้วลองใหม่...")
                time.sleep(60)
            else:
                raise
        except Exception as e:
            print(f"❌ เกิดข้อผิดพลาด: {e} — รอ 30 วินาทีแล้วลองใหม่...")
            time.sleep(30)
