from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from django.core.exceptions import ObjectDoesNotExist
from asgiref.sync import sync_to_async

from bd_models.models import Player, BallInstance
from collect.models import Collectible, PlayerCollectible, GroupName
from settings.models import Settings
from ballsdex.core.utils.utils import inventory_privacy, is_staff

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collectibles")

GROUP_NAME = "collectible"
GROUP_NAME_CAP = GROUP_NAME.capitalize()
plural = "collectibles"


async def get_currency():
    settings = await sync_to_async(Settings.objects.first)()
    if not settings or not settings.currency_name:
        return ("Currency", "Currencies", "")
    return (
        settings.currency_name,
        settings.currency_plural_name or settings.currency_name + "s",
        settings.currency_symbol or "",
    )


def render_emoji(bot: discord.Client, value: str | None) -> str:
    if not value:
        return ""
    if value.isdigit():
        emoji = bot.get_emoji(int(value))
        return str(emoji) if emoji else f"<:_: {value}>"
    return value


def format_requirement(collectible: Collectible) -> str:
    match collectible.requirement_type:
        case "total":
            return f"Have {collectible.requirement_value} total balls."
        case "shiny":
            return f"Obtain {collectible.requirement_value} shiny balls."
        case "ball":
            return f"Catch 1 {collectible.requirement_value}."
        case "balls":
            return f"Catch {collectible.requirement_value}."
        case "special":
            return f"Own a {collectible.requirement_value}."
        case _:
            return "No requirement, just buy!"


async def meets_requirement(player: Player, collectible: Collectible) -> bool:
    match collectible.requirement_type:
        case "total":
            count = await sync_to_async(
                BallInstance.objects.filter(player=player).count
            )()
            return count >= int(collectible.requirement_value)
        case "shiny":
            shiny_count = await sync_to_async(
                BallInstance.objects.filter(
                    player=player,
                    special__name="Shiny",
                ).count
            )()
            return shiny_count >= int(collectible.requirement_value)
        case "ball":
            return await sync_to_async(
                BallInstance.objects.filter(
                    player=player,
                    ball__country=collectible.requirement_value,
                ).exists
            )()
        case "balls":
            try:
                amount_str, country = collectible.requirement_value.split(maxsplit=1)
                amount = int(amount_str)
            except ValueError:
                return False
            count = await sync_to_async(
                BallInstance.objects.filter(
                    player=player,
                    ball__country=country,
                ).count
            )()
            return count >= amount
        case "special":
            try:
                special_name, country = collectible.requirement_value.split(
                    maxsplit=1
                )
            except ValueError:
                return False
            return await sync_to_async(
                BallInstance.objects.filter(
                    player=player,
                    special__name__iexact=special_name,
                    ball__country__iexact=country,
                ).exists
            )()
        case _:
            return True


async def purchase_collectible(player: Player, collectible: Collectible) -> str:
    currency_name, currency_plural, currency_symbol = await get_currency()
    exists = await sync_to_async(
        PlayerCollectible.objects.filter(
            player=player,
            collectible=collectible,
        ).exists
    )()
    if exists:
        return "You already own this item."
    if player.money < collectible.cost:
        return (
            f"Not enough {currency_name.lower()}. "
            f"You need <:Rosaries:1513372255999098910> **{collectible.cost}**, "
            f"but you only have <:Rosaries:1513372255999098910> **{player.money}**."
        )
    if not await meets_requirement(player, collectible):
        return f"You don't meet the requirement for this {GROUP_NAME[:-1]}."
    player.money -= collectible.cost
    await sync_to_async(player.save)()
    await sync_to_async(PlayerCollectible.objects.create)(
        player=player,
        collectible=collectible,
    )
    return (
        f"Successfully purchased the **{collectible.name}** "
        f"for <:Rosaries:1513372255999098910> {collectible.cost}!"
    )


class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="←", custom_id="prev")

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to browse someone else's shop.", ephemeral=True)
            return
        await view.handle_page_navigation(interaction, -1)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="→", custom_id="next")

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to browse someone else's shop.", ephemeral=True)
            return
        await view.handle_page_navigation(interaction, 1)


class BuyButton(discord.ui.Button):
    def __init__(self, currency_symbol: str):
        super().__init__(
            style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji(name="Rosaries", id=1513372255999098910),
            label=f" Buy",
            custom_id="buy"
        )

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to buy items in someone else's shop.", ephemeral=True)
            return
        await view.handle_purchase(interaction)


class CollectibleSelect(discord.ui.Select):
    def __init__(self, collectibles: List[Collectible], bot: "BallsDexBot", page: int, page_size: int):
        options = []
        start = page * page_size
        end = min(start + page_size, len(collectibles))
        for idx, collectible in enumerate(collectibles[start:end], start=start):
            emoji = render_emoji(bot, collectible.emoji)
            label = collectible.name
            description = f"Cost: {collectible.cost}"
            options.append(
                discord.SelectOption(
                    label=label,
                    description=description[:100],
                    emoji=emoji if emoji else None,
                    value=str(idx),
                )
            )
        super().__init__(
            placeholder="Select an item to view...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="collectible_select"
        )

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message("You're not allowed to browse someone else's shop.", ephemeral=True)
            return
        view.index = int(self.values[0])
        view.page = view.index // view.page_size
        view.update_layout()
        await interaction.response.edit_message(view=view)


class CollectibleShopView(discord.ui.LayoutView):
    def __init__(self, player: Player, collectibles: List[Collectible], bot: "BallsDexBot"):
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.collectibles = collectibles
        self.index = 0
        self.page_size = 20
        self.page = 0
        self.message: Optional[discord.Message] = None
        self.update_layout()

    def total_pages(self) -> int:
        if not self.collectibles:
            return 1
        return (len(self.collectibles) - 1) // self.page_size + 1

    def clamp_state(self):
        if not self.collectibles:
            self.index = 0
            self.page = 0
            return
        self.index %= len(self.collectibles)
        self.page = max(0, min(self.page, self.total_pages() - 1))

    def update_layout(self):
        self.clear_items()
        if not self.collectibles:
            return
        self.clamp_state()
        collectible = self.collectibles[self.index]
        emoji = render_emoji(self.bot, collectible.emoji)
        currency_name, currency_plural, currency_symbol = self.bot.currency_cache

        header = f"{emoji} **{collectible.name}**" if emoji else f"**{collectible.name}**"
        bio_text = f"*{collectible.bio}*" if collectible.bio else "*No biography available.*"
        cost_text = f"<:Rosaries:1513372255999098910> **{collectible.cost}**"
        requirement_text = format_requirement(collectible)

        layout = discord.ui.Container(
            discord.ui.TextDisplay(content=f"The {GROUP_NAME_CAP} Store! Page {self.page + 1}/{self.total_pages()}"),
            discord.ui.TextDisplay(content=header),
            discord.ui.TextDisplay(content=bio_text),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            discord.ui.TextDisplay(content=f"**__Cost__**\n{cost_text}"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(content=f"**__Requirement__**\n{requirement_text}"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            discord.ui.MediaGallery(
                discord.MediaGalleryItem(media=collectible.image_url)
            ) if collectible.image_url else None,
            accent_colour=discord.Colour.blurple()
        )

        self.add_item(layout)
        self.add_item(discord.ui.ActionRow(CollectibleSelect(self.collectibles, self.bot, self.page, self.page_size)))
        self.add_item(discord.ui.ActionRow(PrevButton(), BuyButton(currency_symbol), NextButton()))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.player.discord_id

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            await self.message.edit(view=self)

    async def handle_page_navigation(self, interaction: discord.Interaction, direction: int):
        if not self.collectibles:
            return
        self.page = (self.page + direction) % self.total_pages()
        self.index = self.page * self.page_size
        self.update_layout()
        await interaction.response.edit_message(view=self)

    async def handle_purchase(self, interaction: discord.Interaction):
        if not self.collectibles:
            await interaction.response.send_message("There are no items available to purchase.", ephemeral=True)
            return
        collectible = self.collectibles[self.index]
        result = await purchase_collectible(self.player, collectible)
        await interaction.response.send_message(result, ephemeral=True)


class Collectibles(commands.Cog):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.group_model = None
        self.group = None
        self.bot.currency_cache = ("Currency", "Currencies", "")

    async def cog_load(self):
        global GROUP_NAME, GROUP_NAME_CAP, plural

        try:
            self.group_model = await GroupName.objects.aget(pk=1)
        except GroupName.DoesNotExist:
            self.group_model = await GroupName.objects.acreate(
                group_name="collectible",
                plural="collectibles",
            )

        GROUP_NAME = self.group_model.group_name
        GROUP_NAME_CAP = GROUP_NAME.capitalize()
        plural = self.group_model.plural

        self.group = app_commands.Group(
            name=plural.lower(),
            description=f"{GROUP_NAME_CAP} commands",
        )

        self.bot.currency_cache = await get_currency()

        self.group.add_command(
            app_commands.Command(
                name="store",
                description=f"Browse and purchase {plural}.",
                callback=self.store,
            )
        )

        self.group.add_command(
            app_commands.Command(
                name="completion",
                description="Show your current completion.",
                callback=self.completion,
            )
        )

        self.bot.tree.add_command(self.group)

    async def store(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            player = await sync_to_async(Player.objects.get)(discord_id=interaction.user.id)
        except ObjectDoesNotExist:
            await interaction.followup.send("You don't have any player data yet.", ephemeral=True)
            return

        collectibles = await sync_to_async(list)(Collectible.objects.all().order_by("id"))
        if not collectibles:
            await interaction.followup.send(f"There are no {plural} available yet.", ephemeral=True)
            return

        view = CollectibleShopView(player, collectibles, self.bot)
        message = await interaction.followup.send(view=view)
        view.message = message

    async def completion(self, interaction: discord.Interaction, user: discord.User | None = None):
        
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)

        try:
            player = await sync_to_async(Player.objects.get)(discord_id=user_obj.id)
        except ObjectDoesNotExist:
            await interaction.followup.send(f"{user_obj.name} doesn't own any {plural}.")
            return

        interaction_player, _ = await sync_to_async(Player.objects.get_or_create)(discord_id=interaction.user.id)

        blocked = await player.is_blocked(interaction_player)
        if blocked and not is_staff(interaction):
            await interaction.followup.send(f"You cannot view the {plural} of a user who has blocked you.", ephemeral=True)
            return

        if await inventory_privacy(self.bot, interaction, player, user_obj) is False:
            return

        all_items = await sync_to_async(list)(Collectible.objects.all().order_by("id"))
        all_items_by_id = {c.id: c for c in all_items if c.emoji}

        owned_ids = set(
            await sync_to_async(list)(
                PlayerCollectible.objects.filter(player=player).values_list("collectible_id", flat=True)
            )
        )

        entries = []

        def fill_fields(title: str, ids: set[int]):
            first = False
            buffer = ""
            for cid in sorted(ids):
                item = all_items_by_id.get(cid)
                if not item:
                    continue
                emoji_str = render_emoji(self.bot, item.emoji)
                if len(buffer) + len(emoji_str) > 1024:
                    if first:
                        entries.append(("\u200b", buffer))
                    else:
                        entries.append((f"__**{title}**__", buffer))
                        first = True
                    buffer = ""
                buffer += emoji_str + " "
            if buffer:
                if first:
                    entries.append(("\u200b", buffer))
                else:
                    entries.append((f"__**{title}**__", buffer))

        if owned_ids:
            fill_fields(f"Owned {plural}", owned_ids)
        else:
            entries.append((f"__**Owned {plural}**__", "Nothing yet."))

        missing_ids = set(all_items_by_id.keys()) - owned_ids
        if missing_ids:
            fill_fields(f"Missing {plural}", missing_ids)
        else:
            entries.append((f"__**:tada: No missing {plural}! :tada:**__", "\u200b"))

        completion_percent = (
            round(len(owned_ids) / len(all_items_by_id) * 100, 1)
            if all_items_by_id else 0.0
        )

        embed = discord.Embed(
            title=f"{user_obj.display_name}'s {GROUP_NAME_CAP} Completion",
            description=f"Progress: **{completion_percent}% ({len(owned_ids)}/{len(all_items_by_id)})**",
            color=discord.Color.blurple(),
        )
        embed.set_author(name=user_obj.display_name, icon_url=user_obj.display_avatar.url)

        for name, value in entries:
            embed.add_field(name=name, value=value, inline=False)

        await interaction.followup.send(embed=embed)
