import os
import io
import html
import asyncio
from datetime import datetime, timezone
from typing import List
from threading import Thread
from flask import Flask

import aiosqlite
import discord
from discord.ext import commands
from dotenv import load_dotenv

# --- Serveur Flask pour Render ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

Thread(target=run_web).start()
# --------------------------------

# --- Charger les variables d'environnement ---
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if TOKEN is None:
    raise ValueError("Le token Discord n'a pas été trouvé ! Vérifie ton fichier .env")

# --- Intents ---
INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.message_content = True

DB_FILE = "tickets.db"

# --- Vue du panneau ---
class PanelView(discord.ui.View):
    def __init__(self, types_list: List[str]):
        super().__init__(timeout=None)
        self.add_item(TicketTypeSelect(types_list))

class TicketTypeSelect(discord.ui.Select):
    def __init__(self, types_list: List[str]):
        options = [discord.SelectOption(label=t) for t in types_list]
        super().__init__(
            placeholder="Choisissez une catégorie de ticket…",
            options=options,
            min_values=1,
            max_values=1,
            custom_id="ticket_type_select"
        )

    async def callback(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.values[0])

# --- Bot principal ---
bot = commands.Bot(command_prefix="-", intents=INTENTS, help_command=None)

@bot.event
async def on_ready():
    bot.db = await aiosqlite.connect(DB_FILE)
    await bot.db.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            user_id INTEGER,
            channel_id INTEGER,
            type TEXT,
            created_at TEXT
        )
    """)
    await bot.db.commit()
    print(f"Connecté en tant que {bot.user}")

# --- Création ticket ---
async def create_ticket(inter: discord.Interaction, ticket_type: str):
    await inter.response.defer(ephemeral=True)
    guild = inter.guild
    if guild is None:
        return await inter.followup.send("Commande invalide.", ephemeral=True)

    category = guild.get_channel(1390037645643747388)
    if not isinstance(category, discord.CategoryChannel):
        category = None

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        inter.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        guild.get_role(1393279127301128354): discord.PermissionOverwrite(view_channel=True, send_messages=True),
        guild.get_role(1390390153595457726): discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    channel = await guild.create_text_channel(
        name=f"ticket-{inter.user.name}",
        category=category,
        overwrites=overwrites
    )

    await bot.db.execute(
        "INSERT INTO tickets (user_id, channel_id, type, created_at) VALUES (?, ?, ?, ?)",
        (inter.user.id, channel.id, ticket_type, datetime.now(timezone.utc).isoformat())
    )
    await bot.db.commit()

    embed = discord.Embed(
        title=f"Ticket {ticket_type}",
        description=f"Bonjour {inter.user.mention}, un membre du staff va vous répondre.",
        color=0x2ECC71
    )
    view = CloseTicketView()
    await channel.send(embed=embed, view=view)
    await channel.send(f"<@&1393279127301128354> <@&1390390153595457726>")

    await inter.followup.send(f"Ticket créé : {channel.mention}", ephemeral=True)

# --- Fermeture ticket ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_button")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Confirmez-vous la fermeture ?", view=ConfirmCloseView(), ephemeral=True)

class ConfirmCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="Oui, fermer", style=discord.ButtonStyle.danger, custom_id="confirm_close_ticket")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await save_transcript_and_close(interaction.channel)

    @discord.ui.button(label="Annuler", style=discord.ButtonStyle.secondary, custom_id="cancel_close_ticket")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

async def save_transcript_and_close(channel: discord.TextChannel):
    messages = [msg async for msg in channel.history(limit=None, oldest_first=True)]
    transcript = "".join(f"[{m.created_at}] {m.author}: {m.clean_content}\n" for m in messages)
    filename = f"transcript-{channel.name}.html"
    html_content = f"<pre>{html.escape(transcript)}</pre>"

    with open(filename, "w", encoding="utf-8") as f:
        f.write(html_content)

    guild = channel.guild
    transcript_channel = guild.get_channel(1394765363073515560)
    if isinstance(transcript_channel, discord.TextChannel):
        await transcript_channel.send(file=discord.File(filename))

    await channel.delete()

# --- Commande panel ---
@bot.command(name="panel")
@commands.has_permissions(administrator=True)
async def panel_cmd(ctx):
    channel = bot.get_channel(1390037993854730371)
    if not isinstance(channel, discord.TextChannel):
        return await ctx.send("Salon introuvable.")

    description = (
        "**__Contacter le Support de Kiboka__**\n\n"
        "Le support du serveur est disponible 24H/24 et 7J/7\n\n"
        "Il y a 3 catégories de tickets :\n\n"
        "**__Ticket Staff__** : Pour devenir staff, réclamer un rank up ou récupérer des rôles.\n"
        "**__Ticket Partenariat__** : Pour signaler un problème ou faire un report.\n"
        "**__Ticket Modérateur__** : Pour postuler comme modérateur.\n\n"
        "⚠ Pas de demandes liées aux concours nitro ici.\n\n"
        "- Support Kiboka"
    )

    types_list = ["Ticket Staff", "Ticket Partenariat", "Ticket Modérateur"]
    view = PanelView(types_list)
    embed = discord.Embed(title="Centre d'aide Kiboka", description=description, color=0x5865F2)
    await channel.send(embed=embed, view=view)
    await ctx.send("Panneau envoyé.")

import threading
from flask import Flask
import os

app = Flask('')

@app.route('/')
def home():
    return "Bot is alive!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)

# Démarrer le serveur dans un thread séparé
threading.Thread(target=run).start()


# --- Lancer le bot ---
bot.run(TOKEN)

