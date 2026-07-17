import discord
from redbot.core import commands, Config
from redbot.core.bot import Red
from discord.ext import tasks
from datetime import timedelta


DEFAULT_DM_MESSAGE = (
    "Hey! You joined **{guild}** {days} day(s) ago but haven't been verified yet "
    "(no ticket has been approved for you). You've been removed from the server. "
    "If this was a mistake, feel free to rejoin and open a ticket to get verified."
)


class AutoKick(commands.Cog):
    """Kick members who never receive a designated 'verified' role within N days of joining."""

    def __init__(self, bot: Red):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=9834756123, force_registration=True)
        default_guild = {
            "toggle": False,
            "role_ids": [],
            "days": 3,
            "log_channel_id": None,
            "dm_enabled": True,
            "dm_message": DEFAULT_DM_MESSAGE,
        }
        self.config.register_guild(**default_guild)
        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    @tasks.loop(minutes=30)
    async def check_loop(self):
        await self.bot.wait_until_red_ready()
        for guild in self.bot.guilds:
            try:
                await self._check_guild(guild)
            except Exception:
                # never let one guild's failure kill the loop
                self.bot.logger.exception(f"AutoKick: error processing guild {guild.id}") if hasattr(self.bot, "logger") else None

    async def _check_guild(self, guild: discord.Guild):
        settings = await self.config.guild(guild).all()
        if not settings["toggle"] or not settings["role_ids"]:
            return

        roles = [guild.get_role(rid) for rid in settings["role_ids"]]
        roles = [r for r in roles if r is not None]
        if not roles:
            return  # all configured roles were deleted; owner needs to reconfigure
        role_names = ", ".join(r.name for r in roles)
        role_mentions = ", ".join(r.mention for r in roles)

        days = settings["days"]
        cutoff = discord.utils.utcnow() - timedelta(days=days)
        log_channel = guild.get_channel(settings["log_channel_id"]) if settings["log_channel_id"] else None

        # Fetch members directly from the API instead of relying on the gateway
        # cache — guild.members can silently miss members who haven't been
        # active/cached since the bot last started, especially older joins.
        async for member in guild.fetch_members(limit=None):
            if member.bot:
                continue
            if any(role in member.roles for role in roles):
                continue
            if member.joined_at is None or member.joined_at > cutoff:
                continue

            # Skip if bot can't act on them (higher role, etc.) - let it raise and be caught below
            if settings["dm_enabled"]:
                try:
                    msg = settings["dm_message"].format(guild=guild.name, days=days)
                    await member.send(msg)
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

            try:
                await guild.kick(
                    member,
                    reason=f"AutoKick: not verified ({role_names}) within {days} day(s) of joining.",
                )
            except discord.Forbidden:
                if log_channel:
                    await log_channel.send(
                        f"⚠️ Couldn't kick {member.mention} (`{member.id}`) — missing permissions "
                        f"or their role is higher than mine."
                    )
                continue
            except discord.HTTPException:
                continue

            if log_channel:
                joined_str = discord.utils.format_dt(member.joined_at, "R") if member.joined_at else "unknown"
                await log_channel.send(
                    f"🚪 Kicked {member} (`{member.id}`) — joined {joined_str}, never received any of {role_mentions}."
                )

    @check_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_red_ready()

    @commands.group()
    @commands.guild_only()
    @commands.admin_or_permissions(kick_members=True)
    async def autokick(self, ctx: commands.Context):
        """Configure auto-kicking of unverified members."""

    @autokick.group(name="role", invoke_without_command=True)
    async def autokick_role(self, ctx: commands.Context):
        """Manage verified roles. A member with ANY of these roles is considered verified."""
        await ctx.send_help()

    @autokick_role.command(name="add")
    async def autokick_role_add(self, ctx: commands.Context, role: discord.Role):
        """Add a role that marks a member as verified (e.g. your Member role)."""
        role_ids = await self.config.guild(ctx.guild).role_ids()
        if role.id in role_ids:
            await ctx.send(f"{role.mention} is already a verified role.")
            return
        role_ids.append(role.id)
        await self.config.guild(ctx.guild).role_ids.set(role_ids)
        await ctx.send(f"Added {role.mention} as a verified role. Members with any verified role are skipped by auto-kick.")

    @autokick_role.command(name="remove")
    async def autokick_role_remove(self, ctx: commands.Context, role: discord.Role):
        """Remove a role from the verified roles list."""
        role_ids = await self.config.guild(ctx.guild).role_ids()
        if role.id not in role_ids:
            await ctx.send(f"{role.mention} isn't currently a verified role.")
            return
        role_ids.remove(role.id)
        await self.config.guild(ctx.guild).role_ids.set(role_ids)
        await ctx.send(f"Removed {role.mention} from the verified roles list.")

    @autokick_role.command(name="list")
    async def autokick_role_list(self, ctx: commands.Context):
        """List the currently configured verified roles."""
        role_ids = await self.config.guild(ctx.guild).role_ids()
        roles = [ctx.guild.get_role(rid) for rid in role_ids]
        roles = [r for r in roles if r is not None]
        if not roles:
            await ctx.send("No verified roles are set.")
            return
        await ctx.send("Verified roles: " + ", ".join(r.mention for r in roles))

    @autokick.command(name="days")
    async def autokick_days(self, ctx: commands.Context, days: int):
        """Set how many days a member has to get verified before being kicked."""
        if days < 1:
            await ctx.send("Days must be at least 1.")
            return
        await self.config.guild(ctx.guild).days.set(days)
        await ctx.send(f"Members will now be kicked after {days} day(s) if still unverified.")

    @autokick.command(name="toggle")
    async def autokick_toggle(self, ctx: commands.Context, on_off: bool):
        """Enable or disable auto-kicking."""
        await self.config.guild(ctx.guild).toggle.set(on_off)
        role_ids = await self.config.guild(ctx.guild).role_ids()
        if on_off and not role_ids:
            await ctx.send(
                "⚠️ Auto-kick is enabled but no verified roles are set yet — run `[p]autokick role add <role>` first, "
                "otherwise nothing will happen."
            )
        else:
            await ctx.send(f"Auto-kick is now {'enabled' if on_off else 'disabled'}.")

    @autokick.command(name="logchannel")
    async def autokick_logchannel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        """Set (or clear, if omitted) a channel to log kicks to."""
        await self.config.guild(ctx.guild).log_channel_id.set(channel.id if channel else None)
        await ctx.send(f"Log channel set to {channel.mention}." if channel else "Log channel cleared.")

    @autokick.command(name="dmtoggle")
    async def autokick_dmtoggle(self, ctx: commands.Context, on_off: bool):
        """Enable or disable DM'ing members before they're kicked."""
        await self.config.guild(ctx.guild).dm_enabled.set(on_off)
        await ctx.send(f"DM on kick is now {'enabled' if on_off else 'disabled'}.")

    @autokick.command(name="dmmessage")
    async def autokick_dmmessage(self, ctx: commands.Context, *, message: str = None):
        """Set (or reset, if omitted) the DM message sent before kicking. Use {guild} and {days} as placeholders."""
        if message is None:
            await self.config.guild(ctx.guild).dm_message.set(DEFAULT_DM_MESSAGE)
            await ctx.send("DM message reset to default.")
            return
        await self.config.guild(ctx.guild).dm_message.set(message)
        await ctx.send("DM message updated.")

    @autokick.command(name="status")
    async def autokick_status(self, ctx: commands.Context):
        """Show the current auto-kick configuration for this server."""
        settings = await self.config.guild(ctx.guild).all()
        roles = [ctx.guild.get_role(rid) for rid in settings["role_ids"]]
        roles = [r for r in roles if r is not None]
        log_channel = ctx.guild.get_channel(settings["log_channel_id"]) if settings["log_channel_id"] else None

        embed = discord.Embed(title="AutoKick Settings", color=await ctx.embed_color())
        embed.add_field(name="Enabled", value=str(settings["toggle"]))
        embed.add_field(name="Verified roles", value=", ".join(r.mention for r in roles) if roles else "Not set")
        embed.add_field(name="Days before kick", value=str(settings["days"]))
        embed.add_field(name="Log channel", value=log_channel.mention if log_channel else "Not set")
        embed.add_field(name="DM before kick", value=str(settings["dm_enabled"]))
        await ctx.send(embed=embed)

    @autokick.command(name="checkuser")
    async def autokick_checkuser(self, ctx: commands.Context, member: discord.Member):
        """Debug: show what AutoKick sees for a specific member."""
        settings = await self.config.guild(ctx.guild).all()
        roles = [ctx.guild.get_role(rid) for rid in settings["role_ids"]]
        roles = [r for r in roles if r is not None]

        # Fetch fresh from the API to rule out cache issues
        try:
            fresh = await ctx.guild.fetch_member(member.id)
        except discord.NotFound:
            await ctx.send("This member doesn't appear to be in the server according to the API.")
            return

        has_role = any(r in fresh.roles for r in roles) if roles else None
        joined_str = discord.utils.format_dt(fresh.joined_at, "F") if fresh.joined_at else "Unknown"
        days_in = (discord.utils.utcnow() - fresh.joined_at).days if fresh.joined_at else "N/A"

        embed = discord.Embed(title=f"AutoKick check: {fresh}", color=await ctx.embed_color())
        embed.add_field(name="Joined at", value=joined_str, inline=False)
        embed.add_field(name="Days since joining", value=str(days_in))
        embed.add_field(name="Has a verified role?", value=str(has_role))
        embed.add_field(name="Would be kicked next run?", value=str(
            has_role is False and isinstance(days_in, int) and days_in >= settings["days"]
        ))
        await ctx.send(embed=embed)

    @autokick.command(name="checknow")
    async def autokick_checknow(self, ctx: commands.Context):
        """Manually run a check immediately for this server (does not wait for the loop)."""
        async with ctx.typing():
            await self._check_guild(ctx.guild)
        await ctx.send("Check complete. See the log channel (if set) for any kicks that happened.")
