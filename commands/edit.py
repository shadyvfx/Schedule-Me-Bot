"""Ownership-checked schedule replacement command."""
import discord
from discord import app_commands
from discord.ext import commands
from commands.common import parse_local, repeat_details

class EditCommands(commands.Cog):
    def __init__(self,bot): self.bot=bot
    @app_commands.command(name="edit",description="Replace the details of one of your scheduled messages")
    @app_commands.describe(schedule_id="ID shown by /scheduled",recipient1="First explicit recipient",message="Replacement message",when="Local date/time: YYYY-MM-DD HH:MM",ends_at="Optional end date/time",max_occurrences="Optional maximum sends")
    @app_commands.choices(repeat=[app_commands.Choice(name=n,value=v) for n,v in [("None","none"),("Every day","daily"),("Every week","weekly"),("Every 2 weeks","biweekly"),("Every month","monthly"),("Custom interval","custom")]],unit=[app_commands.Choice(name=x.title(),value=x) for x in ["minutes","hours","days","weeks"]])
    async def edit(self,interaction: discord.Interaction,schedule_id: int,recipient1: discord.Member,message: str,when: str,recipient2: discord.Member|None=None,recipient3: discord.Member|None=None,recipient4: discord.Member|None=None,recipient5: discord.Member|None=None,repeat: str="none",interval: int|None=None,unit: str|None=None,ends_at: str|None=None,max_occurrences: app_commands.Range[int,1,10000]|None=None):
        if not interaction.guild_id: return await interaction.response.send_message("Use this command in a server.",ephemeral=True)
        old=await self.bot.database.get_owned(schedule_id,interaction.user.id,interaction.guild_id)
        if not old: return await interaction.response.send_message("❌ That scheduled message no longer exists or is not yours.",ephemeral=True)
        try:
            tz=await self.bot.database.timezone_for(interaction.user.id,interaction.guild_id,self.bot.config.default_timezone)
            first=parse_local(when,tz); end=parse_local(ends_at,tz) if ends_at else None; count,unit_value=repeat_details(repeat,interval,unit)
            if repeat=="none" and (end or max_occurrences): raise ValueError("End conditions are only available for repeating schedules.")
            if repeat!="none" and end and end<=first: raise ValueError("The end date must be after the first send.")
            if not message.strip() or len(message)>2000: raise ValueError("Message must contain 1 to 2,000 characters.")
            recipients=list(dict.fromkeys(m.id for m in [recipient1,recipient2,recipient3,recipient4,recipient5] if m))
            ok=await self.bot.database.edit(schedule_id,interaction.user.id,interaction.guild_id,message=message,first_send_at=first,recipients=recipients,repeat_type=repeat,repeat_interval=count,repeat_unit=unit_value,repeat_end_at=end,max_occurrences=max_occurrences,tz=tz)
            await interaction.response.send_message("✅ Schedule updated." if ok else "❌ That scheduled message no longer exists.",ephemeral=True)
        except ValueError as exc: await interaction.response.send_message(f"❌ {exc}",ephemeral=True)
async def setup(bot): await bot.add_cog(EditCommands(bot))
