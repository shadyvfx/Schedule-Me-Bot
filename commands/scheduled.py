"""List a user's own pending schedules, privately."""
from datetime import datetime
from zoneinfo import ZoneInfo
import discord
from discord import app_commands
from discord.ext import commands

class ScheduledCommands(commands.Cog):
    def __init__(self,bot): self.bot=bot
    @app_commands.command(name="scheduled",description="Show your scheduled private messages")
    async def scheduled(self,interaction: discord.Interaction):
        if not interaction.guild_id: return await interaction.response.send_message("Use this command in a server.",ephemeral=True)
        rows=await self.bot.database.list_owned(interaction.user.id,interaction.guild_id)
        if not rows: return await interaction.response.send_message("You have no active scheduled messages.",ephemeral=True)
        blocks=[]
        for row in rows:
            local=datetime.fromisoformat(row["next_send_at"]).astimezone(ZoneInfo(row["timezone"]))
            recipients=", ".join(f"<@{uid}>" for uid in row["recipients"])
            kind=row["repeat_type"]
            repeat={"none":"None","daily":"Every day","weekly":"Every week","biweekly":"Every 2 weeks","monthly":"Every month","custom":f"Every {row['repeat_interval']} {row['repeat_unit']}"}.get(kind,kind)
            blocks.append(f"**#{row['id']}** · To: {recipients}\n{discord.utils.escape_markdown(row['message'][:250])}\nNext: {local:%b %d, %Y %I:%M %p} ({row['timezone']}) · {repeat}")
        text="\n\n".join(blocks)
        await interaction.response.send_message(text[:1950],ephemeral=True,view=ScheduleListView(self.bot,interaction.user.id,interaction.guild_id,rows))

class ScheduleListView(discord.ui.View):
    def __init__(self,bot,owner,guild_id,rows):
        super().__init__(timeout=300); self.bot=bot; self.owner=owner; self.guild_id=guild_id; self.rows=rows
        for row in rows[:10]:
            self.add_item(ScheduleAction(bot,owner,guild_id,row["id"],"Edit"))
            self.add_item(ScheduleAction(bot,owner,guild_id,row["id"],"Cancel"))
    async def interaction_check(self,interaction):
        if interaction.user.id!=self.owner:
            await interaction.response.send_message("This list belongs to another user.",ephemeral=True); return False
        return True

class ScheduleAction(discord.ui.Button):
    def __init__(self,bot,owner,guild_id,sid,action):
        super().__init__(label=f"{action} #{sid}",style=discord.ButtonStyle.primary if action=="Edit" else discord.ButtonStyle.danger,row=(sid-1)%5)
        self.bot=bot; self.owner=owner; self.guild_id=guild_id; self.sid=sid; self.action=action
    async def callback(self,interaction):
        if interaction.user.id!=self.owner: return await interaction.response.send_message("This list belongs to another user.",ephemeral=True)
        if self.action=="Cancel":
            ok=await self.bot.database.cancel(self.sid,self.owner,self.guild_id)
            return await interaction.response.send_message("Schedule cancelled." if ok else "❌ That scheduled message no longer exists.",ephemeral=True)
        await interaction.response.send_message(f"To edit this schedule, run **/edit id:{self.sid}**. The command lets you replace its message, recipients, date, and recurrence.",ephemeral=True)

async def setup(bot): await bot.add_cog(ScheduledCommands(bot))
