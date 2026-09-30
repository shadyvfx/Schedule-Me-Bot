"""Privately relay replies and reactions on scheduled DMs to their creator."""
import logging
import discord
from discord.ext import commands

log=logging.getLogger(__name__)

class ResponseReports(commands.Cog):
    def __init__(self,bot): self.bot=bot

    async def _report(self,context: dict, recipient_id: int, text: str):
        if context["recipient_id"] != recipient_id: return
        try:
            recipient=self.bot.get_user(recipient_id) or await self.bot.fetch_user(recipient_id)
            creator=self.bot.get_user(context["creator_id"]) or await self.bot.fetch_user(context["creator_id"])
            label=discord.utils.escape_markdown(recipient.display_name)
            await creator.send(f"**{label}** (schedule #{context['scheduled_message_id']}): {text[:1850]}",
                               allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            log.warning("Could not deliver private response report for schedule %s",context["scheduled_message_id"])
        except Exception:
            log.exception("Unexpected error while sending private response report")

    @commands.Cog.listener()
    async def on_message(self,message: discord.Message):
        # Only follow explicit Discord replies to a bot DM; ordinary unsolicited DMs
        # are not associated with a schedule and are ignored.
        if message.guild is not None or message.author.bot or message.reference is None:
            return
        original_id=message.reference.message_id
        if original_id is None: return
        context=await self.bot.database.delivery_context(original_id)
        if context:
            content=message.content.strip() or "(no text; recipient sent an attachment or another non-text response)"
            await self._report(context,message.author.id,content)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self,payload: discord.RawReactionActionEvent):
        if payload.guild_id is not None or payload.user_id==self.bot.user.id:
            return
        context=await self.bot.database.delivery_context(payload.message_id)
        if not context: return
        emoji=f":{payload.emoji.name}:" if payload.emoji.is_custom_emoji() else str(payload.emoji)
        await self._report(context,payload.user_id,f"reacted with {emoji}")

async def setup(bot): await bot.add_cog(ResponseReports(bot))
