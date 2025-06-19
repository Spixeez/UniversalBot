import discord
from discord import app_commands
from discord.ext import tasks
import asyncio
import json
import os
import re
from mcstatus import JavaServer  # Updated import for mcstatus
import yt_dlp
from collections import deque

intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Enable members intent for on_member_join event
bot = discord.Client(intents=intents)
tree = app_commands.CommandTree(bot)

CONFIG_FILE = "config.json"

def load_config():
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    else:
        return {}

def save_config(config):
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)
        # Ensure data is flushed to disk
        f.flush()
        os.fsync(f.fileno())

config = load_config()
status_messages = {}

@bot.event
async def on_member_join(member: discord.Member):
    print(f"Member joined: {member.name} in guild {member.guild.name}")
    guild_id = str(member.guild.id)
    guild_config = config.get(guild_id, {})
    auto_role_id = guild_config.get("auto_role_id")
    if auto_role_id:
        role = member.guild.get_role(auto_role_id)
        if role:
            try:
                await member.add_roles(role)
                print(f"Auto role {role.name} assigned to {member.name} in guild {member.guild.name}")
            except Exception as e:
                print(f"Failed to assign auto role in guild {member.guild.name}: {e}")

    join_channel_id = guild_config.get("join_announcement_channel_id")
    join_message = guild_config.get("join_announcement_message")
    if join_channel_id and join_message:
        channel = member.guild.get_channel(join_channel_id)
        if channel:
            try:
                embed = discord.Embed(title="Bienvenue !", description=join_message.replace("{member}", member.mention).replace("{name}", member.name), color=discord.Color.green())
                await channel.send(embed=embed)
            except Exception as e:
                print(f"Failed to send join announcement in guild {member.guild.name}: {e}")

@bot.event
async def on_ready():
    await tree.sync()
    print(f"Connecté comme {bot.user}")
    update_status.start()
    giveaway_loop.start()

@tree.command(name="setautorole", description="Configurer le rôle automatique de bienvenue")
@app_commands.describe(role="Rôle à attribuer automatiquement aux nouveaux membres")
@app_commands.checks.has_permissions(administrator=True)
async def setautorole(interaction: discord.Interaction, role: discord.Role):
    guild_id = str(interaction.guild.id)
    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]["auto_role_id"] = role.id
    save_config(config)
    await interaction.response.send_message(f"Rôle automatique de bienvenue configuré : {role.mention}", ephemeral=True)

@tree.command(name="setjoinannouncement", description="Configurer le message d'annonce de bienvenue")
@app_commands.describe(channel="Salon pour l'annonce", message="Message d'annonce (utilisez {member} pour mentionner)")
@app_commands.checks.has_permissions(administrator=True)
async def setjoinannouncement(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    guild_id = str(interaction.guild.id)
    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]["join_announcement_channel_id"] = channel.id
    config[guild_id]["join_announcement_message"] = message
    save_config(config)
    await interaction.response.send_message(f"Message d'annonce de bienvenue configuré dans {channel.mention}", ephemeral=True)

@bot.event
async def on_member_remove(member: discord.Member):
    print(f"Member left: {member.name} in guild {member.guild.name}")
    guild_id = str(member.guild.id)
    guild_config = config.get(guild_id, {})
    leave_channel_id = guild_config.get("leave_announcement_channel_id")
    leave_message = guild_config.get("leave_announcement_message")
    if leave_channel_id and leave_message:
        channel = member.guild.get_channel(leave_channel_id)
        if channel:
            try:
                embed = discord.Embed(title="Au revoir !", description=leave_message.replace("{member}", member.name), color=discord.Color.red())
                await channel.send(embed=embed)
            except Exception as e:
                print(f"Failed to send leave announcement in guild {member.guild.name}: {e}")

@tree.command(name="setleaveannouncement", description="Configurer le message d'annonce de départ")
@app_commands.describe(channel="Salon pour l'annonce", message="Message d'annonce (utilisez {member} pour le nom)")
@app_commands.checks.has_permissions(administrator=True)
async def setleaveannouncement(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    guild_id = str(interaction.guild.id)
    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]["leave_announcement_channel_id"] = channel.id
    config[guild_id]["leave_announcement_message"] = message
    save_config(config)
    await interaction.response.send_message(f"Message d'annonce de départ configuré dans {channel.mention}", ephemeral=True)

# ----------- /config -----------
@tree.command(name="config", description="Configure IP Minecraft + salon de statut")
@app_commands.describe(
    ip="Adresse IP du serveur Minecraft",
    port="Port du serveur Minecraft (default 25565)",
    channel="Salon pour afficher le statut"
)
@app_commands.checks.has_permissions(administrator=True)
async def config_command(interaction: discord.Interaction, ip: str, port: int = 25565, channel: discord.TextChannel = None):
    guild_id = str(interaction.guild.id)
    config[guild_id] = {
        "ip": ip,
        "port": port,
        "channel_id": channel.id if channel else None
    }
    save_config(config)
    await interaction.response.send_message(f"Config enregistrée : {ip}:{port}, salon {channel.mention if channel else 'non défini'}", ephemeral=True)

@tree.command(name="kick", description="Expulser un membre")
@app_commands.describe(member="Membre à expulser", reason="Raison de l'expulsion")
@app_commands.checks.has_permissions(administrator=True)
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    try:
        await member.kick(reason=reason)
        await interaction.response.send_message(f"{member.mention} a été expulsé. Raison: {reason if reason else 'Non spécifiée'}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de l'expulsion: {e}", ephemeral=True)

@tree.command(name="ban", description="Bannir un membre")
@app_commands.describe(member="Membre à bannir", reason="Raison du bannissement")
@app_commands.checks.has_permissions(administrator=True)
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = None):
    try:
        await member.ban(reason=reason)
        await interaction.response.send_message(f"{member.mention} a été banni. Raison: {reason if reason else 'Non spécifiée'}")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors du bannissement: {e}", ephemeral=True)

@tree.command(name="unban", description="Débannir un membre")
@app_commands.describe(user="Nom complet du membre (ex: User#1234)")
@app_commands.checks.has_permissions(administrator=True)
async def unban(interaction: discord.Interaction, user: str):
    banned_users = await interaction.guild.bans()
    user_name, user_discriminator = user.split("#")
    for ban_entry in banned_users:
        if (ban_entry.user.name, ban_entry.user.discriminator) == (user_name, user_discriminator):
            try:
                await interaction.guild.unban(ban_entry.user)
                await interaction.response.send_message(f"{user} a été débanni.")
                return
            except Exception as e:
                await interaction.response.send_message(f"Erreur lors du débannissement: {e}", ephemeral=True)
                return
    await interaction.response.send_message(f"Utilisateur {user} non trouvé dans la liste des bannis.", ephemeral=True)

@tree.command(name="purge", description="Supprimer un nombre de messages")
@app_commands.describe(amount="Nombre de messages à supprimer (max 100)")
@app_commands.checks.has_permissions(administrator=True)
async def purge(interaction: discord.Interaction, amount: int):
    if amount < 1 or amount > 100:
        await interaction.response.send_message("Le nombre doit être entre 1 et 100.", ephemeral=True)
        return
    try:
        deleted = await interaction.channel.purge(limit=amount)
        await interaction.response.send_message(f"{len(deleted)} messages supprimés.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de la suppression: {e}", ephemeral=True)

@tree.command(name="mute", description="Mettre un membre en sourdine")
@app_commands.describe(member="Membre à mettre en sourdine", duration="Durée en minutes (optionnel, laisser vide pour mute permanent)")
@app_commands.checks.has_permissions(administrator=True)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: int = None):
    guild = interaction.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if not muted_role:
        try:
            muted_role = await guild.create_role(name="Muted", permissions=discord.Permissions(send_messages=False, add_reactions=False, speak=False, connect=False))
            for channel in guild.channels:
                await channel.set_permissions(muted_role, send_messages=False, add_reactions=False, speak=False, connect=False)
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors de la création du rôle Muted: {e}", ephemeral=True)
            return
    try:
        await member.add_roles(muted_role)
        if duration:
            await interaction.response.send_message(f"{member.mention} est en sourdine pour {duration} minutes.")
            await asyncio.sleep(duration * 60)
            await member.remove_roles(muted_role)
            await interaction.channel.send(f"{member.mention} n'est plus en sourdine.")
        else:
            await interaction.response.send_message(f"{member.mention} est en sourdine permanente.")
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de la mise en sourdine: {e}", ephemeral=True)

@tree.command(name="unmute", description="Enlever la sourdine d'un membre")
@app_commands.describe(member="Membre à enlever de la sourdine")
@app_commands.checks.has_permissions(administrator=True)
async def unmute(interaction: discord.Interaction, member: discord.Member):
    guild = interaction.guild
    muted_role = discord.utils.get(guild.roles, name="Muted")
    if not muted_role:
        await interaction.response.send_message("Le rôle Muted n'existe pas.", ephemeral=True)
        return
    try:
        if muted_role in member.roles:
            await member.remove_roles(muted_role)
            await interaction.response.send_message(f"{member.mention} n'est plus en sourdine.")
        else:
            await interaction.response.send_message(f"{member.mention} n'était pas en sourdine.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Erreur lors de la suppression de la sourdine: {e}", ephemeral=True)

# ----------- /play -----------
music_queues = {}

@tree.command(name="play", description="Jouer musique YouTube")
@app_commands.describe(url="Lien YouTube ou mots clés")
async def play(interaction: discord.Interaction, url: str):
    voice_state = interaction.user.voice
    if not voice_state or not voice_state.channel:
        await interaction.response.send_message("Va dans un vocal avant stp", ephemeral=True)
        return

    guild = interaction.guild
    voice_client = guild.voice_client

    try:
        print(f"Attempting voice connection for guild {guild.id} in channel {voice_state.channel.id}")
        channel = voice_state.channel
        permissions = channel.permissions_for(guild.me)
        print(f"Voice channel region: {getattr(channel, 'rtc_region', 'automatic')}")
        print(f"Bot permissions in channel: connect={permissions.connect}, speak={permissions.speak}")
        if not permissions.connect or not permissions.speak:
            await interaction.response.send_message("Je n'ai pas les permissions nécessaires pour me connecter ou parler dans ce salon vocal.", ephemeral=True)
            return
        if not voice_client:
            voice_client = await channel.connect()
            print(f"Connected to voice channel {channel.id} in guild {guild.id}")
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)
            print(f"Moved voice client to channel {channel.id} in guild {guild.id}")
    except Exception as e:
        print(f"Voice connection error in guild {guild.id}: {e}")
        await interaction.response.send_message(f"Erreur de connexion vocale: {e}", ephemeral=True)
        return

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'default_search': 'auto',
        'noplaylist': True,
    }

    try:
        await interaction.response.defer()
    except discord.errors.InteractionResponded:
        pass

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if 'entries' in info:
                info = info['entries'][0]
            url2 = info['url']
            title = info.get('title', 'Musique inconnue')
            thumbnail = info.get('thumbnail')
            uploader = info.get('uploader')

        queue = music_queues.setdefault(guild.id, deque())
        queue.append((url2, title, thumbnail, uploader))

        if not voice_client.is_playing():
            url2, title, thumbnail, uploader = queue.popleft()
            source = discord.FFmpegPCMAudio(url2)
            voice_client.play(source, after=lambda e: play_next(guild.id, voice_client))

            embed = discord.Embed(title=title, description=f"Par {uploader}", color=discord.Color.blue())
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(f"🎵 Ajouté à la file d'attente : **{title}**")
    except Exception as e:
        await interaction.followup.send(f"Erreur: {e}")

@bot.event
async def on_voice_state_update(member, before, after):
    print(f"Voice state update for {member.name}: before={before.channel if before else None}, after={after.channel if after else None}")
    guild = member.guild
    voice_client = guild.voice_client
    if voice_client and voice_client.channel:
        if not any(m.voice.channel == voice_client.channel for m in guild.members if m.voice):
            try:
                await voice_client.disconnect()
                print(f"Disconnected from voice channel {voice_client.channel} due to no members present.")
            except Exception as e:
                print(f"Error disconnecting from voice channel: {e}")

def play_next(guild_id, voice_client):
    queue = music_queues.get(guild_id)
    if queue and len(queue) > 0:
        url2, title, thumbnail, uploader = queue.popleft()
        source = discord.FFmpegPCMAudio(url2)
        voice_client.play(source, after=lambda e: play_next(guild_id, voice_client))

# ----------- /leave -----------
@tree.command(name="pause", description="Mettre la musique en pause")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("Musique en pause", ephemeral=True)
    else:
        await interaction.response.send_message("Aucune musique en cours de lecture", ephemeral=True)

@tree.command(name="resume", description="Reprendre la musique")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("Musique reprise", ephemeral=True)
    else:
        await interaction.response.send_message("La musique n'est pas en pause", ephemeral=True)

@tree.command(name="stop", description="Arrêter la musique et vider la file d'attente")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client:
        voice_client.stop()
        music_queues.pop(interaction.guild.id, None)
        await interaction.response.send_message("Musique arrêtée et file d'attente vidée", ephemeral=True)
    else:
        await interaction.response.send_message("Je ne suis pas dans un vocal", ephemeral=True)

@tree.command(name="skip", description="Passer la musique en cours")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("Musique passée", ephemeral=True)
    else:
        await interaction.response.send_message("Aucune musique en cours de lecture", ephemeral=True)

@tree.command(name="queue", description="Afficher la file d'attente")
async def queue_command(interaction: discord.Interaction):
    queue = music_queues.get(interaction.guild.id, deque())
    if not queue:
        await interaction.response.send_message("La file d'attente est vide", ephemeral=True)
        return
    description = ""
    for i, (_, title, _, _) in enumerate(queue, start=1):
        description += f"{i}. {title}\n"
    embed = discord.Embed(title="File d'attente", description=description, color=discord.Color.blue())
    await interaction.response.send_message(embed=embed)

# ----------- Ping Minecraft -----------

async def ping_minecraft(ip, port=25565):
    server = JavaServer.lookup(f"{ip}:{port}")
    loop = asyncio.get_event_loop()
    try:
        status = await loop.run_in_executor(None, server.status)
        player_sample = []
        if status.players.sample:
            player_sample = [player.name for player in status.players.sample]
        return {
            "online": True,
            "players": status.players.online,
            "max_players": status.players.max,
            "version": status.version.name,
            "motd": status.description if hasattr(status, 'description') else status.motd,
            "player_names": player_sample,
        }
    except Exception as e:
        return {"online": False, "error": str(e)}

# ----------- Update statut -----------

@tasks.loop(seconds=30)
async def update_status():
    def strip_minecraft_colors(text):
        # Remove Minecraft color codes like §a, §b, etc.
        return re.sub(r'§.', '', text)

    for guild_id, conf in config.items():
        guild = bot.get_guild(int(guild_id))
        if not guild:
            continue
        channel_id = conf.get("channel_id")
        if not channel_id:
            continue
        channel = guild.get_channel(channel_id)
        if not channel:
            continue

        ip = conf.get("ip")
        port = conf.get("port", 25565)
        status_info = await ping_minecraft(ip, port)

        embed = discord.Embed(
            title="📊 Statut serveur Minecraft",
            color=discord.Color.green() if status_info["online"] else discord.Color.red()
        )
        ip_display = ip if port == 25565 else f"{ip}:{port}"
        ip_link = f"[{ip_display}](https://{ip})"
        embed.add_field(name="Adresse", value=ip_link)
        embed.add_field(name="Statut", value="🟢 En ligne" if status_info["online"] else "🔴 Hors ligne")
        
        if status_info["online"]:
            embed.add_field(name="Joueurs connectés", value=f"{status_info['players']} / {status_info['max_players']}")
            # Hide version as requested
            # embed.add_field(name="Version", value=status_info['version'])
            # Add player list if available
            player_names = status_info.get('player_names', [])
            if player_names:
                embed.add_field(name="Joueurs", value=', '.join(player_names), inline=False)
            motd_clean = strip_minecraft_colors(status_info['motd'])
            embed.add_field(name="MOTD", value=motd_clean)

        embed.set_footer(text="Mis à jour toutes les 30 secondes")

        msg = status_messages.get(guild_id)
        if not msg:
            try:
                msg = await channel.send(embed=embed)
                status_messages[guild_id] = msg
            except Exception as e:
                print(f"Erreur lors de l'envoi du message : {e}")
        else:
            try:
                await msg.edit(embed=embed)
            except Exception as e:
                print(f"Erreur lors de la mise à jour du message : {e}")
                try:
                    msg = await channel.send(embed=embed)
                    status_messages[guild_id] = msg
                except Exception as e:
                    print(f"Erreur lors de l'envoi du message : {e}")


import random
from discord.utils import get
from datetime import datetime, timedelta

# --- Système de Warns ---

def get_warns(guild_id, user_id):
    guild_warns = config.get(str(guild_id), {}).get("warns", {})
    return guild_warns.get(str(user_id), [])

def save_warns(guild_id, user_id, warns):
    if str(guild_id) not in config:
        config[str(guild_id)] = {}
    if "warns" not in config[str(guild_id)]:
        config[str(guild_id)]["warns"] = {}
    config[str(guild_id)]["warns"][str(user_id)] = warns
    save_config(config)

@tree.command(name="warn", description="Avertir un membre")
@app_commands.describe(member="Membre à avertir", reason="Raison de l'avertissement")
@app_commands.checks.has_permissions(administrator=True)
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    warns = get_warns(interaction.guild.id, member.id)
    warn_entry = {"reason": reason, "date": datetime.utcnow().isoformat()}
    warns.append(warn_entry)
    save_warns(interaction.guild.id, member.id, warns)

    embed = discord.Embed(title="⚠️ Avertissement", color=discord.Color.orange())
    embed.add_field(name="Membre", value=member.mention, inline=True)
    embed.add_field(name="Raison", value=reason, inline=True)
    embed.add_field(name="Nombre total d'avertissements", value=str(len(warns)), inline=False)
    embed.set_footer(text=f"Averti par {interaction.user}", icon_url=interaction.user.display_avatar.url)
    await interaction.response.send_message(embed=embed)

    # Alerte si beaucoup de warns (ex: 3 ou plus)
    if len(warns) >= 3:
        alert_channel = interaction.channel
        alert_embed = discord.Embed(
            title="⚠️ Alerte Warns",
            description=f"{member.mention} commence à accumuler beaucoup d'avertissements ({len(warns)}). Il faudrait envisager une sanction.",
            color=discord.Color.red()
        )
        await alert_channel.send(embed=alert_embed)

@tree.command(name="warns", description="Afficher les avertissements d'un membre")
@app_commands.describe(member="Membre à consulter")
@app_commands.checks.has_permissions(administrator=True)
async def warns(interaction: discord.Interaction, member: discord.Member):
    warns = get_warns(interaction.guild.id, member.id)
    if not warns:
        await interaction.response.send_message(f"{member.mention} n'a aucun avertissement.", ephemeral=True)
        return

    embed = discord.Embed(title=f"Avertissements de {member}", color=discord.Color.orange())
    for i, warn in enumerate(warns, start=1):
        date_str = warn.get("date", "Date inconnue")
        reason = warn.get("reason", "Raison non spécifiée")
        embed.add_field(name=f"Avertissement #{i}", value=f"Raison: {reason}\nDate: {date_str}", inline=False)
    await interaction.response.send_message(embed=embed)

@tree.command(name="clearwarns", description="Supprimer les avertissements d'un membre")
@app_commands.describe(member="Membre à nettoyer")
@app_commands.checks.has_permissions(administrator=True)
async def clearwarns(interaction: discord.Interaction, member: discord.Member):
    save_warns(interaction.guild.id, member.id, [])
    await interaction.response.send_message(f"Les avertissements de {member.mention} ont été supprimés.", ephemeral=True)

# --- Système de Giveaways ---

active_giveaways = {}

@tree.command(name="giveaway", description="Démarrer un giveaway")
@app_commands.describe(duration="Durée en minutes", prize="Prix du giveaway")
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, duration: int, prize: str):
    if duration < 1:
        await interaction.response.send_message("La durée doit être d'au moins 1 minute.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎉 Giveaway !",
        description=f"Prix : **{prize}**\nDurée : {duration} minute(s)\nRéagissez avec 🎉 pour participer !",
        color=discord.Color.purple(),
        timestamp=datetime.utcnow()
    )
    embed.set_footer(text=f"Lancé par {interaction.user}", icon_url=interaction.user.display_avatar.url)

    message = await interaction.channel.send(embed=embed)
    await message.add_reaction("🎉")

    active_giveaways[message.id] = {
        "channel_id": interaction.channel.id,
        "prize": prize,
        "end_time": datetime.utcnow() + timedelta(minutes=duration),
        "message": message,
        "guild_id": interaction.guild.id
    }

    await interaction.response.send_message(f"Giveaway lancé pour {duration} minute(s) avec le prix : {prize}", ephemeral=True)

async def check_giveaways():
    to_remove = []
    for message_id, giveaway in active_giveaways.items():
        if datetime.utcnow() >= giveaway["end_time"]:
            channel = bot.get_channel(giveaway["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(message_id)
                    users = set()
                    for reaction in message.reactions:
                        if str(reaction.emoji) == "🎉":
                            async for user in reaction.users():
                                if not user.bot:
                                    users.add(user)
                    if users:
                        winner = random.choice(list(users))
                        embed = discord.Embed(
                            title="🎉 Giveaway terminé !",
                            description=f"Félicitations {winner.mention} ! Vous avez gagné : **{giveaway['prize']}**",
                            color=discord.Color.gold(),
                            timestamp=datetime.utcnow()
                        )
                        await channel.send(embed=embed)
                    else:
                        await channel.send("Personne n'a participé au giveaway.")
                    to_remove.append(message_id)
                except Exception as e:
                    print(f"Erreur lors de la fin du giveaway: {e}")
    for message_id in to_remove:
        active_giveaways.pop(message_id, None)

@tasks.loop(seconds=30)
async def giveaway_loop():
    await check_giveaways()

from discord.ui import View, Button
from discord import Interaction, Embed, PermissionOverwrite

# --- Système de tickets ---

class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Ouvrir un ticket", style=discord.ButtonStyle.green, custom_id="open_ticket"))

class CloseTicketView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="Fermer le ticket", style=discord.ButtonStyle.red, custom_id="close_ticket"))

@tree.command(name="setticketpanel", description="Configurer le salon du panel d'ouverture de tickets")
@app_commands.describe(channel="Salon où poster le panel de tickets")
@app_commands.checks.has_permissions(administrator=True)
async def setticketpanel(interaction: discord.Interaction, channel: discord.TextChannel):
    guild_id = str(interaction.guild.id)
    if guild_id not in config:
        config[guild_id] = {}
    config[guild_id]["ticket_panel_channel_id"] = channel.id
    save_config(config)
    await interaction.response.send_message(f"Salon du panel de tickets configuré : {channel.mention}", ephemeral=True)

    # Poster le panel dans le salon configuré
    embed = Embed(
        title="🎫 Système de tickets",
        description="Cliquez sur le bouton ci-dessous pour ouvrir un ticket.",
        color=discord.Color.blue()
    )
    view = TicketView()
    try:
        await channel.send(embed=embed, view=view)
    except Exception as e:
        await interaction.channel.send(f"Erreur lors de l'envoi du panel de tickets : {e}")

@bot.event
async def on_interaction(interaction: Interaction):
    if not interaction.type == discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id")
    guild_id = str(interaction.guild.id)
    guild_config = config.get(guild_id, {})

    if custom_id == "open_ticket":
        # Vérifier si le panel est configuré
        panel_channel_id = guild_config.get("ticket_panel_channel_id")
        if not panel_channel_id:
            await interaction.response.send_message("Le système de tickets n'est pas configuré. Contactez un administrateur.", ephemeral=True)
            return

        # Vérifier si l'utilisateur a déjà un ticket ouvert
        existing_ticket = None
        for channel in interaction.guild.channels:
            if channel.name == f"ticket-{interaction.user.id}":
                existing_ticket = channel
                break
        if existing_ticket:
            await interaction.response.send_message(f"Vous avez déjà un ticket ouvert : {existing_ticket.mention}", ephemeral=True)
            return

        # Créer un salon privé pour le ticket
        overwrites = {
            interaction.guild.default_role: PermissionOverwrite(read_messages=False),
            interaction.user: PermissionOverwrite(read_messages=True, send_messages=True),
            interaction.guild.me: PermissionOverwrite(read_messages=True, send_messages=True)
        }
        category = None
        if panel_channel_id:
            panel_channel = interaction.guild.get_channel(panel_channel_id)
            if panel_channel and panel_channel.category:
                category = panel_channel.category

        channel_name = f"ticket-{interaction.user.id}"
        try:
            ticket_channel = await interaction.guild.create_text_channel(channel_name, overwrites=overwrites, category=category, reason="Ouverture d'un ticket")
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors de la création du ticket : {e}", ephemeral=True)
            return

        # Envoyer un message dans le salon ticket avec un bouton pour fermer
        embed = Embed(
            title="🎫 Ticket ouvert",
            description=f"{interaction.user.mention}, merci de décrire votre demande. Un membre du staff vous répondra bientôt.",
            color=discord.Color.green()
        )
        view = CloseTicketView()
        await ticket_channel.send(embed=embed, view=view)

        await interaction.response.send_message(f"Votre ticket a été créé : {ticket_channel.mention}", ephemeral=True)

    elif custom_id == "close_ticket":
        # Vérifier que le salon est un ticket
        if not interaction.channel.name.startswith("ticket-"):
            await interaction.response.send_message("Ce bouton ne peut être utilisé que dans un salon de ticket.", ephemeral=True)
            return

        # Vérifier que l'utilisateur est le créateur du ticket ou un administrateur
        ticket_owner_id = int(interaction.channel.name.split("-")[1])
        if interaction.user.id != ticket_owner_id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Vous n'avez pas la permission de fermer ce ticket.", ephemeral=True)
            return

        try:
            await interaction.channel.delete(reason=f"Ticket fermé par {interaction.user}")
        except Exception as e:
            await interaction.response.send_message(f"Erreur lors de la fermeture du ticket : {e}", ephemeral=True)

bot.run("token")
