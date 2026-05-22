from typing import TYPE_CHECKING

from .cog import Collectibles as CollectiblesCog
from .admin import CollectAdmin as AdminCollectiblesCog

if TYPE_CHECKING:
    from ballsdex.core.bot import BallsDexBot


async def setup(bot: "BallsDexBot"):
    await bot.add_cog(CollectiblesCog(bot))
    await bot.add_cog(AdminCollectiblesCog(bot))
