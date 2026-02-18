import discord
from discord import app_commands
import sqlite3
import datetime
import os

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

conn = sqlite3.connect("houshu.db")
c = conn.cursor()

# =========================
# DB 初期化
# =========================

c.execute("""
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    role_type TEXT DEFAULT 'general',
    exempt_flag INTEGER DEFAULT 0,
    consecutive_fail INTEGER DEFAULT 0,
    savings INTEGER DEFAULT 0,
    carry_over INTEGER DEFAULT 0
)
""")

c.execute("""
CREATE TABLE IF NOT EXISTS reports(
    report_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    self_point INTEGER,
    final_point INTEGER,
    status TEXT,
    created_at TEXT
)
""")

conn.commit()

# =========================
# ユーザー登録
# =========================

def ensure_user(user_id):
    c.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
    if not c.fetchone():
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

# =========================
# 制作報告
# =========================

@tree.command(name="report", description="制作報告を提出")
@app_commands.describe(point="自己算出ポイント")
async def report(interaction: discord.Interaction, point: int):
    ensure_user(interaction.user.id)

    c.execute("""
    INSERT INTO reports(user_id, self_point, final_point, status, created_at)
    VALUES(?,?,?,?,?)
    """, (interaction.user.id, point, 0, "pending", str(datetime.datetime.now())))
    conn.commit()

    await interaction.response.send_message("✅ 報告を提出しました（承認待ち）", ephemeral=True)

# =========================
# 承認
# =========================

@tree.command(name="approve", description="報告を承認")
@app_commands.describe(report_id="報告ID", fixed_point="確定ポイント")
async def approve(interaction: discord.Interaction, report_id: int, fixed_point: int):

    c.execute("SELECT user_id FROM reports WHERE report_id=? AND status='pending'", (report_id,))
    result = c.fetchone()

    if not result:
        await interaction.response.send_message("報告が見つかりません", ephemeral=True)
        return

    user_id = result[0]

    c.execute("""
    UPDATE reports
    SET status='approved', final_point=?
    WHERE report_id=?
    """, (fixed_point, report_id))

    conn.commit()

    await interaction.response.send_message(f"✅ 報告 {report_id} を承認しました")

# =========================
# 月次決算
# =========================

@tree.command(name="monthly_close", description="月次決算確定（管理者専用）")
async def monthly_close(interaction: discord.Interaction):

    await interaction.response.defer()

    current_month = datetime.datetime.now().strftime("%Y-%m")

    c.execute("SELECT user_id FROM users")
    users = c.fetchall()

    for (user_id,) in users:

        ensure_user(user_id)

        c.execute("""
        SELECT SUM(final_point) FROM reports
        WHERE user_id=? AND status='approved'
        """, (user_id,))
        total = c.fetchone()[0] or 0

        c.execute("SELECT carry_over, consecutive_fail, exempt_flag FROM users WHERE user_id=?", (user_id,))
        carry, fail, exempt = c.fetchone()

        total += carry

        if exempt == 1:
            continue

        if total >= 20:
            new_carry = total - 20
            c.execute("""
            UPDATE users SET carry_over=?, consecutive_fail=0 WHERE user_id=?
            """, (new_carry, user_id))
        else:
            c.execute("""
            UPDATE users SET carry_over=0, consecutive_fail=? WHERE user_id=?
            """, (fail+1, user_id))

    conn.commit()

    await interaction.followup.send("🏛 月次決算を確定しました")

# =========================

@client.event
async def on_ready():
    await tree.sync()
    print("Bot 起動完了")

client.run(TOKEN)
