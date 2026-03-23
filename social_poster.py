"""
ToyRadar — Social Posting Pipeline

social_poster.py

Reads today's social calendar from Supabase and schedules
all posts automatically via Buffer.

Buffer is the scheduling layer — it handles:

- Optimal posting times per platform
- Post queuing and rate limiting
- Analytics on what performs best
- One dashboard to manage all accounts

Supported platforms:

- X / Twitter
- Instagram
- Facebook Page
- TikTok (caption + hook — video creation is manual for now)

Setup:
pip install requests supabase python-dotenv

Env vars (.env):
BUFFER_ACCESS_TOKEN    ← from buffer.com/developers
BUFFER_TWITTER_ID      ← your Buffer channel ID for X/Twitter
BUFFER_INSTAGRAM_ID    ← your Buffer channel ID for Instagram
BUFFER_FACEBOOK_ID     ← your Buffer channel ID for Facebook
SUPABASE_URL
SUPABASE_KEY

How to get Buffer channel IDs:
curl https://api.bufferapp.com/1/profiles.json \
  ?access_token=YOUR_TOKEN
IDs are in the "id" field of each profile.

Run order (cron):

1. collectors.py    — every 30 min
2. toy_scoring.py   — after each collection
3. synthesizer.py   — 8am and 8pm (generates calendar)
4. social_poster.py — 8:30am (schedules today's posts to Buffer)
"""

import os
import json
import logging
import requests
from datetime import datetime, date, timedelta
from typing import Optional

from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("toyradar.social_poster")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

BUFFER_ACCESS_TOKEN = os.getenv("BUFFER_ACCESS_TOKEN")
BUFFER_TWITTER_ID   = os.getenv("BUFFER_TWITTER_ID")
BUFFER_INSTAGRAM_ID = os.getenv("BUFFER_INSTAGRAM_ID")
BUFFER_FACEBOOK_ID  = os.getenv("BUFFER_FACEBOOK_ID")
SUPABASE_URL        = os.getenv("SUPABASE_URL")
SUPABASE_KEY        = os.getenv("SUPABASE_KEY")

BUFFER_API_BASE     = "https://api.bufferapp.com/1"

# Map platform names → Buffer channel IDs
PLATFORM_IDS = {
    "twitter":   BUFFER_TWITTER_ID,
    "instagram": BUFFER_INSTAGRAM_ID,
    "facebook":  BUFFER_FACEBOOK_ID,
}

# Posting window — don't schedule outside these hours
POST_START_HOUR = 7    # 7am
POST_END_HOUR   = 21   # 9pm

# ─────────────────────────────────────────────
# BUFFER API
# ─────────────────────────────────────────────

class BufferClient:
    """
    Thin wrapper around Buffer's v1 API.
    Handles post scheduling and error logging.
    """

    def __init__(self):
        self.token = BUFFER_ACCESS_TOKEN
        if not self.token:
            log.warning("No BUFFER_ACCESS_TOKEN — posts will be logged but not sent")

    def schedule_post(
        self,
        platform: str,
        text: str,
        scheduled_at: Optional[datetime] = None,
    ) -> bool:
        """
        Schedule a post to Buffer.
        Returns True on success, False on failure.

        platform     — "twitter" | "instagram" | "facebook"
        text         — post content (platform rules already applied by Claude)
        scheduled_at — datetime to post (None = add to queue)
        """
        channel_id = PLATFORM_IDS.get(platform)
        if not channel_id:
            log.warning(f"No Buffer channel ID for {platform} — skipping")
            return False

        if not self.token:
            log.info(f"  [DRY RUN] Would post to {platform}: {text[:80]}...")
            return True

        payload = {
            "profile_ids[]": channel_id,
            "text":          text,
            "access_token":  self.token,
        }

        if scheduled_at:
            payload["scheduled_at"] = scheduled_at.strftime("%Y-%m-%dT%H:%M:%S")
            payload["now"] = "false"
        else:
            payload["now"] = "false"   # add to queue

        try:
            resp = requests.post(
                f"{BUFFER_API_BASE}/updates/create.json",
                data=payload,
                timeout=15,
            )
            resp.raise_for_status()
            result = resp.json()

            if result.get("success"):
                log.info(f"  ✓ Scheduled to {platform}: {text[:60]}...")
                return True
            else:
                log.error(f"  Buffer API error: {result.get('message', 'unknown')}")
                return False

        except requests.RequestException as e:
            log.error(f"  Buffer request failed: {e}")
            return False

    def verify_connection(self) -> bool:
        """Quick connectivity check."""
        if not self.token:
            return False
        try:
            resp = requests.get(
                f"{BUFFER_API_BASE}/user.json",
                params={"access_token": self.token},
                timeout=10,
            )
            data = resp.json()
            log.info(f"Buffer connected as: {data.get('name', 'unknown')}")
            return True
        except Exception as e:
            log.error(f"Buffer connection failed: {e}")
            return False

# ─────────────────────────────────────────────
# POSTING PIPELINE
# ─────────────────────────────────────────────

class SocialPoster:
    """
    Reads today's calendar from Supabase.
    Schedules each post to Buffer.
    Logs everything.

    Usage:
        poster = SocialPoster()
        poster.run()
    """

    def __init__(self):
        self.buffer = BufferClient()
        self.db     = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

    def run(self):
        log.info("=" * 55)
        log.info("  ToyRadar Social Posting Run")
        log.info(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        log.info("=" * 55)

        # Verify Buffer is connected
        self.buffer.verify_connection()

        # Load today's calendar
        calendar = self._load_todays_calendar()
        if not calendar:
            log.warning("No calendar found for today — run synthesizer.py first")
            return

        schedule = calendar.get("schedule", [])
        log.info(f"\nTop story: {calendar.get('top_story', 'N/A')}")
        log.info(f"Strategy:  {calendar.get('editors_note', 'N/A')}")
        log.info(f"Posts to schedule: {len(schedule)}\n")

        # Schedule each post
        posted  = 0
        skipped = 0

        for item in schedule:
            platform     = item.get("platform", "").lower()
            content      = item.get("content", "")
            time_str     = item.get("time", "")
            toy_id       = item.get("toy_id", "")
            reason       = item.get("reason", "")

            if not content or not platform:
                skipped += 1
                continue

            # Parse scheduled time
            scheduled_at = self._parse_time(time_str)

            # Skip if outside posting window
            if scheduled_at and not self._in_posting_window(scheduled_at):
                log.info(f"  Skipping {platform} post at {time_str} — outside window")
                skipped += 1
                continue

            log.info(f"\n── {time_str} → {platform.upper()} [{toy_id}]")
            log.info(f"   {reason}")

            success = self.buffer.schedule_post(
                platform     = platform,
                text         = content,
                scheduled_at = scheduled_at,
            )

            if success:
                posted += 1
                self._log_post(toy_id, platform, content, scheduled_at)
            else:
                skipped += 1

        log.info(f"\n{'='*55}")
        log.info(f"  ✅ Done — {posted} scheduled, {skipped} skipped")
        log.info(f"{'='*55}\n")

    def _load_todays_calendar(self) -> Optional[dict]:
        """Load today's social calendar from Supabase."""
        if not self.db:
            log.warning("No DB — using sample calendar")
            return _sample_calendar()

        try:
            resp = (
                self.db.table("social_calendars")
                    .select("*")
                    .eq("date", date.today().isoformat())
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
            )
            if not resp.data:
                return None
            row = resp.data[0]
            return {
                "schedule":     json.loads(row.get("schedule", "[]")),
                "top_story":    row.get("top_story"),
                "editors_note": row.get("editors_note"),
            }
        except Exception as e:
            log.error(f"Calendar load error: {e}")
            return None

    def _parse_time(self, time_str: str) -> Optional[datetime]:
        """
        Parse "8:00 AM" style time into today's datetime.
        Returns None if parsing fails.
        """
        try:
            today = date.today()
            t     = datetime.strptime(time_str.strip(), "%I:%M %p")
            return datetime(
                today.year, today.month, today.day,
                t.hour, t.minute, 0
            )
        except ValueError:
            log.warning(f"Could not parse time: {time_str}")
            return None

    def _in_posting_window(self, dt: datetime) -> bool:
        """Only post between 7am and 9pm."""
        return POST_START_HOUR <= dt.hour < POST_END_HOUR

    def _log_post(
        self,
        toy_id: str,
        platform: str,
        content: str,
        scheduled_at: Optional[datetime],
    ):
        """Log every scheduled post to Supabase for analytics."""
        if not self.db:
            return
        try:
            self.db.table("social_post_log").insert({
                "toy_id":       toy_id,
                "platform":     platform,
                "content":      content,
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                "posted_at":    datetime.utcnow().isoformat(),
                "date":         date.today().isoformat(),
            }).execute()
        except Exception as e:
            log.error(f"Post log error: {e}")

# ─────────────────────────────────────────────
# SUPABASE SCHEMA ADDITION
# ─────────────────────────────────────────────

POST_LOG_SCHEMA = """
CREATE TABLE IF NOT EXISTS social_post_log (
    id            BIGSERIAL PRIMARY KEY,
    toy_id        TEXT,
    platform      TEXT,
    content       TEXT,
    scheduled_at  TIMESTAMPTZ,
    posted_at     TIMESTAMPTZ DEFAULT NOW(),
    date          DATE,
    clicks        INTEGER DEFAULT 0,
    impressions   INTEGER DEFAULT 0
);
"""

# ─────────────────────────────────────────────
# SAMPLE CALENDAR (used when no DB)
# ─────────────────────────────────────────────

def _sample_calendar() -> dict:
    return {
        "top_story":    "NeeDoh Sugar Skull Cool Cats",
        "editors_note": "Lead with the $7 vs $95 eBay story — it's the most shareable data point today.",
        "schedule": [
            {
                "time":     "7:00 AM",
                "platform": "twitter",
                "toy_id":   "needoh-sugar-skull-cats",
                "content":  "💸 This toy costs $7 at Target. It's selling for $95 on eBay right now. NeeDoh Sugar Skull Cool Cats are about to sell out everywhere. radar.toys",
                "reason":   "Most shocking data point — leads the day"
            },
            {
                "time":     "9:30 AM",
                "platform": "facebook",
                "toy_id":   "needoh-nice-cube",
                "content":  "Tired of missing the hot toy your kid is asking for? 😅 NeeDoh Nice Cube is selling out at Target and Five Below nationwide right now. We track this stuff in real time so you never miss it again. Check radar.toys — it's free.",
                "reason":   "Parent-friendly story for morning Facebook scroll"
            },
            {
                "time":     "12:00 PM",
                "platform": "twitter",
                "toy_id":   "jellycat-lazulia-dragon",
                "content":  "🐉✨ Jellycat Lazulia Dragon just dropped for Spring 2026. Previous seasonal Jellycats sold out months early. Stock moving fast at Nordstrom + Jellycat.com. radar.toys #Jellycat #ToyAlert",
                "reason":   "Midday engagement — Jellycat audience is highly active on Twitter"
            },
            {
                "time":     "2:00 PM",
                "platform": "instagram",
                "toy_id":   "needoh-sugar-skull-cats",
                "content":  "The toy that costs $7 at Target is selling for $95 on eBay. 😳 NeeDoh Sugar Skull Cool Cats are the next big thing and you can still get them at retail — for now. Swipe to see where to find them.\n\n#NeeDoh #ToyTrends #KidsToys #ToyAlert #Squishy #RadarToys #TrendingToys #MustHaveToys #ParentingTips #ToyHunt",
                "reason":   "Visual story + strong hashtags for afternoon Instagram traffic"
            },
            {
                "time":     "5:00 PM",
                "platform": "twitter",
                "toy_id":   "needoh-nice-cube",
                "content":  "🚨 STOCK ALERT: NeeDoh Nice Cube down to critical levels nationwide. Search volume up 840% this week. If your kid wants one — move fast. radar.toys",
                "reason":   "Evening urgency post — parents checking phones after work"
            },
            {
                "time":     "7:00 PM",
                "platform": "twitter",
                "toy_id":   "needoh-sugar-skull-cats",
                "content":  "👀 Our model says NeeDoh Sugar Skull Cool Cats break out in 2-3 weeks. eBay resale already at $95. Still $7 at retail right now. radar.toys #ToysUnderTheRadar",
                "reason":   "Evening prediction post — drives curiosity and site visits"
            },
        ]
    }

# ─────────────────────────────────────────────
# CRON SCHEDULE
# ─────────────────────────────────────────────

CRON_SCHEDULE = """
# ToyRadar — Social Posting Pipeline
# Runs at 8:30am daily — after synthesizer generates the calendar at 8am
30 8 * * *  cd /path/to/toyradar && python social_poster.py >> logs/social_poster.log 2>&1
"""

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    poster = SocialPoster()
    poster.run()
