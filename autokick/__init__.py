from .autokick import AutoKick


async def setup(bot):
    cog = AutoKick(bot)
    await bot.add_cog(cog)
