"""Small regression tests for recurrence math and database ownership."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from scheduler.scheduler import next_occurrence
from database.database import Database

class RecurrenceTests(unittest.TestCase):
    def test_weekly_preserves_time(self):
        initial=datetime(2026,10,2,13,0,tzinfo=timezone.utc)
        self.assertEqual(next_occurrence(initial,"weekly",1,"weeks","UTC"),datetime(2026,10,9,13,0,tzinfo=timezone.utc))
    def test_monthly_clamps_short_month(self):
        initial=datetime(2026,1,31,9,0,tzinfo=timezone.utc)
        self.assertEqual(next_occurrence(initial,"monthly",1,"months","UTC"),datetime(2026,2,28,9,0,tzinfo=timezone.utc))
    def test_timezone_dst_wall_time(self):
        initial=datetime(2026,3,7,14,0,tzinfo=timezone.utc) # 9 AM before DST
        nxt=next_occurrence(initial,"daily",1,"days","America/New_York")
        self.assertEqual(nxt,datetime(2026,3,8,13,0,tzinfo=timezone.utc))
    def test_one_time_has_no_next(self):
        self.assertIsNone(next_occurrence(datetime.now(timezone.utc),"none",None,None,"UTC"))

class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.db=Database(str(Path(self.temp.name)/"test.db")); await self.db.initialize()
    async def asyncTearDown(self): self.temp.cleanup()
    async def test_message_has_multiple_recipients_and_owner_scope(self):
        when=datetime(2030,1,1,tzinfo=timezone.utc)
        sid=await self.db.create_schedule(creator_id=1,guild_id=2,message="hello",first_send_at=when,recipients=[3,4,5])
        self.assertEqual((await self.db.get_owned(sid,1,2))["recipients"],[3,4,5])
        self.assertIsNone(await self.db.get_owned(sid,9,2))
    async def test_cancel_owner_only(self):
        when=datetime(2030,1,1,tzinfo=timezone.utc)
        sid=await self.db.create_schedule(creator_id=1,guild_id=2,message="hello",first_send_at=when,recipients=[3])
        self.assertFalse(await self.db.cancel(sid,8,2)); self.assertTrue(await self.db.cancel(sid,1,2))
    async def test_edit_replaces_recipients_and_resets_schedule(self):
        when=datetime(2030,1,1,tzinfo=timezone.utc)
        sid=await self.db.create_schedule(creator_id=1,guild_id=2,message="old",first_send_at=when,recipients=[3])
        ok=await self.db.edit(sid,1,2,message="new",first_send_at=datetime(2030,2,1,tzinfo=timezone.utc),recipients=[4,5],repeat_type="weekly",repeat_interval=1,repeat_unit="weeks",repeat_end_at=None,max_occurrences=3,tz="UTC")
        self.assertTrue(ok)
        row=await self.db.get_owned(sid,1,2)
        self.assertEqual(row["message"],"new"); self.assertEqual(row["recipients"],[4,5]); self.assertEqual(row["max_occurrences"],3)
    async def test_due_job_claim_is_exclusive(self):
        when=datetime(2020,1,1,tzinfo=timezone.utc)
        sid=await self.db.create_schedule(creator_id=1,guild_id=2,message="old",first_send_at=when,recipients=[3])
        class Client: pass
        scheduler=__import__("scheduler.scheduler",fromlist=["Scheduler"]).Scheduler(self.db,Client())
        self.assertTrue(await scheduler._claim(sid)); self.assertFalse(await scheduler._claim(sid))
    async def test_delivered_dm_can_be_mapped_to_creator_and_recipient(self):
        when=datetime(2030,1,1,tzinfo=timezone.utc)
        await self.db.record_delivery_message(765,12,1,3,2,when)
        self.assertEqual(await self.db.delivery_context(765),{"creator_id":1,"recipient_id":3,"scheduled_message_id":12})
        self.assertIsNone(await self.db.delivery_context(999))

if __name__=="__main__": unittest.main()
