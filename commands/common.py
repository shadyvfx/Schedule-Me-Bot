"""Shared schedule input parsing and private confirmation UI."""
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import discord
from discord.ui import View, Button
from database.database import Database
from scheduler.scheduler import next_occurrence

log=logging.getLogger(__name__)

def parse_local(value: str, tz_name: str) -> datetime:
    """Parse YYYY-MM-DD HH:MM in the user's configured timezone."""
    try: local=datetime.strptime(value.strip(),"%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(tz_name))
    except ValueError as exc: raise ValueError("Use YYYY-MM-DD HH:MM (24-hour time), in your configured timezone.") from exc
    result=local.astimezone(timezone.utc)
    if result <= datetime.now(timezone.utc): raise ValueError("Please choose a time in the future.")
    return result

def repeat_details(kind: str, amount: int | None, unit: str | None):
    if kind=="custom":
        if not amount or amount<1: raise ValueError("The repeat interval must be greater than 0.")
        if unit not in {"minutes","hours","days","weeks"}: raise ValueError("Choose minutes, hours, days, or weeks for a custom interval.")
        return amount,unit
    return {"daily":(1,"days"),"weekly":(1,"weeks"),"biweekly":(2,"weeks"),"monthly":(1,"months")}.get(kind,(None,None))

def repeat_label(kind, amount=None, unit=None):
    return {"none":"None","daily":"Every day","weekly":"Every week","biweekly":"Every 2 weeks","monthly":"Every month","custom":f"Every {amount} {unit}"}.get(kind,kind)

class ConfirmSchedule(View):
    def __init__(self, db: Database, owner: int, guild_id: int, data: dict):
        super().__init__(timeout=180); self.db=db; self.owner=owner; self.guild_id=guild_id; self.data=data

    async def interaction_check(self, interaction):
        if interaction.user.id!=self.owner:
            await interaction.response.send_message("This confirmation belongs to another user.",ephemeral=True); return False
        return True

    @discord.ui.button(label="Confirm",style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        d=self.data
        sid=await self.db.create_schedule(creator_id=self.owner,guild_id=self.guild_id,message=d["message"],first_send_at=d["when"],recipients=d["recipients"],repeat_type=d["repeat"],repeat_interval=d["interval"],repeat_unit=d["unit"],repeat_end_at=d["end"],max_occurrences=d["maximum"],tz=d["tz"])
        log.info("Schedule %s created by user %s for %d explicit recipients",sid,self.owner,len(d["recipients"]))
        await interaction.response.edit_message(content=f"✅ Schedule **#{sid}** saved. It will be sent privately to the selected recipients.",embed=None,view=None)

    @discord.ui.button(label="Cancel",style=discord.ButtonStyle.secondary)
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        await interaction.response.edit_message(content="Schedule creation cancelled.",embed=None,view=None)

def confirmation_embed(data: dict, members: list[discord.Member]):
    embed=discord.Embed(title="📨 Scheduled Message",description=data["message"],color=discord.Color.blurple())
    embed.add_field(name="Recipients",value="\n".join(discord.utils.escape_markdown(m.display_name) for m in members),inline=False)
    embed.add_field(name="First send",value=data["when"].astimezone(ZoneInfo(data["tz"])).strftime("%B %d, %Y at %I:%M %p")+f" ({data['tz']})",inline=False)
    embed.add_field(name="Repeat",value=repeat_label(data["repeat"],data["interval"],data["unit"]),inline=True)
    end=data["end"].astimezone(ZoneInfo(data["tz"])).strftime("%b %d, %Y %I:%M %p") if data["end"] else (f"After {data['maximum']} occurrences" if data["maximum"] else "Never")
    embed.add_field(name="Ends",value=end,inline=True)
    return embed
