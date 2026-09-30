"""Entry point for the private scheduled-message bot."""
import logging
import discord
from discord.ext import commands
from config import load_config
from database.database import Database
from scheduler.scheduler import Scheduler

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log=logging.getLogger(__name__)

class SendLaterBot(commands.Bot):
    def __init__(self,config):
        intents=discord.Intents.none(); intents.guilds=True; intents.members=True
        intents.dm_messages=True; intents.dm_reactions=True
        super().__init__(command_prefix=commands.when_mentioned, intents=intents)
        self.config=config; self.database=Database(config.database_path); self.scheduler=Scheduler(self.database,self,config.scheduler_poll_seconds)
    async def setup_hook(self):
        await self.database.initialize()
        for extension in ("commands.schedule","commands.scheduled","commands.cancel","commands.edit","commands.settings","commands.responses"):
            await self.load_extension(extension)
        await self.tree.sync()
        await self.scheduler.start()
        log.info("Slash commands synced; persistent scheduler started")
    async def close(self):
        log.info("Bot shutting down")
        await self.scheduler.close()
        await super().close()

def main():
    config=load_config()
    bot=SendLaterBot(config)
    bot.run(config.token,log_handler=None)

if __name__=="__main__": main()
