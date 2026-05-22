from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands
from asgiref.sync import sync_to_async, async_to_sync
import tomllib

from ballsdex.core.utils import checks
from bd_models.models import Player
from collect.models import Collectible, PlayerCollectible, GroupName

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.admin.collectibles")

GROUP_MODEL = async_to_sync(GroupName.objects.aget)(pk=1)

GROUP_NAME = GROUP_MODEL.group_name
GROUP_NAME_CAP = GROUP_NAME.capitalize()
plural = GROUP_MODEL.plural

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


class Collectibles(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot

    collectibles = app_commands.Group(
        name=GROUP_NAME.lower(),
        description=f"{GROUP_NAME_CAP} management commands",
    )

    @collectibles.command(name="give")
    @checks.is_staff()
    async def collectibles_give(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        collectible: str,
    ):
        ctx = await commands.Context.from_interaction(interaction)

        try:
            collectible_obj = await CollectibleConverter().convert(ctx, collectible)
        except commands.BadArgument as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        player, _ = await sync_to_async(Player.objects.get_or_create)(
            discord_id=user.id
        )

        exists = await sync_to_async(
            PlayerCollectible.objects.filter(
                player=player,
                collectible=collectible_obj,
            ).exists
        )()

        if exists:
            await interaction.response.send_message(
                f"{user.mention} already owns **{collectible_obj.name}**.",
                ephemeral=True,
            )
            return

        await sync_to_async(PlayerCollectible.objects.create)(
            player=player,
            collectible=collectible_obj,
        )

        await interaction.response.send_message(
            f"✅ Gave **{collectible_obj.name}** to {user.mention}. "
            f"Reload the cache to load the instance.",
            ephemeral=True,
        )

        log.info(
            f"{interaction.user} ({interaction.user.id}) gave "
            f"'{collectible_obj.name}' to {user} ({user.id})",
            extra={"webhook": True},
        )

    @collectibles.command(name="remove")
    @checks.is_staff()
    async def collectibles_remove(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        collectible: str,
    ):
        ctx = await commands.Context.from_interaction(interaction)

        try:
            collectible_obj = await CollectibleConverter().convert(ctx, collectible)
        except commands.BadArgument as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        try:
            player = await sync_to_async(Player.objects.get)(discord_id=user.id)

            owned = await sync_to_async(PlayerCollectible.objects.get)(
                player=player,
                collectible=collectible_obj,
            )

        except Exception:
            await interaction.response.send_message(
                f"{user.mention} does not own **{collectible_obj.name}**.",
                ephemeral=True,
            )
            return

        await sync_to_async(owned.delete)()

        await interaction.response.send_message(
            f"Removed **{collectible_obj.name}** from {user.mention}. "
            f"Reload the cache to update the players data.",
            ephemeral=True,
        )

        log.info(
            f"{interaction.user} ({interaction.user.id}) removed "
            f"'{collectible_obj.name}' from {user} ({user.id})",
            extra={"webhook": True},
        )

    @collectibles.command(name="create")
    @checks.is_staff()
    async def collectibles_create(
        self,
        interaction: discord.Interaction,
        name: str,
        emoji: str,
        cost: int,
        image_url: str,
        requirement_type: str | None = None,
        requirement_value: str | None = None,
    ):
        exists = await sync_to_async(
            Collectible.objects.filter(name__iexact=name).exists
        )()

        if exists:
            await interaction.response.send_message(
                f"A {GROUP_NAME[:-1]} with that name already exists.",
                ephemeral=True,
            )
            return

        collectible = await sync_to_async(Collectible.objects.create)(
            name=name,
            emoji=emoji,
            cost=cost,
            image_url=image_url,
            requirement_type=requirement_type,
            requirement_value=requirement_value,
        )

        await interaction.response.send_message(
            f"Created **{collectible.name}**.\n"
            f"Reload the bot's cache to load the new collectible.\n"
            f"{collectible.image_url}",
            ephemeral=True,
        )

        log.info(
            f"{interaction.user} ({interaction.user.id}) created "
            f"collectible '{collectible.name}'",
            extra={"webhook": True},
        )