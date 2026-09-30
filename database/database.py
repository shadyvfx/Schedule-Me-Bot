"""SQLite persistence and ownership-aware schedule operations."""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import aiosqlite

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()

class Database:
    def __init__(self, path: str): self.path = path

    @asynccontextmanager
    async def connect(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            yield db

    async def initialize(self):
        async with self.connect() as db:
            await db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
              discord_user_id INTEGER NOT NULL, guild_id INTEGER NOT NULL,
              timezone TEXT NOT NULL DEFAULT 'UTC', created_at TEXT NOT NULL,
              PRIMARY KEY(discord_user_id,guild_id));
            CREATE TABLE IF NOT EXISTS scheduled_messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT, creator_id INTEGER NOT NULL,
              guild_id INTEGER NOT NULL, message TEXT NOT NULL,
              first_send_at TEXT NOT NULL, next_send_at TEXT,
              repeat_type TEXT NOT NULL DEFAULT 'none', repeat_interval INTEGER,
              repeat_unit TEXT, repeat_end_at TEXT, max_occurrences INTEGER,
              occurrences_sent INTEGER NOT NULL DEFAULT 0,
              status TEXT NOT NULL DEFAULT 'scheduled', created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL, timezone TEXT NOT NULL DEFAULT 'UTC',
              claimed_at TEXT);
            CREATE TABLE IF NOT EXISTS scheduled_recipients (
              id INTEGER PRIMARY KEY AUTOINCREMENT, scheduled_message_id INTEGER NOT NULL
                REFERENCES scheduled_messages(id) ON DELETE CASCADE,
              recipient_id INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
              last_sent_at TEXT, last_error TEXT,
              UNIQUE(scheduled_message_id,recipient_id));
            CREATE TABLE IF NOT EXISTS delivery_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT, scheduled_message_id INTEGER NOT NULL,
              recipient_id INTEGER NOT NULL, sent_at TEXT NOT NULL, status TEXT NOT NULL,
              error TEXT);
            CREATE TABLE IF NOT EXISTS delivery_messages (
              discord_message_id INTEGER PRIMARY KEY, scheduled_message_id INTEGER NOT NULL,
              creator_id INTEGER NOT NULL, recipient_id INTEGER NOT NULL,
              guild_id INTEGER NOT NULL, sent_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS due_schedules ON scheduled_messages(status,next_send_at);
            CREATE INDEX IF NOT EXISTS creator_schedules ON scheduled_messages(creator_id,guild_id,status);
            """)
            await db.commit()

    async def record_delivery_message(self, discord_message_id: int, schedule_id: int,
                                      creator_id: int, recipient_id: int, guild_id: int,
                                      sent_at: datetime):
        """Map a bot DM to its schedule so replies and reactions can be attributed."""
        async with self.connect() as db:
            await db.execute("INSERT OR IGNORE INTO delivery_messages VALUES(?,?,?,?,?,?)",
                             (discord_message_id,schedule_id,creator_id,recipient_id,guild_id,iso(sent_at)))
            await db.commit()

    async def delivery_context(self, discord_message_id: int):
        """Return the owner and recipient associated with one delivered DM."""
        async with self.connect() as db:
            row=await (await db.execute("SELECT creator_id,recipient_id,scheduled_message_id FROM delivery_messages WHERE discord_message_id=?",(discord_message_id,))).fetchone()
            return dict(row) if row else None

    async def timezone_for(self, user_id: int, guild_id: int, default: str) -> str:
        async with self.connect() as db:
            row = await (await db.execute("SELECT timezone FROM users WHERE discord_user_id=? AND guild_id=?", (user_id,guild_id))).fetchone()
            return row["timezone"] if row else default

    async def set_timezone(self, user_id: int, guild_id: int, tz: str):
        async with self.connect() as db:
            await db.execute("INSERT INTO users VALUES(?,?,?,?) ON CONFLICT(discord_user_id,guild_id) DO UPDATE SET timezone=excluded.timezone", (user_id,guild_id,tz,iso(utc_now())))
            await db.commit()

    async def create_schedule(self, *, creator_id, guild_id, message, first_send_at, recipients,
                              repeat_type="none", repeat_interval=None, repeat_unit=None,
                              repeat_end_at=None, max_occurrences=None, tz="UTC") -> int:
        now=iso(utc_now())
        async with self.connect() as db:
            cur=await db.execute("""INSERT INTO scheduled_messages
            (creator_id,guild_id,message,first_send_at,next_send_at,repeat_type,repeat_interval,repeat_unit,repeat_end_at,max_occurrences,status,created_at,updated_at,timezone)
            VALUES(?,?,?,?,?,?,?,?,?,?,'scheduled',?,?,?)""",
            (creator_id,guild_id,message,iso(first_send_at),iso(first_send_at),repeat_type,repeat_interval,repeat_unit,iso(repeat_end_at) if repeat_end_at else None,max_occurrences,now,now,tz))
            sid=cur.lastrowid
            await db.executemany("INSERT INTO scheduled_recipients(scheduled_message_id,recipient_id) VALUES(?,?)", [(sid,int(uid)) for uid in recipients])
            await db.commit()
            return sid

    async def get_owned(self, sid: int, creator_id: int, guild_id: int):
        async with self.connect() as db:
            row=await (await db.execute("SELECT * FROM scheduled_messages WHERE id=? AND creator_id=? AND guild_id=?",(sid,creator_id,guild_id))).fetchone()
            if row:
                row=dict(row); row["recipients"]=[r[0] for r in await (await db.execute("SELECT recipient_id FROM scheduled_recipients WHERE scheduled_message_id=?",(sid,))).fetchall()]
            return row

    async def list_owned(self, creator_id: int, guild_id: int):
        async with self.connect() as db:
            rows=await (await db.execute("SELECT * FROM scheduled_messages WHERE creator_id=? AND guild_id=? AND status IN ('scheduled','processing') ORDER BY next_send_at LIMIT 25",(creator_id,guild_id))).fetchall()
            output=[]
            for row in rows:
                item=dict(row); item["recipients"]=[r[0] for r in await (await db.execute("SELECT recipient_id FROM scheduled_recipients WHERE scheduled_message_id=?",(item["id"],))).fetchall()]; output.append(item)
            return output

    async def cancel(self, sid: int, creator_id: int, guild_id: int) -> bool:
        async with self.connect() as db:
            cur=await db.execute("UPDATE scheduled_messages SET status='cancelled',next_send_at=NULL,updated_at=? WHERE id=? AND creator_id=? AND guild_id=? AND status='scheduled'",(iso(utc_now()),sid,creator_id,guild_id)); await db.commit(); return cur.rowcount>0

    async def edit(self, sid: int, creator_id: int, guild_id: int, *, message, first_send_at, recipients,
                   repeat_type, repeat_interval, repeat_unit, repeat_end_at, max_occurrences, tz):
        async with self.connect() as db:
            cur=await db.execute("""UPDATE scheduled_messages SET message=?,first_send_at=?,next_send_at=?,repeat_type=?,repeat_interval=?,repeat_unit=?,repeat_end_at=?,max_occurrences=?,occurrences_sent=0,status='scheduled',timezone=?,updated_at=?,claimed_at=NULL WHERE id=? AND creator_id=? AND guild_id=? AND status IN ('scheduled','processing')""",
              (message,iso(first_send_at),iso(first_send_at),repeat_type,repeat_interval,repeat_unit,iso(repeat_end_at) if repeat_end_at else None,max_occurrences,tz,iso(utc_now()),sid,creator_id,guild_id))
            if cur.rowcount:
                await db.execute("DELETE FROM scheduled_recipients WHERE scheduled_message_id=?",(sid,))
                await db.executemany("INSERT INTO scheduled_recipients(scheduled_message_id,recipient_id) VALUES(?,?)",[(sid,int(uid)) for uid in recipients])
            await db.commit(); return cur.rowcount>0
