import logging
from typing import TYPE_CHECKING, List, Optional

import discord
from discord import app_commands
from discord.ext import commands
from django.core.exceptions import ObjectDoesNotExist
from asgiref.sync import sync_to_async
import tomllib

from bd_models.models import Player, Ball, BallInstance
from collect.models import Collectible, PlayerCollectible, GroupName
from ballsdex.core.utils.utils import inventory_privacy, is_staff

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot

log = logging.getLogger("ballsdex.packages.collectibles")

GROUP_NAME: str = "collectible"
GROUP_NAME_CAP: str = GROUP_NAME.capitalize()
plural: str = "collectibles"


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
            f"Not enough money. You need 🪙**{collectible.cost}**, "
            f"but you only have 🪙**{player.money}**."
        )
    if not await meets_requirement(player, collectible):
        return f"You don't meet the requirement for this {GROUP_NAME[:-1]}."
    player.money -= collectible.cost
    await sync_to_async(player.save)()
    await sync_to_async(PlayerCollectible.objects.create)(
        player=player,
        collectible=collectible,
    )
    return f"Successfully purchased the **{collectible.name}**!"


class PrevButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="←", custom_id="prev")

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message(
                f"You're not allowed to browse someone else's {GROUP_NAME}.",
                ephemeral=True,
            )
            return
        await view.handle_navigation(interaction, -1)


class NextButton(discord.ui.Button):
    def __init__(self):
        super().__init__(style=discord.ButtonStyle.secondary, label="→", custom_id="next")

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message(
                f"You're not allowed to browse someone else's {GROUP_NAME}.",
                ephemeral=True,
            )
            return
        await view.handle_navigation(interaction, 1)


class BuyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Buy",
            custom_id="buy",
            emoji="🪙",
        )

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message(
                f"You're not allowed to buy {plural} in someone else's shop.",
                ephemeral=True,
            )
            return
        await view.handle_purchase(interaction)


class CollectibleSelect(discord.ui.Select):
    def __init__(self, collectibles: List[Collectible], bot: "BallsDexBot"):
        options: list[discord.SelectOption] = []
        for idx, collectible in enumerate(collectibles):
            emoji = render_emoji(bot, collectible.emoji)
            options.append(
                discord.SelectOption(
                    label=collectible.name,
                    description=f"Cost: {collectible.cost}"[:100],
                    emoji=emoji if emoji else None,
                    value=str(idx),
                )
            )
        super().__init__(
            placeholder=f"Select a {GROUP_NAME} to view...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="collectible_select",
        )

    async def callback(self, interaction: discord.Interaction):
        view: CollectibleShopView = self.view
        if interaction.user.id != view.player.discord_id:
            await interaction.response.send_message(
                f"You're not allowed to browse someone else's {GROUP_NAME}.",
                ephemeral=True,
            )
            return
        view.index = int(self.values[0])
        view.update_layout()
        await interaction.response.edit_message(view=view)


class CollectibleShopView(discord.ui.LayoutView):
    def __init__(
        self,
        player: Player,
        collectibles: List[Collectible],
        bot: "BallsDexBot",
    ):
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.collectibles = collectibles
        self.index = 0
        self.message: Optional[discord.Message] = None
        self.update_layout()

    def update_layout(self):
        self.clear_items()
        collectible = self.collectibles[self.index]
        emoji = render_emoji(self.bot, collectible.emoji)

        header = (
            f"{emoji} **{collectible.name}**"
            if emoji
            else f"**{collectible.name}**"
        )
        bio_text = (
            f"*{collectible.bio}*"
            if collectible.bio
            else "*No biography available.*"
        )
        cost_text = f"🪙 **{collectible.cost}**"
        requirement_text = format_requirement(collectible)

        layout = discord.ui.Container(
            discord.ui.TextDisplay(content=f"The {GROUP_NAME_CAP} Store!"),
            discord.ui.TextDisplay(content=header),
            discord.ui.TextDisplay(content=bio_text),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            discord.ui.TextDisplay(content=f"**__Cost__**\n{cost_text}"),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.small),
            discord.ui.TextDisplay(
                content=f"**__Requirement__**\n{requirement_text}"
            ),
            discord.ui.Separator(spacing=discord.SeparatorSpacing.large),
            (
                discord.ui.MediaGallery(
                    discord.MediaGalleryItem(media=collectible.image_url)
                )
                if collectible.image_url
                else None
            ),
            discord.ui.ActionRow(
                CollectibleSelect(self.collectibles, self.bot),
            ),
            discord.ui.ActionRow(
                PrevButton(),
                BuyButton(),
                NextButton(),
            ),
            accent_colour=discord.Colour.blurple(),
        )
        self.add_item(layout)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.player.discord_id

    async def on_timeout(self):
        self.clear_items()
        if self.message:
            await self.message.edit(view=self)

    async def handle_navigation(
        self,
        interaction: discord.Interaction,
        direction: int,
    ):
        self.index = (self.index + direction) % len(self.collectibles)
        self.update_layout()
        await interaction.response.edit_message(view=self)

    async def handle_purchase(self, interaction: discord.Interaction):
        collectible = self.collectibles[self.index]
        result = await purchase_collectible(self.player, collectible)
        await interaction.response.send_message(result, ephemeral=True)


class Collectibles(commands.GroupCog, group_name="collectibles"):
    def __init__(self, bot: "BallsDexBot"):
        self.bot = bot
        self.group_model: GroupName | None = None

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

    @app_commands.command(
        name="store",
        description=f"Browse and purchase {plural}.",
    )
    async def store(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            player = await sync_to_async(Player.objects.get)(
                discord_id=interaction.user.id
            )
        except ObjectDoesNotExist:
            await interaction.followup.send(
                "You don't have any player data yet.",
                ephemeral=True,
            )
            return

        collectibles = await sync_to_async(list)(
            Collectible.objects.all().order_by("id")
        )
        if not collectibles:
            await interaction.followup.send(
                f"There are no {plural} available yet.",
                ephemeral=True,
            )
            return

        view = CollectibleShopView(player, collectibles, self.bot)
        message = await interaction.followup.send(view=view)
        view.message = message

    @app_commands.command(
        name="completion",
        description=f"Show your current {GROUP_NAME} completion.",
    )
    @app_commands.checks.cooldown(1, 20, key=lambda i: i.user.id)
    async def completion(
        self,
        interaction: discord.Interaction["BallsDexBot"],
        user: discord.User | None = None,
    ):
        user_obj = user or interaction.user
        await interaction.response.defer(thinking=True)

        try:
            player = await sync_to_async(Player.objects.get)(
                discord_id=user_obj.id
            )
        except ObjectDoesNotExist:
            await interaction.followup.send(
                f"{user_obj.name} doesn't own any {plural}.",
            )
            return

        interaction_player, _ = await sync_to_async(
            Player.objects.get_or_create
        )(discord_id=interaction.user.id)

        blocked = await player.is_blocked(interaction_player)
        if blocked and not is_staff(interaction):
            await interaction.followup.send(
                f"You cannot view the {plural} of a user who has blocked you.",
                ephemeral=True,
            )
            return

        if inventory_privacy(self.bot, interaction, player, user_obj) is False:
            return

        all_items = await sync_to_async(list)(
            Collectible.objects.all().order_by("id")
        )
        all_items_by_id = {c.id: c for c in all_items if c.emoji}

        owned_ids = set(
            await sync_to_async(list)(
                PlayerCollectible.objects.filter(player=player).values_list(
                    "collectible_id",
                    flat=True,
                )
            )
        )

        entries: list[tuple[str, str]] = []

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
            fill_fields(f"Owned {GROUP_NAME_CAP}", owned_ids)
        else:
            entries.append(
                (f"__**Owned {GROUP_NAME_CAP}**__", "Nothing yet.")
            )

        missing_ids = set(all_items_by_id.keys()) - owned_ids
        if missing_ids:
            fill_fields(f"Missing {GROUP_NAME_CAP}", missing_ids)
        else:
            entries.append(
                (
                    f"__**:tada: No missing {GROUP_NAME}! :tada:**__",
                    "\u200b",
                )
            )

        completion_percent = (
            round(len(owned_ids) / len(all_items_by_id) * 100, 1)
            if all_items_by_id
            else 0.0
        )

        embed = discord.Embed(
            title=f"{user_obj.display_name}'s {GROUP_NAME_CAP} Completion",
            description=(
                f"Progress: **{completion_percent}% "
                f"({len(owned_ids)}/{len(all_items_by_id)})**"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_author(
            name=user_obj.display_name,
            icon_url=user_obj.display_avatar.url,
        )

        for name, value in entries:
            embed.add_field(name=name, value=value, inline=False)

        await interaction.followup.send(embed=embed)
