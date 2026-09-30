"""Ownership-checked schedule cancellation command."""
import discord
from discord import app_commands
from discord.ext import commands

class CancelCommands(commands.Cog):
    def __init__(self,bot): self.bot=bot
    @app_commands.command(name="cancel",description="Cancel one of your scheduled messages")
    async def cancel(self,interaction: discord.Interaction, schedule_id: int):
        if not interaction.guild_id: return await interaction.response.send_message("Use this command in a server.",ephemeral=True)
        ok=await self.bot.database.cancel(schedule_id,interaction.user.id,interaction.guild_id)
        await interaction.response.send_message("Schedule cancelled." if ok else "❌ That scheduled message no longer exists or is not yours.",ephemeral=True)
async def setup(bot): await bot.add_cog(CancelCommands(bot))
