"""Schedule creation command."""
import logging
import discord
from discord import app_commands
from discord.ext import commands
from commands.common import parse_local, repeat_details, ConfirmSchedule, confirmation_embed

log=logging.getLogger(__name__)

class ScheduleCommands(commands.Cog):
    def __init__(self,bot): self.bot=bot

    @app_commands.command(name="schedule",description="Schedule a private message to selected server members")
    @app_commands.describe(recipient1="Required selected recipient",message="Message to send privately",when="Local date/time: YYYY-MM-DD HH:MM",repeat="Recurrence",interval="Custom recurrence count",unit="Custom recurrence unit",ends_at="Optional end date/time in your timezone",max_occurrences="Optional maximum sends")
    @app_commands.choices(repeat=[app_commands.Choice(name=n,value=v) for n,v in [("None","none"),("Every day","daily"),("Every week","weekly"),("Every 2 weeks","biweekly"),("Every month","monthly"),("Custom interval","custom")]],unit=[app_commands.Choice(name=x.title(),value=x) for x in ["minutes","hours","days","weeks"]])
    async def schedule(self, interaction: discord.Interaction, recipient1: discord.Member, message: str, when: str, recipient2: discord.Member|None=None, recipient3: discord.Member|None=None, recipient4: discord.Member|None=None, recipient5: discord.Member|None=None, repeat: str="none", interval: int|None=None, unit: str|None=None, ends_at: str|None=None, max_occurrences: app_commands.Range[int,1,10000]|None=None):
        if interaction.guild is None: return await interaction.response.send_message("Use this command in a server.",ephemeral=True)
        try:
            tz=await self.bot.database.timezone_for(interaction.user.id,interaction.guild_id,self.bot.config.default_timezone)
            first=parse_local(when,tz); end=parse_local(ends_at,tz) if ends_at else None
            count,unit_value=repeat_details(repeat,interval,unit)
            if repeat=="none" and (end or max_occurrences): raise ValueError("End conditions are only available for repeating schedules.")
            if repeat!="none" and end and end<=first: raise ValueError("The end date must be after the first send.")
            recipients=[]
            for member in [recipient1,recipient2,recipient3,recipient4,recipient5]:
                if member and member.id not in recipients: recipients.append(member.id)
            if len(recipients)>20: raise ValueError("Choose no more than 20 recipients per schedule.")
            if not message.strip() or len(message)>2000: raise ValueError("Message must contain 1 to 2,000 characters.")
            data={"message":message,"when":first,"recipients":recipients,"repeat":repeat,"interval":count,"unit":unit_value,"end":end,"maximum":max_occurrences,"tz":tz}
            members=[m for m in [recipient1,recipient2,recipient3,recipient4,recipient5] if m and m.id in recipients]
            embed=confirmation_embed(data,members)
            if tz=="UTC": embed.set_footer(text="Timezone is UTC. Set your local timezone with /settings.")
            await interaction.response.send_message(embed=embed,view=ConfirmSchedule(self.bot.database,interaction.user.id,interaction.guild_id,data),ephemeral=True)
        except ValueError as exc: await interaction.response.send_message(f"❌ {exc}",ephemeral=True)

async def setup(bot): await bot.add_cog(ScheduleCommands(bot))
