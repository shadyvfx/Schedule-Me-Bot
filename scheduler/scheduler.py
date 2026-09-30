"""Database-backed due-job polling and private DM delivery."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from calendar import monthrange
from zoneinfo import ZoneInfo
import aiosqlite
from database.database import Database, iso, utc_now

log=logging.getLogger(__name__)

def next_occurrence(previous: datetime, repeat_type: str, interval: int | None,
                    unit: str | None, tz_name: str) -> datetime | None:
    """Return the next local-calendar recurrence, preserving wall time across DST."""
    if repeat_type == "none": return None
    local=previous.astimezone(ZoneInfo(tz_name))
    count=interval or {"daily":1,"weekly":1,"biweekly":2,"monthly":1}.get(repeat_type,1)
    selected_unit=unit or {"daily":"days","weekly":"weeks","biweekly":"weeks","monthly":"months"}.get(repeat_type,"days")
    naive=local.replace(tzinfo=None)
    if selected_unit in ("minutes","hours","days","weeks"):
        delta={"minutes":timedelta(minutes=count),"hours":timedelta(hours=count),"days":timedelta(days=count),"weeks":timedelta(weeks=count)}[selected_unit]
        naive+=delta
    elif selected_unit=="months":
        month_index=naive.year*12+naive.month-1+count
        year,month=divmod(month_index,12); month+=1
        naive=naive.replace(year=year,month=month,day=min(naive.day,monthrange(year,month)[1]))
    else: raise ValueError("Unsupported repeat unit")
    return naive.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)

class Scheduler:
    def __init__(self, database: Database, client, poll_seconds: int=15):
        self.database=database; self.client=client; self.poll_seconds=poll_seconds; self.task=None; self.stopping=False

    async def start(self):
        async with self.database.connect() as db:
            await db.execute("UPDATE scheduled_messages SET status='scheduled',claimed_at=NULL WHERE status='processing' AND claimed_at<?",(iso(utc_now()-timedelta(minutes=10)),)); await db.commit()
        self.task=asyncio.create_task(self._run(),name="send-later-scheduler")

    async def close(self):
        self.stopping=True
        if self.task:
            self.task.cancel()
            try: await self.task
            except asyncio.CancelledError: pass

    async def _run(self):
        while not self.stopping:
            try: await self.process_due()
            except asyncio.CancelledError: raise
            except Exception: log.exception("Scheduler polling failed")
            await asyncio.sleep(self.poll_seconds)

    async def process_due(self):
        async with self.database.connect() as db:
            # Recover a process that died during delivery even when this process stayed alive.
            await db.execute("UPDATE scheduled_messages SET status='scheduled',claimed_at=NULL WHERE status='processing' AND claimed_at<?",(iso(utc_now()-timedelta(minutes=10)),))
            rows=await (await db.execute("SELECT id FROM scheduled_messages WHERE status='scheduled' AND next_send_at<=? ORDER BY next_send_at LIMIT 20",(iso(utc_now()),))).fetchall()
            await db.commit()
        for row in rows:
            if await self._claim(row[0]): await self._deliver(row[0])

    async def _claim(self, sid: int) -> bool:
        async with self.database.connect() as db:
            cur=await db.execute("UPDATE scheduled_messages SET status='processing',claimed_at=? WHERE id=? AND status='scheduled' AND next_send_at<=?",(iso(utc_now()),sid,iso(utc_now()))); await db.commit(); return cur.rowcount==1

    async def _deliver(self, sid: int):
        async with self.database.connect() as db:
            row=await (await db.execute("SELECT * FROM scheduled_messages WHERE id=? AND status='processing'",(sid,))).fetchone()
            recipients=await (await db.execute("SELECT recipient_id FROM scheduled_recipients WHERE scheduled_message_id=?",(sid,))).fetchall()
        if not row: return
        when=utc_now()
        for recipient in recipients:
            uid=recipient[0]; outcome="sent"; error=None
            try:
                guild=self.client.get_guild(row["guild_id"]) or await self.client.fetch_guild(row["guild_id"])
                member=guild.get_member(uid) or await guild.fetch_member(uid)
                sent_message=await member.send(row["message"])
                try:
                    await self.database.record_delivery_message(sent_message.id,sid,row["creator_id"],uid,row["guild_id"],when)
                except Exception:
                    log.exception("Could not save reply tracking data for schedule %s",sid)
                log.info("Scheduled message %s delivered to recipient %s",sid,uid)
            except Exception as exc:
                outcome="failed"; error=type(exc).__name__
                log.warning("Scheduled message %s failed for recipient %s (%s)",sid,uid,error)
            async with self.database.connect() as db:
                await db.execute("UPDATE scheduled_recipients SET status=?,last_sent_at=?,last_error=? WHERE scheduled_message_id=? AND recipient_id=?",(outcome,iso(when),error,sid,uid))
                await db.execute("INSERT INTO delivery_history(scheduled_message_id,recipient_id,sent_at,status,error) VALUES(?,?,?,?,?)",(sid,uid,iso(when),outcome,error)); await db.commit()
            await asyncio.sleep(0.75)
        sent=int(row["occurrences_sent"])+1
        nxt=next_occurrence(datetime.fromisoformat(row["next_send_at"]),row["repeat_type"],row["repeat_interval"],row["repeat_unit"],row["timezone"])
        end=datetime.fromisoformat(row["repeat_end_at"]) if row["repeat_end_at"] else None
        done=(nxt is None or (end is not None and nxt>end) or (row["max_occurrences"] is not None and sent>=row["max_occurrences"]))
        if done: nxt=None
        async with self.database.connect() as db:
            await db.execute("UPDATE scheduled_messages SET occurrences_sent=?,next_send_at=?,status=?,claimed_at=NULL,updated_at=? WHERE id=? AND status='processing'",(sent,iso(nxt) if nxt else None,"completed" if done else "scheduled",iso(utc_now()),sid))
            if not done: await db.execute("UPDATE scheduled_recipients SET status='pending',last_error=NULL WHERE scheduled_message_id=?",(sid,))
            await db.commit()
