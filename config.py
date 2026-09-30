"""Environment based application configuration."""
from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Config:
    token: str
    database_path: str
    default_timezone: str
    scheduler_poll_seconds: int

def load_config() -> Config:
    token = os.getenv("DISCORD_TOKEN", "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN is required. Copy .env.example to .env and set it.")
    return Config(token, os.getenv("DATABASE_PATH", "./data/bot.db"),
                  os.getenv("DEFAULT_TIMEZONE", "EST"),
                  max(1, int(os.getenv("SCHEDULER_POLL_SECONDS", "15"))))
