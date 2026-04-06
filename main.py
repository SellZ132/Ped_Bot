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
import random
from datetime import datetime, timezone

TOKEN = os.getenv("TOKEN_ID")
MY_GUILD_ID = int(os.getenv("MY_GUILD_ID"))

ALLOWED_USERS = [int(user_id) for user_id in os.getenv("ALLOWED_USERS").split(",")]

AI_CHANNEL_ID = int(os.getenv("AI_CHANNEL_ID"))
ASTD_CHANNEL_ID = int(os.getenv("ASTD_CHANNEL_ID")) if os.getenv("ASTD_CHANNEL_ID") else None
astd_message_id = int(os.getenv("ASTD_MESSAGE_ID")) if os.getenv("ASTD_MESSAGE_ID") else None

BANNER_CHANNEL_ID = None
BANNER_X_UNITS = "ยังไม่มีข้อมูล (ดูได้จากลิงก์สด)"
BANNER_Y_UNITS = "ยังไม่มีข้อมูล (ดูได้จากลิงก์สด)"
BANNER_Z_UNITS = "ยังไม่มีข้อมูล (ดูได้จากลิงก์สด)"
astd_message_id = None

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

    if message.author.id in BLOCKED_AI_USERS:
        await message.reply("🚫 คุณถูกบล็อกจากการใช้งาน AI ครับ")
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

@bot.tree.command(name="block_ai", description="บล็อกไม่ให้ผู้ใช้คนนี้ใช้ AI (เฉพาะ Admin)")
async def block_ai(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    if member.id in BLOCKED_AI_USERS:
        await interaction.response.send_message(f"⚠️ **{member.display_name}** ถูกบล็อกอยู่แล้วครับ", ephemeral=True)
        return

    BLOCKED_AI_USERS.append(member.id)
    await interaction.response.send_message(f"🚫 บล็อก **{member.display_name}** จากการใช้ AI แล้วครับ")

@bot.tree.command(name="unblock_ai", description="ปลดบล็อกให้ผู้ใช้คนนี้ใช้ AI ได้ (เฉพาะ Admin)")
async def unblock_ai(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    if member.id not in BLOCKED_AI_USERS:
        await interaction.response.send_message(f"⚠️ **{member.display_name}** ไม่ได้ถูกบล็อกอยู่ครับ", ephemeral=True)
        return

    BLOCKED_AI_USERS.remove(member.id)
    await interaction.response.send_message(f"✅ ปลดบล็อก **{member.display_name}** แล้ว สามารถใช้ AI ได้แล้วครับ")

@bot.tree.command(name="list_blocked_ai", description="ดูรายชื่อคนที่ถูกบล็อกจากการใช้ AI")
async def list_blocked_ai(interaction: discord.Interaction):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    if not BLOCKED_AI_USERS:
        await interaction.response.send_message("✅ ไม่มีใครถูกบล็อกอยู่ครับ", ephemeral=True)
        return

    lines = []
    for uid in BLOCKED_AI_USERS:
        member = interaction.guild.get_member(uid)
        name = member.display_name if member else f"ID: {uid}"
        lines.append(f"🚫 {name}")

    await interaction.response.send_message("**รายชื่อคนที่ถูกบล็อก AI:**\n" + "\n".join(lines), ephemeral=True)

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

@bot.tree.command(name="chaos_move", description="ย้าย User ไปห้อง Voice สุ่มรัวๆ ตามจำนวนที่กำหนด (เฉพาะ Admin)")
async def chaos_move(interaction: discord.Interaction, member: discord.Member, times: int):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    if times < 1 or times > 100:
        await interaction.response.send_message("❌ ใส่จำนวนระหว่าง 1-100 ครับ", ephemeral=True)
        return

    if not member.voice or not member.voice.channel:
        await interaction.response.send_message("❌ คนนี้ไม่ได้อยู่ใน Voice Channel ครับ", ephemeral=True)
        return

    voice_channels = [ch for ch in interaction.guild.channels if isinstance(ch, discord.VoiceChannel)]
    if len(voice_channels) < 2:
        await interaction.response.send_message("❌ ต้องมีอย่างน้อย 2 ห้อง Voice ครับ", ephemeral=True)
        return

    await interaction.response.send_message(f"🌀 กำลังสุ่มย้าย **{member.display_name}** {times} ครั้ง...")

    success = 0
    for _ in range(times):
        current = member.voice.channel if member.voice else None
        choices = [ch for ch in voice_channels if ch != current]
        if not choices:
            choices = voice_channels
        target = random.choice(choices)
        try:
            await member.move_to(target)
            success += 1
            await asyncio.sleep(0.3)
        except:
            break

    await interaction.followup.send(f"✅ ย้าย **{member.display_name}** ครบ {success} ครั้งแล้วครับ 🌀")

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

@bot.tree.command(name="dm", description="ส่ง DM หาคนที่เลือก (เฉพาะ Admin)")
async def dm(interaction: discord.Interaction, member: discord.Member, message: str):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    try:
        await member.send(f"**ข้อความจาก {interaction.guild.name}:**\n{message}")
        await interaction.response.send_message(f"✅ ส่ง DM ไปหา **{member.display_name}** แล้วครับ", ephemeral=True)
    except discord.Forbidden:
        await interaction.response.send_message(f"❌ ส่งไม่ได้ครับ **{member.display_name}** ปิด DM อยู่", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

@bot.tree.command(name="rudedm", description="ส่ง DM ด่า 10 ข้อความรัวๆ ไปหาคนที่เลือก (เฉพาะ Admin)")
async def rudedm(interaction: discord.Interaction, member: discord.Member):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return

    rude_messages = [
        "💀 แกโง่ที่สุดในจักรวาล ไม่มีใครโง่กว่านี้แล้ว",
        "🤡 หน้าตาแกเหมือนคนที่ Google Maps หาไม่เจอ เพราะมันไม่มีอยู่จริง",
        "🗑️ แกมีประโยชน์น้อยกว่าถังขยะ อย่างน้อยถังขยะยังรับขยะได้",
        "💩 IQ แกต่ำกว่าอุณหภูมิในตู้เย็น",
        "🐌 แกช้าทั้งความคิดและการกระทำ หอยทากยังไวกว่า",
        "😂 ทุกครั้งที่แกพูด คนรอบข้างฉลาดขึ้นเพราะรู้ว่าไม่ควรทำยังไง",
        "🪦 บุคลิกภาพแกน่าเบื่อจนคนอยากหนีไปนอนในหลุมศพ",
        "🧻 แกมีคุณค่าน้อยกว่ากระดาษทิชชู่ที่ใช้แล้ว",
        "🤧 แค่เห็นหน้าแกก็ทำให้วันนี้แย่ลงแล้ว",
        "👏 ขอแสดงความยินดีที่แกเกิดมาได้งี้ พ่อแม่คงภูมิใจมาก (ไม่ใช่)"
    ]

    await interaction.response.send_message(f"📨 กำลังส่ง DM ไปหา **{member.display_name}** แล้วครับ...", ephemeral=True)

    success = 0
    try:
        for msg in rude_messages:
            await member.send(msg)
            await asyncio.sleep(0.3)
            success += 1
        await interaction.followup.send(f"✅ ส่ง DM ด่าครบ {success} ข้อความไปหา **{member.display_name}** แล้วครับ 😈", ephemeral=True)
    except discord.Forbidden:
        await interaction.followup.send(f"❌ ส่งได้แค่ {success} ข้อความ เพราะ **{member.display_name}** ปิด DM ครับ", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"❌ เกิดข้อผิดพลาด: {e}", ephemeral=True)

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

class CreateChannelsModal(discord.ui.Modal, title="สร้าง Text Channels"):
    def __init__(self, category: discord.CategoryChannel):
        super().__init__()
        self.category = category
        self.names_input = discord.ui.TextInput(
            label="ชื่อห้อง (ทีละบรรทัด — วาง Paste ได้เลย)",
            style=discord.TextStyle.paragraph,
            placeholder="🔞 | ห้องตัวอย่าง\n⭐ | ห้อง2\n🟢 | ห้อง3",
            required=True,
            max_length=4000
        )
        self.add_item(self.names_input)

    async def on_submit(self, interaction: discord.Interaction):
        channel_names = [n.strip() for n in self.names_input.value.splitlines() if n.strip()]
        if not channel_names:
            await interaction.response.send_message("❌ ไม่พบชื่อห้องครับ", ephemeral=True)
            return

        await interaction.response.send_message(f"🏗️ กำลังสร้าง {len(channel_names)} ห้องใน **{self.category.name}**...")

        created = []
        failed = []
        for name in channel_names:
            try:
                await interaction.guild.create_text_channel(name=name, category=self.category)
                created.append(name)
            except Exception:
                failed.append(name)

        result = f"✅ สร้างสำเร็จ {len(created)} ห้อง ในหมวด **{self.category.name}**:\n"
        result += "\n".join(f"💬 {n}" for n in created)
        if failed:
            result += f"\n\n❌ สร้างไม่สำเร็จ ({len(failed)} ห้อง): {', '.join(failed)}"
        await interaction.followup.send(result)

class CopyChannelModal(discord.ui.Modal, title="คัดลอกการตั้งค่าห้อง"):
    def __init__(self, source: discord.abc.GuildChannel, category: discord.CategoryChannel):
        super().__init__()
        self.source = source
        self.category = category

        self.skip_input = discord.ui.TextInput(
            label="ข้ามห้องที่มีคำ (ทีละบรรทัด / ว่างได้)",
            style=discord.TextStyle.paragraph,
            placeholder="ตัวอย่าง\ntest\nสาธิต",
            required=False,
            max_length=1000
        )
        self.only_input = discord.ui.TextInput(
            label="เฉพาะห้องที่มีคำ (ทีละบรรทัด / ว่างได้)",
            style=discord.TextStyle.paragraph,
            placeholder="ว่างไว้ = เพิ่มทุกห้อง\nใส่คำ = เพิ่มเฉพาะห้องที่มีคำนั้น",
            required=False,
            max_length=1000
        )
        self.add_item(self.skip_input)
        self.add_item(self.only_input)

    async def on_submit(self, interaction: discord.Interaction):
        skip_words = [w.strip().lower() for w in self.skip_input.value.splitlines() if w.strip()]
        only_words = [w.strip().lower() for w in self.only_input.value.splitlines() if w.strip()]

        all_channels = [ch for ch in self.category.channels if ch.id != self.source.id]

        targets = []
        skipped = []
        for ch in all_channels:
            name_lower = ch.name.lower()
            if skip_words and any(w in name_lower for w in skip_words):
                skipped.append(ch.name)
                continue
            if only_words and not any(w in name_lower for w in only_words):
                skipped.append(ch.name)
                continue
            targets.append(ch)

        if not targets:
            await interaction.response.send_message("❌ ไม่มีห้องที่ตรงกับเงื่อนไขครับ", ephemeral=True)
            return

        await interaction.response.send_message(
            f"🔧 กำลังคัดลอกจาก **{self.source.name}** → {len(targets)} ห้องในหมวด **{self.category.name}**"
            + (f"\n⏭️ ข้าม {len(skipped)} ห้อง" if skipped else "")
        )

        success = []
        failed = []
        for target in targets:
            try:
                kwargs = {"overwrites": self.source.overwrites}
                if isinstance(target, discord.TextChannel) and isinstance(self.source, discord.TextChannel):
                    kwargs["topic"] = self.source.topic
                    kwargs["nsfw"] = self.source.nsfw
                    kwargs["slowmode_delay"] = self.source.slowmode_delay
                elif isinstance(target, discord.VoiceChannel) and isinstance(self.source, discord.VoiceChannel):
                    kwargs["bitrate"] = self.source.bitrate
                    kwargs["user_limit"] = self.source.user_limit
                await target.edit(**kwargs)
                success.append(target.name)
            except Exception as e:
                failed.append(f"{target.name} ({str(e)[:40]})")

        result = f"✅ คัดลอกสำเร็จ {len(success)}/{len(targets)} ห้อง:\n"
        result += "\n".join(f"🔧 {n}" for n in success)
        if skipped:
            result += f"\n\n⏭️ ข้ามไป {len(skipped)} ห้อง:\n" + "\n".join(f"• {n}" for n in skipped)
        if failed:
            result += f"\n\n❌ ล้มเหลว {len(failed)} ห้อง:\n" + "\n".join(failed)
        await interaction.followup.send(result)

@bot.tree.command(name="copychannel", description="คัดลอกการตั้งค่าห้อง ไปทุกห้องในหมวดหมู่ที่เลือก (เฉพาะ Admin)")
async def copychannel(interaction: discord.Interaction, source: discord.TextChannel, category: discord.CategoryChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    modal = CopyChannelModal(source=source, category=category)
    await interaction.response.send_modal(modal)

@bot.tree.command(name="createchannels", description="สร้าง Text Channel หลายห้องในหมวดหมู่ที่เลือก (เฉพาะ Admin)")
async def createchannels(interaction: discord.Interaction, category: discord.CategoryChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    modal = CreateChannelsModal(category=category)
    await interaction.response.send_modal(modal)

def get_banner_countdown():
    now = datetime.now(timezone.utc)
    minutes = now.minute
    seconds = now.second
    if minutes < 30:
        secs_left = (30 - minutes) * 60 - seconds
        next_banner = "Y"
    else:
        secs_left = (60 - minutes) * 60 - seconds
        next_banner = "X"
    m = secs_left // 60
    s = secs_left % 60
    return next_banner, m, s

@tasks.loop(seconds=30)
async def banner_notify_task():
    if BANNER_CHANNEL_ID is None:
        return
    now = datetime.now(timezone.utc)
    if now.second > 15:
        return
    if now.minute != 0:
        return
    channel = bot.get_channel(BANNER_CHANNEL_ID)
    if channel is None:
        return
    embed = discord.Embed(
        title="🎰 All Star Tower Defense — ตู้รีเซ็ตแล้ว!",
        description="ตู้ทั้งหมดรีเซ็ตแล้ว เช็คตัวละครในตู้ได้เลยครับ!",
        color=discord.Color.gold()
    )
    embed.add_field(name="🟡 Banner X", value=BANNER_X_UNITS, inline=False)
    embed.add_field(name="🔵 Banner Y", value=BANNER_Y_UNITS, inline=False)
    embed.add_field(name="🔴 Banner Z", value=BANNER_Z_UNITS, inline=False)
    embed.add_field(name="📖 Wiki", value="[Hero Summon Wiki](https://allstartd.fandom.com/wiki/Hero_Summon)", inline=False)
    embed.set_footer(text="ใช้ /updatebanner X/Y/Z เพื่ออัปเดตตัวละคร • รีเซ็ตทุก 1 ชั่วโมง")
    await channel.send("🎰 **ตู้รีเซ็ตแล้ว!**", embed=embed)

@bot.tree.command(name="setbanner_channel", description="ตั้งห้องรับแจ้งเตือนตู้ ASTD รีเซ็ตอัตโนมัติ (เฉพาะ Admin)")
async def setbanner_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    global BANNER_CHANNEL_ID
    BANNER_CHANNEL_ID = channel.id
    embed = discord.Embed(
        title="✅ ตั้งค่าระบบแจ้งเตือนตู้ ASTD สำเร็จ!",
        description=f"ห้องที่จะรับแจ้งเตือน: {channel.mention}",
        color=discord.Color.green()
    )
    embed.add_field(name="🔄 ตู้ X, Y, Z", value="แจ้งเตือนทุกชั่วโมงที่ :00 อัตโนมัติ", inline=False)
    embed.add_field(name="📖 Wiki", value="[Hero Summon Wiki](https://allstartd.fandom.com/wiki/Hero_Summon)", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="updatebanner", description="อัปเดตตัวละครในตู้ ASTD X/Y/Z (เฉพาะ Admin)")
async def updatebanner(interaction: discord.Interaction, banner: str, units: str):
    if interaction.user.id not in ALLOWED_USERS:
        await interaction.response.send_message("❌ คุณไม่มีสิทธิ์ใช้คำสั่งนี้", ephemeral=True)
        return
    global BANNER_X_UNITS, BANNER_Y_UNITS, BANNER_Z_UNITS
    banner = banner.upper()
    if banner == "X":
        BANNER_X_UNITS = units
        await interaction.response.send_message(f"✅ อัปเดต Banner X:\n{units}")
    elif banner == "Y":
        BANNER_Y_UNITS = units
        await interaction.response.send_message(f"✅ อัปเดต Banner Y:\n{units}")
    elif banner == "Z":
        BANNER_Z_UNITS = units
        await interaction.response.send_message(f"✅ อัปเดต Banner Z:\n{units}")
    else:
        await interaction.response.send_message("❌ ใส่ X, Y หรือ Z เท่านั้นครับ", ephemeral=True)

@bot.tree.command(name="banner", description="เช็คข้อมูลตู้ ASTD และนับถอยหลัง")
async def banner_check(interaction: discord.Interaction):
    _, m, s = get_banner_countdown()
    embed = discord.Embed(
        title="🎰 All Star Tower Defense — Banner Info",
        color=discord.Color.purple()
    )
    embed.add_field(name="🟡 Banner X", value=BANNER_X_UNITS, inline=False)
    embed.add_field(name="🔵 Banner Y", value=BANNER_Y_UNITS, inline=False)
    embed.add_field(name="🔴 Banner Z", value=BANNER_Z_UNITS, inline=False)
    embed.add_field(name="⏱️ รีเซ็ตใน", value=f"**{m} นาที {s} วินาที**", inline=False)
    embed.add_field(name="📖 Wiki", value="[Hero Summon Wiki](https://allstartd.fandom.com/wiki/Hero_Summon)", inline=False)
    embed.set_footer(text="ตู้รีเซ็ตทุก 1 ชั่วโมง • ใช้ /updatebanner X/Y/Z เพื่ออัปเดต")
    await interaction.response.send_message(embed=embed)

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
    if not banner_notify_task.is_running():
        banner_notify_task.start()

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
