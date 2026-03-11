import discord
from discord import app_commands, ChannelType, utils
from discord import ui
from discord.ui import View, Button, Select, Modal, TextInput
from discord.ext import commands, tasks
import aiohttp
import os
import asyncio
import random
import re
import json
import time
from datetime import datetime, timedelta
from discord.utils import utcnow
import math
from io import BytesIO
from typing import Optional
import secrets
import string
from collections import defaultdict
from dotenv import load_dotenv
load_dotenv()

intents = discord.Intents.all()


class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="+", intents=intents, help_command=None)

    async def setup_hook(self):
        self.tree.on_error = self.on_app_command_error
        self.add_view(Ticket())
        self.add_view(TicketControlView())
        await self.tree.sync()
        print(f"Systèmes synchronisés pour {self.user}")
    # --- Gestionnaire d'erreurs pour les commandes classiques (!) ---
    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        
        permissions_errors = (
            commands.MissingPermissions,
            commands.MissingRole,
            commands.MissingAnyRole
        )

        if isinstance(error, permissions_errors):
            embed = discord.Embed(
                description=f"{ctx.author.mention}, vous n'avez pas la permission d'utiliser cette commande",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
        else:
            print(f"Erreur non gérée (Prefix) : {error}")

    # --- Gestionnaire d'erreurs pour les Slash Commands (/) ---
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandNotFound):
            return

        permissions_errors = (
            app_commands.MissingPermissions,
            app_commands.MissingRole,
            app_commands.MissingAnyRole
        )

        if isinstance(error, permissions_errors):
            embed = discord.Embed(
                description=f"{interaction.user.mention}, vous n'avez pas la permission d'utiliser cette commande",
                color=discord.Color.red()
            )
            
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            print(f"Erreur Slash non gérée : {error}")

bot = MyBot()


async def check_hierarchy(ctx, member: discord.Member, action: str):
    # Owner bypass total
    if ctx.author.id == ctx.guild.owner_id:
        return True

    # Vérifie auteur vs membre
    if member.top_role >= ctx.author.top_role:
        await ctx.send(f"Tu ne peux pas {action} un membre avec un rôle supérieur ou égal au tien.")
        return False

    # Vérifie bot vs membre
    if member.top_role >= ctx.guild.me.top_role:
        await ctx.send(f"Je ne peux pas {action} ce membre.")
        return False

    return True


OWNER_IDS = [1447233337830936807, 1477344366769999913]


def is_team_owner():
    async def predicate(ctx):
        return ctx.author.id in OWNER_IDS
    return commands.check(predicate)

async def update_status():
    await bot.change_presence(
        status=discord.Status.online,
    )


@bot.event
async def on_ready():
    print('Le bot est prêt !')


@bot.command()
@is_team_owner()
async def statut(ctx, mode: str, *, texte: str = None):
    mode = mode.lower()
    
    status_map = {
        "online": discord.Status.online,
        "idle": discord.Status.idle,
        "dnd": discord.Status.dnd,
        "invisible": discord.Status.invisible,
        "live": discord.Status.online
    }

    new_status = status_map.get(mode, discord.Status.online)
    
    activity = None
    if texte:
        if mode == "live":
            activity = discord.Streaming(name=texte, url="https://www.twitch.tv/discord")
        else:
            activity = discord.Game(name=texte)


    await bot.change_presence(status=f"{new_status}", activity=activity)
    
    if texte:
        message_confirm = f"Statut **{mode}** défini avec : *{texte}*"
    else:
        message_confirm = f"Statut **{mode}** défini."
        
    await ctx.send(message_confirm)




@bot.command()
@commands.has_permissions(manage_nicknames=True)
async def ping(ctx):
    latency = round(bot.latency * 1000)
    await ctx.send(f"Latence: `{latency}ms`")



TICKET_CATEGORY_ID = 1481371306413920446
STAFF_ROLE_IDS = (1481334964732563618,1481337029273845805,1481356100111568937,1481337097561440421)
# --- CLASSE : CONTRÔLE INTERNE DU TICKET ---
class TicketControlView(discord.ui.LayoutView):
    def __init__(self):
        super().__init__(timeout=None)

    container1 = discord.ui.Container(
        discord.ui.TextDisplay(content="**Gestion du Ticket**"),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(content="Seule l'équipe de modération peut fermer ce ticket via le bouton ci-dessous."),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.ActionRow(
            discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Fermer",
                custom_id="btn_close_ticket",
            ),
        ),
        accent_colour=discord.Colour(1),
    )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "btn_close_ticket":
            # Vérification : Est-ce que l'utilisateur a l'un des rôles Staff ?
            user_role_ids = [role.id for role in interaction.user.roles]
            is_staff = any(role_id in STAFF_ROLE_IDS for role_id in user_role_ids)

            if not is_staff:
                await interaction.response.send_message("❌ Seul le staff peut fermer ce ticket.", ephemeral=True)
                return False

            await interaction.response.send_message("🔒 **Fermeture du ticket dans 5 secondes...**")
            await asyncio.sleep(5)
            await interaction.channel.delete()
            return True
        return await super().interaction_check(interaction)

# --- CLASSE : MENU DE CRÉATION (PRINCIPAL) ---
class Ticket(discord.ui.LayoutView):     
    def __init__(self):
        super().__init__(timeout=None)

    container1 = discord.ui.Container(
        discord.ui.TextDisplay(content="# Créer un ticket"),
        discord.ui.TextDisplay(content="Utilise le menu ci-dessous pour créer un ticket"),
        discord.ui.ActionRow(
            discord.ui.Select(
                custom_id="ticket_selector_main",
                placeholder="Fait un choix...",
                options=[
                    discord.SelectOption(label="Contacter le Staff", value="staff", description="Contacter le Staff du serveur", emoji="<:3446blurplecertifiedmoderator:1481370549476262119>"),
                    discord.SelectOption(label="Signaler un Membre", value="report", description="Signaler un Membre du Serveur", emoji="<:8263blurplemembers:1481370661673898107>"),
                    discord.SelectOption(label="Signalement Bot", value="bot", description="Signalent sur ServerMaster", emoji="<:1598blurplesupport:1481370647610528005>"),
                    discord.SelectOption(label="Recrutement Staff", value="recrutement", emoji="<:9023blurpleemployee:1481370575954776198>"),
                ],
            ),
        ),
        accent_colour=0x5865F2,
    )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") == "ticket_selector_main":
            # 1. On récupère la valeur technique (ex: "order")
            choice_value = interaction.data.get("values")[0]
            
            # 2. On cherche le texte (label) qui correspond à cette valeur
            select_menu = self.container1.children[2].children[0]
            # Cette variable 'raison_choisie' contiendra "Commander un Site", "Partenariat", etc.
            raison_choisie = next((opt.label for opt in select_menu.options if opt.value == choice_value), "Ticket")
            
            # 3. On envoie cette raison à la fonction de création
            await self.create_ticket(interaction, raison_choisie)
            return True
        return await super().interaction_check(interaction)

    async def create_ticket(self, interaction: discord.Interaction, raison: str):
        guild = interaction.guild
        category = guild.get_channel(TICKET_CATEGORY_ID)
        
        if not category:
            return await interaction.response.send_message("❌ Erreur : Catégorie introuvable.", ephemeral=True)

        # Permissions (Staff + Utilisateur)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }

        staff_mentions = []
        for role_id in STAFF_ROLE_IDS:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                staff_mentions.append(role.mention)

        # Création du salon
        channel = await guild.create_text_channel(
            name=f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        # 1. Notification (Pings)
        mentions_str = " ".join(staff_mentions)
        await channel.send(content=f"{interaction.user.mention} | {mentions_str}")
        
        # 2. Affichage de la RAISON séléctionnée
        embed = discord.Embed(
            title="🎫 Nouveau Ticket",
            description=f"Un nouveau ticket a été ouvert.\n\n**Raison séléctionnée :** {raison}\n**Client :** {interaction.user.mention}",
            color=0x5865F2
        )
        embed.set_footer(text="GhostProtect Support")
        await channel.send(embed=embed)
        
        # 3. Bouton Fermer
        await channel.send(view=TicketControlView())
        
        # Réponse à l'utilisateur
        await interaction.response.send_message(f"✅ Ton ticket pour **{raison}** est ouvert : {channel.mention}", ephemeral=True)
        
@bot.command()
@is_team_owner()
async def ticket(ctx):
    await ctx.send(view=Ticket())
    await ctx.message.delete()

class AddBot(discord.ui.LayoutView):    
    container1 = discord.ui.Container(
        discord.ui.TextDisplay(content="# *Propulse ton serveur avec ServerMaster !*"),
        discord.ui.TextDisplay(content="Marre de jongler entre dix bots différents pour gérer ta communauté ? Découvre **ServerMaster**, l'outil tout-en-un conçu pour simplifier la vie des modérateurs et booster l'activité des membres.\n\n**Pourquoi choisir ServerMaster ?**\n🛡️ **Modération Pro :** Des outils puissants pour garder ton serveur sain et sécurisé sans effort.\n\n⚙️ **Gestion Simplifiée :** Configure tes salons, rôles et permissions en quelques secondes.\n\n📈 **Croissance & Engagement :** Des fonctionnalités pensées pour animer ta communauté et fidéliser tes membres.\n\n⚡ **Performance :** Un bot stable, rapide et disponible 24h/24."),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.TextDisplay(content="**👇 Ajouter le bot au serveur 👇**"),
        discord.ui.Separator(visible=True, spacing=discord.SeparatorSpacing.small),
        discord.ui.ActionRow(
                discord.ui.Button(
                    url="https://discord.com/oauth2/authorize?client_id=1481335929288523899",
                    style=discord.ButtonStyle.link,
                    label="Ajouter",
                    emoji="<:8512blurplelink:1481379552331829308>"
                ),
        ),
        accent_colour=0x5865F2,
    )


@bot.command()
@is_team_owner()
async def commande(ctx: commands.Context) -> None:
    view = AddBot()
    await ctx.send(view=view)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def lockurl(ctx, state: str = "on"):
    guild_id = str(ctx.guild.id)

    if not hasattr(bot, "url_lock"):
        bot.url_lock = {}

    if state.lower() == "on":
        bot.url_lock[guild_id] = True
        await ctx.send("✅ Suppression automatique des URLs activée.")
    elif state.lower() == "off":
        bot.url_lock[guild_id] = False
        await ctx.send("❌ Suppression automatique des URLs désactivée.")
    else:
        await ctx.send("Usage : `+lockurl on/off`")


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    guild_id = str(message.guild.id)
    if getattr(bot, "url_lock", {}).get(guild_id, False):
        # Cherche les URLs
        url_pattern = r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+"
        if re.search(url_pattern, message.content):
            try:
                await message.delete()
                await message.channel.send(f"{message.author.mention}, les liens ne sont pas autorisés ici !", delete_after=5)
            except discord.Forbidden:
                pass

    await bot.process_commands(message)
    

    
@bot.command(name="mutelist")
@commands.has_permissions(moderate_members=True)
async def mutelist(ctx):
    muted_members = [m for m in ctx.guild.members if m.is_timed_out()]
    if not muted_members:
        return await ctx.send("Aucun membre n'est actuellement en mute.")
    
    description = "\n".join([f"{m} ({m.id}) — fin du mute : {m.timed_out_until}" for m in muted_members])
    embed = discord.Embed(
        title="Liste des membres en mute",
        description=description,
        color=discord.Color.orange()
    )
    await ctx.send(embed=embed)
    
@bot.command()
@commands.has_permissions(ban_members=True)
async def banlist(ctx):
    bans = [entry async for entry in ctx.guild.bans()]
    if not bans:
        return await ctx.send("Aucun membre banni sur ce serveur.")
    
    description = "\n".join([f"{entry.user} ({entry.user.id})" for entry in bans])
    embed = discord.Embed(
        title="Liste des membres bannis",
        description=description,
        color=discord.Color.red()
    )
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(manage_channels=True)
async def renew(ctx):
    channel = ctx.channel

    try:
        # clone le salon (mêmes perms / nom / catégorie)
        new_channel = await channel.clone(
            reason=f"Renew par {ctx.author}"
        )

        # remet à la même position
        await new_channel.edit(position=channel.position)

        # supprime l'ancien salon
        await channel.delete()

        # message confirmation
        await new_channel.send("Salon nettoyé")

    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")

@bot.command()
@commands.has_permissions(manage_messages=True)
async def clearurl(ctx, limit: int = 100):
    def is_url(msg):
        url_pattern = r"https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+"
        return re.search(url_pattern, msg.content)

    deleted = await ctx.channel.purge(limit=limit, check=is_url)
    await ctx.send(f"✅ {len(deleted)} message(s) contenant des URLs supprimé(s).", delete_after=5)

@bot.command(name="reagir")
@commands.has_permissions(manage_messages=True)
async def reagir(ctx, message_id: int, emoji: str):
    try:
        message = await ctx.channel.fetch_message(message_id)
        await message.add_reaction(emoji)
        await ctx.send(f"Réaction {emoji} ajoutée au message `{message_id}`.", delete_after=5)
        await ctx.message.delete()
    except discord.NotFound:
        await ctx.send("Message introuvable. Vérifie l'ID.", delete_after=5)
    except discord.HTTPException:
        await ctx.send("Emoji invalide ou erreur de permission.", delete_after=5)
    except Exception as e:
        await ctx.send(f"Une erreur est survenue : {e}", delete_after=5)
        
        
@bot.command()
@commands.has_permissions(administrator=True)
async def ghostping(ctx, target):
    try:
        # @everyone
        if target.lower() == "everyone":
            msg = await ctx.send("@everyone")
            await msg.delete()

        # @here
        elif target.lower() == "here":
            msg = await ctx.send("@here")
            await msg.delete()

        # rôle mentionné
        elif ctx.message.role_mentions:
            role = ctx.message.role_mentions[0]
            msg = await ctx.send(role.mention)
            await msg.delete()

        else:
            await ctx.send("Utilisation : `+ghostping @role` ou `+ghostping everyone` ou `+ghostping here`")

        # supprimer la commande aussi
        await ctx.message.delete()

    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de mentionner ou supprimer les messages.")


@bot.command(name="nick")
@commands.has_permissions(manage_nicknames=True)
async def nick(ctx, member: discord.Member, *, nick: str):
    if not await check_hierarchy(ctx, member, "changer le pseudo de"):
        return

    try:
        await member.edit(nick=nick)
        await ctx.send(f"Le pseudo de {member.mention} a été changé en **{nick}**.")
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de changer ce pseudo.")
    except discord.HTTPException:
        await ctx.send("Une erreur est survenue.")

@bot.command(name="role")
@commands.has_permissions(manage_roles=True)
async def add_role(ctx, member: discord.Member, role: discord.Role):
    # Vérifie hiérarchie (bot + auteur)
    if not await check_hierarchy(ctx, member, "ajouter un rôle à"):
        return
    
    await member.add_roles(role)
    await ctx.send(f"✅ {role.mention} a été ajouté à {member.mention}.")
    
@bot.command(name="delrole")
@commands.has_permissions(manage_roles=True)
async def remove_role(ctx, member: discord.Member, role: discord.Role):
    # Vérifie hiérarchie (bot + auteur)
    if not await check_hierarchy(ctx, member, "retirer un rôle de"):
        return
    
    await member.remove_roles(role)
    await ctx.send(f"✅ {role.mention} a été retiré de {member.mention}.")

@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, option: str = None, user: discord.User = None):
    if option == "all":
        bans = [entry async for entry in ctx.guild.bans()]
        if not bans:
            return await ctx.send("Aucun utilisateur banni")
        count = 0
        for ban_entry in bans:
            try:
                await ctx.guild.unban(ban_entry.user)
                count += 1
            except:
                pass
        return await ctx.send(f"**{count}** utilisateur(s) débanni(s)")
    if user:
        try:
            await ctx.guild.unban(user)
            return await ctx.send(f"**{user}** débanni.")
        except:
            return await ctx.send("Impossible de débannir ce membre")
    return

@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason=None):
    if not await check_hierarchy(ctx, member, "kick"):
        return

    try:
        await member.kick(reason=reason)
        await ctx.send(f"**{member}** a été expulsé. {'Raison : ' + reason if reason else ''}")
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de kicker ce membre.")
    except discord.HTTPException:
        await ctx.send("Impossible de kick ce membre.")

@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, option: str = None, member: discord.Member = None):
    if option == "all":
        count = 0
        for m in ctx.guild.members:
            try:
                if m.is_timed_out():
                    await m.timeout(None)
                    count += 1
            except:
                pass
        return await ctx.send(f"**{count}** utilisateur(s) unmute")
    if member:
        try:
            await member.timeout(None)
            return await ctx.send(f"**{member}** unmute")
        except:
            return await ctx.send("Impossible de unmute ce membre")
    return



@bot.command(name="clear")
@commands.has_permissions(manage_messages=True)
async def clear(ctx, amount: int):
    limit = amount + 1
    try:
        deleted = await ctx.channel.purge(limit=limit)
        await ctx.send(f"{len(deleted)-1} messages supprimés.", delete_after=5)
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission", delete_after=5)
    except discord.HTTPException:
        await ctx.send("Une erreur est survenue lors de la suppression", delete_after=5)




# ✅ CLEANUP → expulse tout le monde d'un vocal
@bot.command()
@commands.has_guild_permissions(move_members=True)
async def cleanup(ctx, channel: discord.VoiceChannel):

    if not channel.members:
        return await ctx.send("Aucun membre dans ce salon.")

    for member in channel.members:
        await member.move_to(None)

    await ctx.send(f"Tous les membres ont été expulsés de {channel.name}")


# ✅ MOOV → déplacer une personne vers un vocal
@bot.command()
@commands.has_guild_permissions(move_members=True)
async def moov(ctx, member: discord.Member, channel: discord.VoiceChannel):

    if not member.voice:
        return await ctx.send("Cette personne n'est pas en vocal.")

    await member.move_to(channel)
    await ctx.send(f"{member.display_name} déplacé vers {channel.name}")


# ✅ MOOVUP → déplacer tous les membres d'un vocal vers un autre
@bot.command()
@commands.has_guild_permissions(move_members=True)
async def moovup(ctx, source: discord.VoiceChannel, destination: discord.VoiceChannel):

    if not source.members:
        return await ctx.send("Aucun membre dans le salon source.")

    for member in source.members:
        await member.move_to(destination)

    await ctx.send(f"Tous les membres de {source.name} ont été déplacés vers {destination.name}")



@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    # On récupère le rôle @everyone du serveur
    everyone = ctx.guild.default_role
    
    # On récupère les permissions actuelles du rôle dans ce salon
    current_overwrite = ctx.channel.overwrites_for(everyone)
    
    # On ne modifie QUE la permission d'envoyer des messages
    current_overwrite.send_messages = False
    
    try:
        await ctx.channel.set_permissions(everyone, overwrite=current_overwrite, reason=f"Salon verrouillé par {ctx.author}")
        await ctx.send(f"Ce salon est désormais verrouillé")
    except Exception as e:
        await ctx.send(f"Erreur : {e}")

@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    """Déverrouille le salon en remettant la permission d'écrire sur 'neutre' ou 'autorisé'."""
    everyone = ctx.guild.default_role
    current_overwrite = ctx.channel.overwrites_for(everyone)
    current_overwrite.send_messages = True 
    
    try:
        await ctx.channel.set_permissions(everyone, overwrite=current_overwrite, reason=f"Salon déverrouillé par {ctx.author}")
        await ctx.send(f"Ce salon est désormais déverrouillé")
    except Exception as e:
        await ctx.send(f"Erreur : {e}")


        
@bot.command()
@commands.has_permissions(administrator=True)
async def setlogs(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    
    # Charger les données existantes
    if os.path.exists("logs_config.json"):
        with open("logs_config.json", "r") as f:
            data = json.load(f)
    else:
        data = {}

    # Enregistrer l'ID pour ce serveur
    data[str(ctx.guild.id)] = channel.id

    with open("logs_config.json", "w") as f:
        json.dump(data, f, indent=4)

    await ctx.send(f"Le salon des logs a été configuré sur {channel.mention}")

@bot.event
async def on_command_completion(ctx):
    # Si la commande est faite en DM, on ignore
    if not ctx.guild:
        return

    # 1. Vérifier si le fichier existe et charger l'ID
    if not os.path.exists("logs_config.json"):
        return

    with open("logs_config.json", "r") as f:
        data = json.load(f)

    log_channel_id = data.get(str(ctx.guild.id))
    if not log_channel_id:
        return # Pas de salon configuré pour ce serveur

    # 2. Récupérer le salon
    log_channel = bot.get_channel(log_channel_id)
    if not log_channel:
        return

    # 3. Création de l'Embed de Log
    embed = discord.Embed(
        title="Log de Commande",
        description=f"Une commande a été exécutée avec succès.",
        color=0x000001
    )
    
    embed.add_field(name="Modérateur", value=f"{ctx.author.mention} (`{ctx.author.id}`)", inline=True)
    embed.add_field(name="Commande", value=f"`{ctx.command.name}`", inline=True)
    embed.add_field(name="Salon", value=ctx.channel.mention, inline=True)
    
    # Nettoyage des arguments pour l'affichage
    args = ", ".join([str(val) for val in ctx.args[2:]]) if len(ctx.args) > 2 else ""
    kwargs = ", ".join([f"{k}={v}" for k, v in ctx.kwargs.items()]) if ctx.kwargs else ""
    all_args = f"{args} {kwargs}".strip()
    
    embed.add_field(name="Arguments", value=f"`{all_args if all_args else 'Aucun'}`", inline=False)
    embed.timestamp = discord.utils.utcnow()
    embed.set_footer(text=f"Serveur : {ctx.guild.name}")

    try:
        await log_channel.send(embed=embed)
    except discord.Forbidden:
        pass


@bot.command()
@commands.has_permissions(administrator=True)
async def welcome(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    
    # Charger les données existantes ou créer un dictionnaire vide
    if os.path.exists("welcome.json"):
        with open("welcome.json", "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}

    # Enregistrer l'ID du salon pour ce serveur
    data[str(ctx.guild.id)] = channel.id

    with open("welcome.json", "w") as f:
        json.dump(data, f, indent=4)

    embed = discord.Embed(
        title="Configuration Bienvenue",
        description=f"Le salon de bienvenue a été configuré sur {channel.mention}",
        color=discord.Color.green()
    )
    await ctx.send(embed=embed)
    
@bot.event
async def on_member_join(member):
    if not os.path.exists("welcome.json"):
        return

    with open("welcome.json", "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return

    channel_id = data.get(str(member.guild.id))
    if not channel_id:
        return

    channel = member.guild.get_channel(channel_id)
    if not channel:
        return

    try:
        # Ligne qui posait problème : vérifie bien l'alignement ici
        msg = await channel.send(f"{member.mention}")
        await asyncio.sleep(0.1)
        await msg.delete()
    except Exception as e:
        print(f"Erreur welcome: {e}")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def mp(ctx, member: discord.Member, *, message: str):
    """Envoie un message privé à un membre via le bot."""
    try:
        embed = discord.Embed(
            title=f"Message de l'équipe de **{ctx.guild.name}**",
            description=message,
            color=0x000001
        )
        embed.set_footer(text="Ne répondez pas à ce message, le bot ne lit pas les MPs.")
        
        await member.send(embed=embed)
        embed = discord.Embed(
            title=f"Mp",
            description=f"Message envoyé avec succès à **{member.display_name}**.",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
    except discord.Forbidden:
        embed = discord.Embed(
            title=f"Mp",
            description=f"Impossible d'envoyer le message (l'utilisateur a fermé ses MPs).",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def dmall(ctx, *, message: str):
    count = 0
    for member in ctx.guild.members:
        if member.bot:
            continue  # ignore les bots
        try:
            await member.send(message)
            count += 1
        except:
            pass  # ignore si impossible d'envoyer
    await ctx.send(f"Message envoyé à **{count}** membre(s).")


# ======================
# BAN COMMAND
# ======================
@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    if not await check_hierarchy(ctx, member, "bannir"):
        return

    try:
        await member.ban(reason=reason)
        await ctx.send(f"**{member}** a été banni pour : **{reason}**")
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de bannir ce membre")
    except Exception as e:
        await ctx.send(f"Erreur : {e}")

# ======================
# BLACKLIST COMMAND (alias de ban)
# ======================
@bot.command()
@commands.has_permissions(ban_members=True)
async def bl(ctx, member: discord.Member, *, reason="Aucune raison fournie"):
    await ban(ctx, member=member, reason=reason)  # réutilise la commande ban

# ======================
# MUTE COMMAND
# ======================
@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, duration: str = "15m", *, reason: str = "Aucune raison fournie"):
    if not await check_hierarchy(ctx, member, "mute"):
        return

    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    unit = duration[-1].lower()
    amount_str = duration[:-1]

    if not amount_str.isdigit() or unit not in units:
        return await ctx.send("Format invalide ! Exemple : `30m`, `2h`")

    seconds = int(amount_str) * units[unit]

    if seconds > 2419200:
        return await ctx.send("Impossible de mute plus de 28 jours")

    delta = timedelta(seconds=seconds)

    try:
        await member.timeout(delta, reason=reason)
        await ctx.send(f"**{member.display_name}** mute pendant **{duration}**")
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de mute ce membre")
    except Exception as e:
        await ctx.send(f"Erreur : {e}")

# ======================
# UNSETNAME COMMAND
# ======================
@bot.command()
@commands.has_permissions(manage_nicknames=True)
async def unnick(ctx, member: discord.Member):
    if not await check_hierarchy(ctx, member, "réinitialiser le pseudo de"):
        return

    try:
        await member.edit(nick=None)
        await ctx.send(f"Le pseudo de **{member}** a été réinitialisé.")
    except discord.Forbidden:
        await ctx.send("Je n'ai pas la permission de modifier ce pseudo.")
    except Exception as e:
        await ctx.send(f"Erreur : {e}")

def parse_duration(duration_str):
    time_dict = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    match = re.match(r"(\d+)([smhd])", duration_str.lower())
    if match:
        value, unit = match.groups()
        return int(value) * time_dict[unit]
    return None

class GiveawaySetupView(discord.ui.View):
    def __init__(self, author):
        super().__init__(timeout=180)
        self.author = author
        self.data = {
            "lot": "Non défini",
            "seconds": None,
            "duration_str": "Non définie",
            "gagnants": 1,
            "salon": None,
            "emoji": "🎉"
        }

    def create_preview_embed(self):
        embed = discord.Embed(
            title="⚙️ Configuration du Giveaway",
            description="Modifiez les paramètres et cliquez sur Lancer.",
            color=discord.Color.blue()
        )
        embed.add_field(name="🎁 Lot", value=self.data["lot"], inline=True)
        embed.add_field(name="⏳ Durée", value=self.data["duration_str"], inline=True)
        embed.add_field(name="👥 Gagnants", value=str(self.data["gagnants"]), inline=True)
        salon_name = self.data["salon"].mention if self.data["salon"] else "Non défini"
        embed.add_field(name="📍 Salon", value=salon_name, inline=True)
        embed.add_field(name="🎭 Réaction", value=self.data["emoji"], inline=True)
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.author:
            await interaction.response.send_message("Tu n'es pas l'organisateur.", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Choisir un paramètre...",
        options=[
            discord.SelectOption(label="Lot", value="lot", emoji="🎁"),
            discord.SelectOption(label="Temps", value="temps", emoji="⏳"),
            discord.SelectOption(label="Gagnants", value="gagnants", emoji="👥"),
            discord.SelectOption(label="Salon", value="salon", emoji="📍"),
            discord.SelectOption(label="Réaction", value="emoji", emoji="🎭")
        ]
    )
    async def select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        choice = select.values[0]
        await interaction.response.send_message(f"Répondez avec la valeur pour : **{choice}**", ephemeral=True)

        def check(m):
            return m.author == self.author and m.channel == interaction.channel

        try:
            msg = await interaction.client.wait_for("message", timeout=30.0, check=check)
            if choice == "lot": self.data["lot"] = msg.content
            elif choice == "temps":
                sec = parse_duration(msg.content)
                if sec:
                    self.data["seconds"] = sec
                    self.data["duration_str"] = msg.content
                else: await interaction.followup.send("Format invalide (ex: 1m)!", ephemeral=True)
            elif choice == "gagnants": self.data["gagnants"] = int(msg.content) if msg.content.isdigit() else 1
            elif choice == "salon": self.data["salon"] = msg.channel_mentions[0] if msg.channel_mentions else interaction.channel
            elif choice == "emoji": self.data["emoji"] = msg.content

            await msg.delete()
            await interaction.message.edit(embed=self.create_preview_embed(), view=self)
        except asyncio.TimeoutError:
            await interaction.followup.send("Délai dépassé.", ephemeral=True)

    @discord.ui.button(label="Lancer le Giveaway", style=discord.ButtonStyle.green, emoji="🚀")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.data["lot"] == "Non défini" or not self.data["seconds"] or not self.data["salon"]:
            return await interaction.response.send_message("❌ Incomplet !", ephemeral=True)

        channel = self.data["salon"]
        end_time = int(time.time() + self.data["seconds"])
        
        embed = discord.Embed(
            title=f"GIVEAWAY : {self.data['lot']}",
            description=f"Réagissez avec {self.data['emoji']} pour participer !\n\n"
                        f"Fin : <t:{end_time}:R>\n"
                        f"Gagnants : **{self.data['gagnants']}**",
            color=0x2b2d31
        )
        
        await interaction.response.send_message("Lancé !", ephemeral=True)
        gv_msg = await channel.send(embed=embed)
        await gv_msg.add_reaction(self.data["emoji"])
        await interaction.message.delete()
        self.stop()

        await asyncio.sleep(self.data["seconds"])
        await finish_giveaway(gv_msg, self.data["emoji"], self.data["lot"], self.data["gagnants"])

# --- Fonction pour finir le giveaway ---
async def finish_giveaway(msg, emoji_str, lot, nb_gagnants):
    msg = await msg.channel.fetch_message(msg.id)
    reaction = next((r for r in msg.reactions if str(r.emoji) == str(emoji_str)), None)
    
    users = [u async for u in reaction.users() if not u.bot] if reaction else []

    if not users:
        embed = msg.embeds[0]
        embed.description = "❌ Terminé. Aucun participant."
        embed.color = discord.Color.red()
        return await msg.edit(embed=embed)

    winners = random.sample(users, min(len(users), nb_gagnants))
    mentions = ", ".join([w.mention for w in winners])
    
    embed = msg.embeds[0]
    embed.description = f"Terminé !\n\nGagnant(s): {mentions}"
    embed.color =0x2b2d31
    await msg.edit(embed=embed)
    await msg.channel.send(f"Félicitations {mentions} ! Tu gagnes **{lot}** !")

# --- Commandes et Events ---

@bot.command()
@commands.has_permissions(manage_messages=True)
async def giveaway(ctx):
    view = GiveawaySetupView(ctx.author)
    await ctx.send(embed=view.create_preview_embed(), view=view)

@bot.command()
@commands.has_permissions(manage_messages=True)
async def reroll(ctx, message_id: int):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        if not msg.embeds or "GIVEAWAY" not in msg.embeds[0].title:
            return await ctx.send("Ce n'est pas un message de giveaway valide.")
        
        # On cherche la réaction utilisée
        reaction = msg.reactions[0] 
        users = [u async for u in reaction.users() if not u.bot]
        
        if not users:
            return await ctx.send("Personne n'a participé.")
        
        winner = random.choice(users)
        await ctx.send(f"🎉 Nouveau tirage : {winner.mention} est le nouveau gagnant !")
    except Exception as e:
        await ctx.send(f"Erreur : {e}")

@bot.event
async def on_raw_reaction_remove(payload):
    # Si quelqu'un enlève sa réaction, on la remet
    if payload.user_id == bot.user.id: return
    
    channel = bot.get_channel(payload.channel_id)
    message = await channel.fetch_message(payload.message_id)
    
    # On vérifie si c'est un message du bot et s'il y a un embed de giveaway
    if message.author == bot.user and message.embeds and "GIVEAWAY" in message.embeds[0].title:
        # Si le giveaway n'est pas encore fini (couleur verte)
        if message.embeds[0].color == discord.Color.green():
            user = await bot.fetch_user(payload.user_id)
            await message.add_reaction(payload.emoji)

bot.run(os.getenv('DISCORD_TOKEN'))