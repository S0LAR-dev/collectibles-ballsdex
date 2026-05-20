from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord.ext import commands
from asgiref.sync import sync_to_async
import tomllib

from ballsdex.core.utils import checks
from bd_models.models import Player
from collect.models import Collectible, PlayerCollectible

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.admin.collectibles")

def load_group_name() -> str:
    try:
        with open("config/extra.toml", "rb") as f:
            data = tomllib.load(f)
            return data.get("collectibles", {}).get("group_name", "collectibles")
    except Exception:
        return "collectibles"

GROUP_NAME = load_group_name()
GROUP_NAME_CAP = GROUP_NAME.capitalize()

class CollectibleConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, value: str) -> Collectible:
        try:
            return await sync_to_async(Collectible.objects.get)(pk=int(value))
        except Exception:
            pass
        try:
            return await sync_to_async(Collectible.objects.get)(name__iexact=value)
        except Exception:
            pass
        result = await sync_to_async(
            lambda: Collectible.objects.filter(name__icontains=value).first()
        )()
        if result is None:
            raise commands.BadArgument(f'{GROUP_NAME_CAP[:-1]} "{value}" not found.')
        return result

@commands.hybrid_group(name=GROUP_NAME.lower())
@checks.is_staff()
async def collectibles(ctx: commands.Context["BallsDexBot"]):
    await ctx.send_help(ctx.command)

@collectibles.command(name="give")
@checks.is_staff()
async def collectibles_give(
    ctx: commands.Context["BallsDexBot"],
    user: discord.User,
    collectible: CollectibleConverter,
):
    player, _ = await sync_to_async(Player.objects.get_or_create)(discord_id=user.id)
    exists = await sync_to_async(
        PlayerCollectible.objects.filter(player=player, collectible=collectible).exists
    )()
    if exists:
        await ctx.send(f"{user.mention} already owns **{collectible.name}**.", ephemeral=True)
        return
    await sync_to_async(PlayerCollectible.objects.create)(player=player, collectible=collectible)
    await ctx.send(f"✅ Gave **{collectible.name}** to {user.mention}. Reload the cache to load the instance.", ephemeral=True)
    log.info(
        f"{ctx.author} ({ctx.author.id}) gave '{collectible.name}' to {user} ({user.id})",
        extra={"webhook": True},
    )

@collectibles.command(name="remove")
@checks.is_staff()
async def collectibles_remove(
    ctx: commands.Context["BallsDexBot"],
    user: discord.User,
    collectible: CollectibleConverter,
):
    try:
        player = await sync_to_async(Player.objects.get)(discord_id=user.id)
        owned = await sync_to_async(PlayerCollectible.objects.get)(
            player=player, collectible=collectible
        )
    except Exception:
        await ctx.send(f"{user.mention} does not own **{collectible.name}**.", ephemeral=True)
        return
    await sync_to_async(owned.delete)()
    await ctx.send(f"🗑️ Removed **{collectible.name}** from {user.mention}. Reload the cache to update the players data.", ephemeral=True)
    log.info(
        f"{ctx.author} ({ctx.author.id}) removed '{collectible.name}' from {user} ({user.id})",
        extra={"webhook": True},
    )

@collectibles.command(name="create")
@checks.is_staff()
async def collectibles_create(
    ctx: commands.Context["BallsDexBot"],
    name: str,
    emoji: str,
    cost: int,
    image_url: str,
    requirement_type: str | None = None,
    requirement_value: str | None = None,
):
    exists = await sync_to_async(Collectible.objects.filter(name__iexact=name).exists)()
    if exists:
        await ctx.send(f"A {GROUP_NAME[:-1]} with that name already exists.", ephemeral=True)
        return
    collectible = await sync_to_async(Collectible.objects.create)(
        name=name,
        emoji=emoji,
        cost=cost,
        image_url=image_url,
        requirement_type=requirement_type,
        requirement_value=requirement_value,
    )
    await ctx.send(f"✨ Created **{collectible.name}**. Reload the bot's cache to load the new collectible.\n{collectible.image_url}", ephemeral=True)
    log.info(
        f"{ctx.author} ({ctx.author.id}) created collectible '{collectible.name}'",
        extra={"webhook": True},
    )
