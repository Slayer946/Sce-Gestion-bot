import discord
from discord.ext import commands, tasks
import aiohttp
import json
import random
import os
import sys
import asyncio
import datetime
import sqlite3
import requests
from discord.ui import Button, View
from database import update_report_count, get_report_count, connect_to_database
import logging
from pytube import YouTube
from moviepy.editor import VideoFileClip, concatenate_videoclips
from googletrans import Translator



bot = commands.Bot(command_prefix='.', intents=discord.Intents.all())
token = ''


def load_config(filename):
    try:
        with open(filename, 'r') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        print(f"Le fichier {filename} n'a pas été trouvé.")
        return None
    except Exception as e:
        print(f"Erreur lors du chargement de la configuration depuis {filename}: {e}")
        return None

# Exemple d'utilisation
config = load_config('config_bot.json')
if config:
    print(f"Configuration chargée avec succès : {config}")
else:
    print("Impossible de charger la configuration.")

global anti_invite_enabled
anti_invite_enabled = True



def create_reports_table():
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS reports (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        member_id INTEGER,
                        report_count INTEGER
                    )''')
    connection.commit()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='reports'")
    result = cursor.fetchone()
    if result:
        print("La table reports a été créée avec succès.")
    else:
        print("Erreur : La table reports n'a pas été créée.")

    connection.close()

def update_report_count(member_id, new_count):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("UPDATE reports SET report_count = ? WHERE member_id = ?", (new_count, member_id))
    connection.commit()
    connection.close()

def get_report_count(member_id):
    connection = sqlite3.connect('database.db')
    cursor = connection.cursor()
    cursor.execute("SELECT report_count FROM reports WHERE member_id = ?", (member_id,))
    result = cursor.fetchone()
    connection.close()
    if result:
        return result[0]
    else:
        return 0

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    await member.kick(reason=reason)
    await ctx.send(f'{member} a été expulsé pour la raison : {reason}')

@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason=None):
    await member.ban(reason=reason)
    await ctx.send(f'{member} a été banni pour la raison : {reason}')

@bot.command(name='unban')
@commands.guild_only()
async def _unban(ctx, id: int):
    user = await bot.fetch_user(id)
    try:
        await ctx.guild.unban(user)
        await ctx.send(f"L'utilisateur {user.name} a été débanni avec succès.")
    except discord.NotFound:
        await ctx.send("Cet utilisateur n'était pas banni.")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def mute(ctx, member: discord.Member, duration: int):
    mute_role = discord.utils.get(ctx.guild.roles, name="Muted")
    if not mute_role:
        mute_role = await ctx.guild.create_role(name="Muted")

        for channel in ctx.guild.channels:
            await channel.set_permissions(mute_role, speak=False, send_messages=False, read_message_history=True, read_messages=True)

    await member.add_roles(mute_role)
    await ctx.send(f'{member} a été mute pour {duration} secondes')

    await asyncio.sleep(duration)
    await member.remove_roles(mute_role)
    await ctx.send(f'{member} n\'est plus mute')

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount=5):
    await ctx.channel.purge(limit=amount)
    await ctx.send(f'{amount} messages ont été supprimés', delete_after=5)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason=None):
    if reason is None:
        await ctx.send("Veuillez fournir une raison pour l'avertissement.")
        return

    moderator = ctx.author
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    warn_info = (
        f"**Avertissement**\n"
        f"**Membre averti :** {member.mention}\n"
        f"**Raison :** {reason}\n"
        f"**Modérateur :** {moderator.mention} ({moderator.id})\n"
        f"**Date et heure :** {current_time}"
    )

    try:
        await member.send(warn_info)
    except discord.Forbidden:
        await ctx.send(f"Impossible d'envoyer un message privé à {member.mention} concernant l'avertissement.")

    await ctx.send(f'{member} a été averti pour la raison : {reason}')


@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    await ctx.channel.edit(slowmode_delay=seconds)
    await ctx.send(f'Le mode ralenti est maintenant activé avec un délai de {seconds} secondes')

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx, *, reason=None):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send(f'Ce canal a été verrouillé pour la raison : {reason}')

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx, *, reason=None):
    await ctx.channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send(f'Ce canal a été déverrouillé pour la raison : {reason}')


@bot.command()
async def set_admin_reports_channel(ctx, channel: discord.TextChannel):
    if ctx.author == ctx.guild.owner:
        with open('config.json', 'r') as f:
            config = json.load(f)
        
        config['admin_reports_channel_id'] = channel.id
        
        with open('config.json', 'w') as f:
            json.dump(config, f)
        
        await ctx.send(f"Le salon admin-reports a été défini sur {channel.mention}.")
    else:
        await ctx.send("Vous devez être le propriétaire du serveur pour définir le salon admin-reports.")


@bot.command()
async def report(ctx, member: discord.Member, *, reason=None):
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    admin_reports_channel_id = config.get('admin_reports_channel_id')
    admin_channel = discord.utils.get(ctx.guild.text_channels, id=admin_reports_channel_id)
    
    if not admin_channel:
        await ctx.send("Le salon admin-reports n'est pas défini. Veuillez le définir avant de pouvoir utiliser cette commande.")
        return
    
    report_author = ctx.author
    accused = member
    report_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report_id = ctx.author.id
    report_count = get_report_count(member.id)
    
    await admin_channel.send(f'Auteur du report: {report_author}\nAccusé: {accused}\nDate et heure: {report_date}\nID de l\'accusé: {accused.id}\nID de l\'auteur: {report_id}\nNombre de reports précédents: {report_count}\nRaison: {reason}')
    update_report_count(member.id, report_count + 1)
    
    await ctx.send(f'{member} a été signalé pour : {reason}')

@bot.command()
@commands.has_permissions(manage_channels=True)
async def announce(ctx, channel: discord.TextChannel, *, message):
    await channel.send(message)
    await ctx.send(f'Annonce envoyée dans {channel.mention}')

@bot.command()
@commands.has_permissions(manage_nicknames=True)
async def nickname(ctx, member: discord.Member, *, nickname):
    await member.edit(nick=nickname)
    await ctx.send(f'Le surnom de {member.mention} a été changé en {nickname}')

@bot.command()
@commands.has_permissions(manage_messages=True)
async def purgeuser(ctx, member: discord.Member, limit: int):
    def is_user(m):
        return m.author == member

    deleted = await ctx.channel.purge(limit=limit, check=is_user)
    await ctx.send(f'{len(deleted)} messages de {member.mention} ont été supprimés', delete_after=5)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def checkwarns(ctx, member: discord.Member):
    # Supposez que get_warns_from_database est une fonction qui retourne une liste d'avertissements pour le membre donné
    warns = get_warns_from_database(member)

    if warns:
        await ctx.send(f"{member.mention} a {len(warns)} avertissement(s).")
    else:
        await ctx.send(f"{member.mention} n'a aucun avertissement.")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def lockdown(ctx):
    for channel in ctx.guild.channels:
        await channel.set_permissions(ctx.guild.default_role, send_messages=False)
    await ctx.send('Le serveur est en lockdown. Tous les canaux ont été verrouillés.')

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlockdown(ctx):
    for channel in ctx.guild.channels:
        await channel.set_permissions(ctx.guild.default_role, send_messages=True)
    await ctx.send('Le lockdown est terminé. Tous les canaux ont été déverrouillés.')

@bot.command()
async def listroles(ctx, member: discord.Member):
    roles = [role.name for role in member.roles if role.name != "@everyone"]
    await ctx.send(f'{member.mention} a les rôles : {", ".join(roles)}')

@bot.command()
@commands.has_permissions(deafen_members=True)
async def deafen(ctx, member: discord.Member, *, reason=None):
    await member.edit(deafen=True, reason=reason)
    await ctx.send(f'{member} a été rendu sourd pour la raison : {reason}')

@bot.command()
@commands.has_permissions(deafen_members=True)
async def undeafen(ctx, member: discord.Member, *, reason=None):
    await member.edit(deafen=False, reason=reason)
    await ctx.send(f'{member} n\'est plus sourd pour la raison : {reason}')

@bot.command()
async def userinfo(ctx, member: discord.Member):
    embed = discord.Embed(title=f"Information sur {member}", color=0x00ff00)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Nom d'utilisateur", value=member.name, inline=True)
    embed.add_field(name="Discriminateur", value=member.discriminator, inline=True)
    embed.add_field(name="Compte créé le", value=member.created_at, inline=True)
    embed.add_field(name="Rejoint le", value=member.joined_at, inline=True)
    embed.add_field(name="Rôles", value=", ".join([role.name for role in member.roles if role.name != "@everyone"]), inline=True)
    await ctx.send(embed=embed)

@bot.command()
async def serverinfo(ctx):
    guild = ctx.guild
    embed = discord.Embed(title="Informations sur le serveur", color=0x00ff00)
    embed.add_field(name="Nom du serveur", value=guild.name, inline=True)
    embed.add_field(name="ID du serveur", value=guild.id, inline=True)
    embed.add_field(name="Nombre de membres", value=len(guild.members), inline=True)
    embed.add_field(name="Nombre de rôles", value=len(guild.roles), inline=True)
    embed.add_field(name="Nombre de salons textuels", value=len(guild.text_channels), inline=True)
    embed.add_field(name="Nombre de salons vocaux", value=len(guild.voice_channels), inline=True)
    
    if guild.icon:
        icon_url = guild.icon_url_as(format='png')
        embed.set_thumbnail(url=icon_url)
    else:
        # Mettez ici l'URL de votre image par défaut ou laissez vide pour ne pas inclure d'icône
        pass
    
    await ctx.send(embed=embed)



@bot.command()
async def roleinfo(ctx, role: discord.Role):
    embed = discord.Embed(title=f"Information sur le rôle {role.name}", color=role.color)
    embed.add_field(name="ID", value=role.id, inline=True)
    embed.add_field(name="Nom", value=role.name, inline=True)
    embed.add_field(name="Couleur", value=str(role.color), inline=True)
    embed.add_field(name="Mentionnable", value=role.mentionable, inline=True)
    embed.add_field(name="Créé le", value=role.created_at, inline=True)
    await ctx.send(embed=embed)


def save_prefix(prefix):
    with open("prefix.txt", "w") as file:
        file.write(prefix)
@bot.command()
@commands.has_permissions(administrator=True)
async def setprefix(ctx, prefix: str):
    bot.command_prefix = prefix
    save_prefix(prefix)
    await ctx.send(f"Préfixe changé en: {prefix}")

try:
    with open("prefix.txt", "r") as file:
        saved_prefix = file.read()
        bot.command_prefix = saved_prefix
except FileNotFoundError:
    pass

@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnlist(ctx, member: discord.Member):
    warnings = get_warns_from_database(member)
    if warnings:
        warnings_str = '\n'.join(warnings)
    else:
        warnings_str = "Aucun avertissement trouvé."
    await ctx.send(f'{member.mention} a les avertissements suivants :\n{warnings_str}')

def get_warns_from_database(member):
    warnings = {
        "user1": ["Avertissement 1", "Avertissement 2"],
        "user2": ["Avertissement 3", "Avertissement 4"],
    }
  
    if str(member.id) in warnings:
        return warnings[str(member.id)]
    else:
        return []

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clearwarns(ctx, member: discord.Member):
    # Fonction pour effacer les avertissements de la base de données
    await ctx.send(f"Tous les avertissements de {member.mention} ont été effacés.")
    # Exemple: clear_warns_in_database(member)


@bot.command()
async def poll(ctx, question, *options: str):
    if len(options) < 2:
        await ctx.send('Vous devez fournir au moins deux options.')
        return
    if len(options) > 10:
        await ctx.send('Vous ne pouvez pas fournir plus de dix options.')
        return

    embed = discord.Embed(title="Sondage", description=question, color=0x00ff00)
    reactions = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟']
    for i, option in enumerate(options):
        embed.add_field(name=f'Option {i+1}', value=f'{reactions[i]} {option}', inline=False)
    
    message = await ctx.send(embed=embed)
    for i in range(len(options)):
        await message.add_reaction(reactions[i])    

current_poll = None

@bot.command()
async def stoppoll(ctx):
    global current_poll
    if current_poll:
        await current_poll.delete()
        current_poll = None
        await ctx.send("Le sondage a été arrêté. Vous pouvez désormais en lancer un nouveau.")
    else:
        await ctx.send("Il n'y a pas de sondage en cours.")

@bot.command()
async def snipe(ctx):
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('''SELECT content, author_id, deleted_at
                      FROM snipes
                      WHERE channel_id = ?
                      AND deleted_at >= datetime('now', '-1 day')  -- Limite aux messages supprimés au cours des dernières 24 heures
                      ORDER BY deleted_at DESC  -- Tri par ordre décroissant de suppression
                      LIMIT 1''', (ctx.channel.id,))
    result = cursor.fetchone()
    connection.close()

    if result:
        content, author_id, deleted_at_str = result
        deleted_at = datetime.datetime.fromisoformat(deleted_at_str)  
        author = ctx.guild.get_member(author_id)
        embed = discord.Embed(description=content, color=discord.Color.red(), timestamp=deleted_at)
        embed.set_author(name=f"{author.name}#{author.discriminator}", icon_url=author.avatar.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("Aucun message trouvé.")


@bot.command()
async def createchannel(ctx, name):
    await ctx.guild.create_text_channel(name)
    await ctx.send(f"Le salon {name} a été créé.")

@bot.command()
async def deletechannel(ctx, channel: discord.TextChannel):
    await channel.delete()
    await ctx.send(f"Le salon {channel.name} a été supprimé.")

@bot.command()
async def createvoice(ctx, name):
    await ctx.guild.create_voice_channel(name)
    await ctx.send(f"Le salon vocal {name} a été créé.")

@bot.command()
async def deletevoice(ctx, channel: discord.VoiceChannel):
    await channel.delete()
    await ctx.send(f"Le salon vocal {channel.name} a été supprimé.")

@bot.command()
@commands.has_permissions(administrator=True)
async def add_role(ctx, member: discord.Member, role: discord.Role):
    await member.add_roles(role)
    await ctx.send(f"Rôle {role.name} ajouté à {member.display_name}")

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_role(ctx, member: discord.Member, role: discord.Role):
    await member.remove_roles(role)
    await ctx.send(f"Rôle {role.name} retiré à {member.display_name}")


@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000) 
    await ctx.send(f'Ping du bot : {latency} ms')


@bot.command()
async def create_temp_voice(ctx, name="Temporary Voice", *, bitrate=64000):
    guild = ctx.guild
    author = ctx.author
    
    
    voice_channel = await guild.create_voice_channel(name, bitrate=bitrate)
    
    
    await author.move_to(voice_channel)

    await ctx.send(f'Salon vocal temporaire "{name}" créé!')


@bot.command()
async def cool(ctx):
    embed = discord.Embed(title="CoolRate", description=f"tu es {random.randrange(101)}% Cool 😎 {ctx.author.mention}", color = discord.Color.random())
    await ctx.send(embed = embed)

@bot.command()
async def gay(ctx):
    embed = discord.Embed(title="GayRate", description=f"tu es {random.randrange(101)}% Gay 🌈 {ctx.author.mention}", color = discord.Color.random())
    await ctx.send(embed = embed)

@bot.command()
async def raciste(ctx):
    embed = discord.Embed(title="racisteRate", description=f"tu es {random.randrange(101)}% Raciste {ctx.author.mention}", color = discord.Color.random())
    await ctx.send(embed = embed)


@bot.command()
async def pprate(ctx):
    pp_list = ['8D', '8=D', '8==D','8===D','8====D','8=====D','8======D','8=======D','8========D','8=========D','8==========D']
    embed = discord.Embed(title="ppRate", description=f'tas pp {random.choice(pp_list)}')
    await ctx.send(embed=embed)

@bot.command()
async def enable_anti_invite(ctx):
    global anti_invite_enabled
    anti_invite_enabled = True
    await ctx.send("L'anti-invitation est activé.")

@bot.command()
@commands.has_permissions(administrator=True)
async def reactrole(ctx, message_id: int, emoji: str, role: discord.Role):
    message = await ctx.fetch_message(message_id)
    await message.add_reaction(emoji)
    
    @bot.event
    async def on_raw_reaction_add(payload):
        if payload.message_id == message_id and str(payload.emoji) == emoji:
            guild = bot.get_guild(payload.guild_id)
            if guild is None:
                return
            reaction_role = guild.get_role(role.id)  # Récupérer le rôle à chaque fois dans l'événement
            if reaction_role is None:
                return
            member = guild.get_member(payload.user_id)
            if member is None:
                return
            await member.add_roles(reaction_role)

    @bot.event
    async def on_raw_reaction_remove(payload):
        if payload.message_id == message_id and str(payload.emoji) == emoji:
            guild = bot.get_guild(payload.guild_id)
            if guild is None:
                return
            reaction_role = guild.get_role(role.id)  # Récupérer le rôle à chaque fois dans l'événement
            if reaction_role is None:
                return
            member = guild.get_member(payload.user_id)
            if member is None:
                return
            await member.remove_roles(reaction_role)




@bot.command()
@commands.has_permissions(manage_channels=True)
async def send(ctx, channel: discord.TextChannel, *, message: str):
    await channel.send(message)
    await ctx.send(f"Message envoyé dans {channel.mention}")

@bot.command()
@commands.has_permissions(create_instant_invite=True)
async def createinvite(ctx, channel: discord.TextChannel):
    invite = await channel.create_invite(max_age=0, max_uses=0)
    await ctx.send(f"Invitation créée: {invite.url}")


def has_send_message_perms():
    async def predicate(ctx):
        permissions = ctx.channel.permissions_for(ctx.author)
        if permissions.send_messages:
            return True
        else:
            await ctx.send("Vous n'avez pas la permission d'envoyer des messages dans ce canal.")
            return False
    return commands.check(predicate)

@bot.command()
@has_send_message_perms()
async def dm(ctx, user: discord.User, *, message: str):
    try:
        await user.send(message)
        timestamp = datetime.datetime.utcnow()
        author_name = ctx.author.name
        author_id = ctx.author.id
        author_avatar = ctx.author.avatar.url if ctx.author.avatar else None
        guild_name = ctx.guild.name if ctx.guild else "N/A"
        channel_name = ctx.channel.name
        author_avatar = ctx.author.avatar.url if ctx.author.avatar else discord.Embed.Empty
        
        embed = discord.Embed(title="Nouveau message privé",
                              description=f"**Auteur du DM:** {author_name}\n"
                                          f"**ID de l'auteur:** {author_id}\n"
                                          f"**Pseudo de l'autre:** {user.name}\n"
                                          f"**Date/Heure:** {timestamp}\n"
                                          f"**Serveur:** {guild_name}\n"
                                          f"**Canal:** {channel_name}\n"
                                          f"**Contenu:** {message}",
                              color=discord.Color.green())
        embed.set_author(name=author_name, icon_url=author_avatar)
        
        await user.send(embed=embed)
        await ctx.send(f"Message envoyé à {user.name}")
    except discord.Forbidden:
        await ctx.send("Je ne peux pas envoyer de message à cet utilisateur.")


@bot.command()
async def info_bot(ctx, module=None):
    member = ctx.guild.me
    guild_count = len(bot.guilds)
    if module is None or module == "info": 
        embed = discord.Embed(title="Informations sur le Bot :", timestamp=ctx.message.created_at, color=discord.Color.random())
        embed.set_footer(text=f"Demandé par {ctx.author} !")
        embed.set_thumbnail(url="https://cdn.discordapp.com/avatars/1243970937339121694/eae6044607c6de6b7c4a57116ecce4a3.png?size=1024")
        embed.add_field(name="Bot Créé le :", value=member.created_at.strftime("%a, %#d %B %Y, %I:%M %p UTC"), inline=False)
        embed.add_field(name="Rejoint ce serveur le :", value=member.joined_at.strftime("%a, %#d %B %Y, %I:%M %p UTC"), inline=False)
        embed.add_field(name="ID :", value=member.id, inline=False)
        embed.add_field(name="Nom affiché sur le serveur :", value=member.display_name, inline=False)
        embed.add_field(name="Lien d'invitation :", value="https://discord.com/oauth2/authorize?client_id=1243970937339121694&permissions=8&integration_type=0&scope=bot+applications.commands", inline=False)
        embed.add_field(name="Nombre de serveurs :", value=guild_count, inline=False)
        await ctx.reply(embed=embed)


@bot.command()
async def profile_pic(ctx, member: discord.Member = None):
    member = member or ctx.author
    if member.avatar:
        avatar_url = member.avatar.url
        await ctx.send(f"Voici le lien vers la photo de profil de {member.display_name}: {avatar_url}")
    else:
        await ctx.send("Ce membre n'a pas de photo de profil définie.")

@bot.command(name='dog')
async def dog(ctx):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://dog.ceo/api/breeds/image/random') as response:
            if response.status == 200:
                data = await response.json()
                await ctx.send(data['message'])
            else:
                await ctx.send('Impossible de récupérer une image de chien pour le moment.')

@bot.command(name='cat')
async def cat(ctx):
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.thecatapi.com/v1/images/search') as response:
            if response.status == 200:
                data = await response.json()
                await ctx.send(data[0]['url'])
            else:
                await ctx.send('Impossible de récupérer une image de chat pour le moment.')



@bot.command()
async def meme(ctx):
    try:
        response = requests.get('https://api.imgflip.com/get_memes')
        
        if response.status_code == 200:
            data = response.json()
            
            if 'success' in data and data['success'] == True:
                memes = data['data']['memes']
                meme = memes[0] 
                
                await ctx.send(meme['url'])
            else:
                await ctx.send("Impossible de récupérer un mème pour le moment.")
        else:
            await ctx.send("Impossible de récupérer un mème pour le moment.")
    except Exception as e:
        await ctx.send(f"Une erreur s'est produite : {e}")



blacklisted_users = set()
bypass_users = {}

def is_bot_owner(ctx):
    return ctx.author.id == 1128008782727893082

@bot.command()
@commands.check(is_bot_owner)
async def add_to_blacklist(ctx, user_id: int):
    blacklisted_users.add(user_id)
    user = await bot.fetch_user(user_id)
    if user:
        for guild in bot.guilds:
            member = guild.get_member(user.id)
            if member:
                await member.ban(reason="Membre ajouté à la liste noire du bot.")
        await ctx.send(f"{user.name} a été ajouté à la liste noire et banni de tous les serveurs où je suis.")
    else:
        await ctx.send("Impossible de trouver l'utilisateur avec cet ID.")


@bot.command()
@commands.check(is_bot_owner)
async def remove_from_blacklist(ctx, user_id: int):
    if user_id in blacklisted_users:
        blacklisted_users.remove(user_id)
        user = await bot.fetch_user(user_id)
        if user:
            for guild in bot.guilds:
                try:
                    await guild.unban(user, reason="Membre retiré de la liste noire du bot.")
                    await ctx.send(f"{user.name} a été retiré de la liste noire sur {guild.name}.")
                except discord.Forbidden:
                    await ctx.send(f"Je n'ai pas les permissions nécessaires pour retirer {user.name} de la liste noire sur {guild.name}.")
                except discord.HTTPException as e:
                    await ctx.send(f"Une erreur s'est produite lors de la tentative de retrait de {user.name} de la liste noire sur {guild.name}: {e}")
        else:
            await ctx.send("Impossible de trouver l'utilisateur avec cet ID.")
    else:
        await ctx.send("Cet utilisateur n'est pas dans la liste noire.")


@bot.command()
@commands.has_permissions(administrator=True)
async def bypass_blacklist(ctx, user_id: int):
    user = await bot.fetch_user(user_id)
    if user:
        if ctx.guild:  # Vérifie si la commande est exécutée dans un serveur
            if ctx.author.id not in bypass_users:
                bypass_users[ctx.author.id] = set()
            bypass_users[ctx.author.id].add(ctx.guild.id)
            await ctx.send(f"{user.name} peut maintenant contourner la liste noire sur ce serveur.")
        else:
            await ctx.send("Cette commande doit être exécutée dans un serveur.")
    else:
        await ctx.send("Impossible de trouver l'utilisateur avec cet ID.")

@bot.event
async def on_message(message):
    if message.author.id in blacklisted_users and message.guild and message.guild.id not in bypass_users.get(message.author.id, []):
        await message.delete()
        await message.author.send("Vous avez été ajouté à la liste noire du bot et ne pouvez pas envoyer de messages.")
    else:
        await bot.process_commands(message)


anti_ban_enabled = False
ban_counter = {}

@bot.command()
@commands.has_permissions(administrator=True)
async def toggle_anti_ban(ctx):
    global anti_ban_enabled
    anti_ban_enabled = not anti_ban_enabled
    await ctx.send(f"La fonctionnalité anti-ban est maintenant {'activée' if anti_ban_enabled else 'désactivée'}.")

@bot.event
async def on_member_ban(guild, user):
    global anti_ban_enabled, ban_counter
    if anti_ban_enabled:
        author_id = await get_ban_author_id(user, guild)
        
        if author_id == user.id:
            if user.id in ban_counter:
                ban_counter[user.id] += 1
            else:
                ban_counter[user.id] = 1
            
            if ban_counter[user.id] >= 5:
                await guild.kick(user, reason="Trop de bans effectués.")
                await guild.owner.send(f"L'utilisateur {user.name} a été kick car il a effectué trop de bans.")
                ban_counter[user.id] = 0

async def get_ban_author_id(user, guild):
    async for entry in guild.audit_logs(action=discord.AuditLogAction.ban, limit=None, after=datetime.datetime.now() - datetime.timedelta(seconds=120)):
        if entry.target == user:
            return entry.user.id
    return None


anti_kick_enabled = False
kick_count_threshold = 5
kick_time_threshold = 120

@bot.command()
@commands.has_permissions(administrator=True)
async def toggle_anti_kick(ctx):
    global anti_kick_enabled
    anti_kick_enabled = not anti_kick_enabled
    await ctx.send(f"Fonctionnalité anti-kick {'activée' if anti_kick_enabled else 'désactivée'}.")

@bot.event
async def on_member_remove(member):
    global anti_kick_enabled
    if anti_kick_enabled:
        guild = member.guild
        author = guild.get_member(guild.owner_id)
        kick_count = sum(1 for entry in guild.audit_logs(action=discord.AuditLogAction.kick, limit=None) if entry.target.id == member.id and entry.user.id == author.id and (discord.utils.utcnow() - entry.created_at).total_seconds() <= kick_time_threshold)
        if kick_count >= kick_count_threshold:
            await member.guild.owner.send(f"{member.name} a été kické {kick_count} fois par {author.name} en moins de 2 minutes.")
            await member.guild.invite(member, reason=f"Membre automatiquement réinvité après avoir été kické {kick_count} fois par l'auteur en moins de 2 minutes.")



class CommandView(View):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx

    @discord.ui.button(label="Modération", style=discord.ButtonStyle.primary, custom_id="mod_button")
    async def mod_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Commandes de Modération", color=0x00ff00)
        commands = [
            ".kick [@utilisateur] [raison]", ".ban [@utilisateur] [raison]", ".unban [nom_utilisateur]",
            ".mute [@utilisateur] [durée] [raison]", ".clear [nombre]", ".warn [@utilisateur] [raison]",
            ".slowmode [secondes]", ".lock [raison]", ".unlock [raison]", ".createvoice [name]",
            ".deletevoice [id voice]",".send", ".createinvite", ".announce [canal] [message]",
            ".nickname [@utilisateur] [nouveau_surnom]", ".purgeuser [@utilisateur] [nombre]",]
        for cmd in commands:
            embed.add_field(name=cmd, value="\u200b", inline=False)
        await interaction.response.edit_message(embed=embed)

    @discord.ui.button(label="Membres", style=discord.ButtonStyle.primary, custom_id="memb_button")
    async def memb_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Commandes pour Membres", color=0x00ff00)
        commands = [
            ".userinfo [@utilisateur]", ".serverinfo", ".roleinfo [nom_du_rôle]",
            ".poll [question] [option1] [option2] ...", ".report [@utilisateur] [raison]", "snipe", "ping",
            "create_temp_voice", "cool", "raciste", "gay", "pprate", "info_bot",
            "profile.pic [@member]", "cat/dog", "meme","8ball","**blague**"
        ]
        for cmd in commands:
            embed.add_field(name=cmd, value="\u200b", inline=False)
        await interaction.response.edit_message(embed=embed)

    @discord.ui.button(label="Gestion", style=discord.ButtonStyle.primary, custom_id="gest_button")
    async def gest_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="Commandes de Gestion", color=0x00ff00)
        commands = [
            ".report [@utilisateur] [raison]", ".ping", "set_admin_reports_channel [salon]",
            ".setprefix", ".enable_anti_invite", ".disable_anti_invite", ".createinvite", ".toggle_anti_ban",
            ".toggle_anti_kick", ".set_logs_ban"
        ]
        for cmd in commands:
            embed.add_field(name=cmd, value="\u200b", inline=False)
        await interaction.response.edit_message(embed=embed)

@bot.command()
async def aide(ctx):
    embed = discord.Embed(title="Commandes d'aide", description="Cliquez sur les boutons ci-dessous pour voir les commandes de différentes catégories.", color=0x00ff00)
    view = CommandView(ctx)
    await ctx.send(embed=embed, view=view)
    


@bot.command(name='8ball')
async def _8ball(ctx):
    """.8ball - Posez une question à la Magic 8-Ball."""
    icon_url = 'https://i.imgur.com/XhNqADi.png'
    responses = [
        'Il est certain.',
        'Il en est décidément ainsi.',
        'Sans aucun doute.',
        'Oui définitivement.',
        'Vous pouvez compter dessus.',
        'Comme je le vois oui.',
        'Le plus probable.',
        'Les perspectives sont bonnes.',
        'Oui.',
        'Les signes pointent vers Oui.',
        'Répondez à Hazy, réessayez.',
        'Demandez à nouveau plus tard.',
        'Mieux vaut ne pas te le dire maintenant.',
        'Je ne peux pas prédire maintenant.',
        'Concentre-toi et demande encore.',
        'Ne compte pas dessus.',
        'Ma réponse est non.',
        'Mes sources disent non.',
        'Les perspectives ne sont pas très bonnes.',
        'Très douteux.'
    ]
    fortune = random.choice(responses)
    embed = discord.Embed(colour=discord.Colour.purple())
    embed.set_author(name='Magic 8-Ball', icon_url=icon_url)
    embed.add_field(name=f'*{ctx.author.name}, votre réponse est...*', value=f'**{fortune}**')
    await ctx.send(embed=embed)






@bot.event
async def on_message_delete(message):
    connection = connect_to_database()
    cursor = connection.cursor()
    cursor.execute('''INSERT INTO snipes (message_id, content, author_id, channel_id, deleted_at)
                      VALUES (?, ?, ?, ?, ?)''', (message.id, message.content, message.author.id, message.channel.id, datetime.datetime.now(datetime.timezone.utc).isoformat()))
    connection.commit()
    connection.close()


@bot.event
async def on_ready():
    print('bot is ready')

bot.run(token)