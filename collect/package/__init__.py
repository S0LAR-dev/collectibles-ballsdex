from typing import TYPE_CHECKING

from .cog import Collectibles as CollectiblesCog
from .admin import CollectAdmin as AdminCollectiblesCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(CollectiblesCog(bot))

    admin_cog = AdminCollectiblesCog(bot)
    await bot.add_cog(admin_cog)
    root_admin = bot.cogs.get("Admin")
    if root_admin is not None and hasattr(root_admin, "admin"):
        root_admin.admin.add_command(admin_cog.collectibles)
