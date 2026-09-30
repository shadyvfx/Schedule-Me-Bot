"""Per-user timezone settings."""
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import discord
from discord import app_commands
from discord.ext import commands

class SettingsCommands(commands.Cog):
    def __init__(self,bot): self.bot=bot
    @app_commands.command(name="settings",description="Set your timezone for schedules")
    @app_commands.describe(timezone="IANA timezone, such as America/New_York")
    async def settings(self,interaction: discord.Interaction,timezone: str):
        if not interaction.guild_id: return await interaction.response.send_message("Use this command in a server.",ephemeral=True)
        try: ZoneInfo(timezone)
        except (ZoneInfoNotFoundError,ValueError): return await interaction.response.send_message("❌ Use a valid IANA timezone such as America/New_York or Europe/London.",ephemeral=True)
        await self.bot.database.set_timezone(interaction.user.id,interaction.guild_id,timezone)
        await interaction.response.send_message(f"Timezone set to **{timezone}** for this server.",ephemeral=True)
async def setup(bot): await bot.add_cog(SettingsCommands(bot))
