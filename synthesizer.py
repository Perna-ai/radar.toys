"""
ToyRadar — Claude Synthesis Layer (with Social)

synthesizer.py

Reads heat scores + raw signals from Supabase, calls Claude Sonnet
to generate all content automatically:

1. ToyCard content       — punchy 2-sentence descriptions per toy
2. Prediction narratives — why a toy is about to break out
3. Alert emails          — personalized restock / trend alerts
4. Weekly digest         — human-readable trend report for subscribers
5. Anomaly flags         — catches weird data before it hits the site
6. Social content        — X/Twitter, TikTok, Instagram, Facebook (NEW)
7. Daily social calendar — ranked post schedule for the day (NEW)

Setup:
pip install anthropic supabase python-dotenv

Env vars (.env):
ANTHROPIC_API_KEY
SUPABASE_URL
SUPABASE_KEY
"""

import os
import json
import logging
from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass, field

import anthropic
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("toyradar.synthesizer")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
SUPABASE_URL      = os.getenv("SUPABASE_URL")
SUPABASE_KEY      = os.getenv("SUPABASE_KEY")

MODEL      = "claude-sonnet-4-20250514"
MAX_TOKENS = 1024

# Alert thresholds
ALERT_HEAT_THRESHOLD    = 75
ALERT_STOCK_THRESHOLD   = 20
RESALE_ALERT_MULTIPLIER = 2.5

# Social thresholds — only post about toys above these
SOCIAL_MIN_HEAT_SCORE  = 55     # don't post low-heat toys
SOCIAL_RESALE_MIN_MULT = 1.8    # resale must be 1.8x+ retail

# ─────────────────────────────────────────────
# DATA STRUCTURES
# ─────────────────────────────────────────────

@dataclass
class ScoredToy:
    toy_id:              str
    name:                str
    brand:               str
    retail_price:        float
    heat_score:          float
    status:              str
    stock_risk:          str
    resale_flag:         bool
    breakout_flag:       bool
    search_velocity:     Optional[float]
    search_acceleration: Optional[float]
    amz_stock_pct:       Optional[float]
    ebay_avg_sold_price: Optional[float]
    tiktok_views_7d:     Optional[float]
    youtube_views_7d:    Optional[float]
    reddit_mentions_7d:  Optional[float]
    retailers:           list = None
    age_range:           str  = ""
    category:            str  = ""

@dataclass
class SocialContent:
    """All social posts generated for one toy."""
    toy_id:            str
    name:              str
    twitter_post:      str = ""   # 280 chars, punchy + emoji
    twitter_hook:      str = ""   # alternate urgent angle
    tiktok_hook:       str = ""   # 15-word spoken video opener
    tiktok_caption:    str = ""   # video caption + hashtags
    instagram_caption: str = ""   # 2-3 sentences + hashtags
    facebook_post:     str = ""   # longer, parent-friendly
    ticker_hook:       str = ""   # ALL CAPS, 10 words for site ticker
    best_platform:     str = ""   # where this story fits best
    post_urgency:      str = ""   # "immediate" | "today" | "this week"
    generated_at:      str = ""

@dataclass
class SynthesisOutput:
    toy_id:               str
    name:                 str
    card_description:     str
    card_tag:             str
    parent_tip:           str
    prediction_narrative: Optional[str]          = None
    alert_subject:        Optional[str]          = None
    alert_body:           Optional[str]          = None
    anomaly_flag:         Optional[str]          = None
    social:               Optional[SocialContent] = None
    generated_at:         str                    = ""

# ─────────────────────────────────────────────
# PROMPT BUILDERS — SITE CONTENT
# ─────────────────────────────────────────────

def _build_card_prompt(toy: ScoredToy) -> str:
    social_views = (toy.tiktok_views_7d or 0) + (toy.youtube_views_7d or 0)
    resale_str   = (
        f"${toy.ebay_avg_sold_price:.2f} on eBay "
        f"({toy.ebay_avg_sold_price/toy.retail_price:.1f}x retail)"
        if toy.ebay_avg_sold_price else "no resale data"
    )
    return f"""You write copy for ToyRadar, a toy trend tracking website.
Audience: kids who want to know what's cool, and parents who need practical buying info.
Be punchy, specific, honest. Never invent facts. Only use the data provided.

TOY DATA:
Name: {toy.name} | Brand: {toy.brand} | Category: {toy.category}
Age: {toy.age_range} | Retail: ${toy.retail_price:.2f}
Heat score: {toy.heat_score:.1f}/100 | Status: {toy.status}
Stock risk: {toy.stock_risk} | Resale: {resale_str}
Search velocity: {toy.search_velocity or 'N/A'}/100
Social views 7d: {int(social_views):,} | Reddit: {int(toy.reddit_mentions_7d or 0)}
Where to buy: {', '.join(toy.retailers or [])}

Respond ONLY with JSON:
{{
  "card_description": "<2 punchy sentences. Lead with what makes it special. End with urgency. Max 35 words.>",
  "card_tag": "<ONE of: SOLD OUT RISK | LIMITED STOCK | WATCH NOW | GET AHEAD | TRENDING>",
  "parent_tip": "<One practical sentence. Specific retailer, price, or timing. Max 20 words.>"
}}"""


def _build_prediction_prompt(toy: ScoredToy) -> str:
    social_views = (toy.tiktok_views_7d or 0) + (toy.youtube_views_7d or 0)
    return f"""You write trend predictions for ToyRadar's "On Our Radar" section.
Tone: confident, specific, exciting — like a friend who always knows what's about to be hot.

TOY: {toy.name} | Heat: {toy.heat_score:.1f}/100 (Emerging)
Search accel: {toy.search_acceleration or 'N/A'} week-over-week
Resale: {f'${toy.ebay_avg_sold_price:.2f} vs ${toy.retail_price:.2f} retail' if toy.ebay_avg_sold_price else 'none yet'}
Social views 7d: {int(social_views):,} | Reddit: {int(toy.reddit_mentions_7d or 0)}

Respond ONLY with JSON:
{{
  "signal_label": "<4-6 word label>",
  "prediction_narrative": "<2 sentences. Name the signal. Tell parents what to do now. Max 40 words.>",
  "estimated_breakout": "<e.g. '2-3 weeks'>"
}}"""


def _build_alert_prompt(toy: ScoredToy, alert_type: str) -> str:
    return f"""Write a short urgent email alert for ToyRadar subscribers.
Subject + 3 sentences max. No fluff. Parents are busy.

Alert: {alert_type} | Toy: {toy.name} by {toy.brand}
Heat: {toy.heat_score:.1f}/100 | Stock: {toy.amz_stock_pct or 'unknown'}%
Retail: ${toy.retail_price:.2f} | Resale: ${toy.ebay_avg_sold_price if toy.ebay_avg_sold_price else 'N/A'}
Where to buy: {', '.join(toy.retailers or [])}

Respond ONLY with JSON:
{{
  "subject": "<Urgent subject line. Max 8 words.>",
  "body": "<3 sentences. What happened, why it matters, what to do now.>"
}}"""


def _build_anomaly_prompt(toy: ScoredToy) -> str:
    return f"""Data quality check for ToyRadar. Flag anything suspicious or contradictory.

TOY: {toy.name} | Heat: {toy.heat_score:.1f}
Search: {toy.search_velocity} | Accel: {toy.search_acceleration}
Stock%: {toy.amz_stock_pct} | eBay: {toy.ebay_avg_sold_price} | Retail: ${toy.retail_price}
TikTok: {toy.tiktok_views_7d} | YouTube: {toy.youtube_views_7d} | Reddit: {toy.reddit_mentions_7d}

Respond ONLY with JSON:
{{
  "anomaly_detected": true or false,
  "description": "<specific plain-English description or 'Signals look consistent.'>",
  "severity": "<'low' | 'medium' | 'high' — only if anomaly>"
}}"""


def _build_weekly_digest_prompt(toys: list, week_ending: str) -> str:
    toy_summaries = "\n".join([
        f"  - {t.name}: heat {t.heat_score:.1f}, {t.status}, "
        f"stock={t.stock_risk}, resale={t.resale_flag}"
        for t in sorted(toys, key=lambda x: x.heat_score, reverse=True)
    ])
    return f"""Write the weekly radar.toys digest email.
Subscribers are parents. Tone: friendly expert — like a well-connected parent friend.
Lead with the biggest story. Be specific. Name names. Give prices.

WEEK ENDING: {week_ending}
TOYS:
{toy_summaries}

Respond ONLY with JSON:
{{
  "subject": "<Subject line>",
  "opening": "<Opening paragraph — biggest story this week>",
  "quick_hits": ["<bullet 1>", "<bullet 2>", "<bullet 3>"],
  "get_ahead_pick": "<Toy name + 1 sentence why>",
  "signoff": "<2 sentence warm sign-off>"
}}"""

# ─────────────────────────────────────────────
# PROMPT BUILDERS — SOCIAL CONTENT
# ─────────────────────────────────────────────

def _build_social_prompt(toy: ScoredToy) -> str:
    """
    One Claude call generates content for all four platforms.
    Efficient and consistent voice across channels.
    """
    social_views = (toy.tiktok_views_7d or 0) + (toy.youtube_views_7d or 0)
    resale_str   = (
        f"${toy.ebay_avg_sold_price:.2f} on eBay "
        f"({toy.ebay_avg_sold_price/toy.retail_price:.1f}x the retail price of ${toy.retail_price:.2f})"
        if toy.ebay_avg_sold_price else "no resale data yet"
    )

    return f"""You write viral social media content for radar.toys — a toy trend tracker.
Audience: parents and kids. Tone: urgent, specific, data-driven, emoji-forward.
Goal: stop the scroll. Create FOMO. Drive them to radar.toys.
NEVER invent facts. Only use the data below.

TOY DATA:
Name:            {toy.name}
Brand:           {toy.brand}
Category:        {toy.category}
Age range:       {toy.age_range}
Retail price:    ${toy.retail_price:.2f}
Heat score:      {toy.heat_score:.1f}/100
Status:          {toy.status}
Stock risk:      {toy.stock_risk}
Resale:          {resale_str}
Search velocity: {toy.search_velocity or 'N/A'}/100
Search accel:    {f'+{toy.search_acceleration:.1f} this week' if toy.search_acceleration else 'N/A'}
Social views 7d: {int(social_views):,} combined TikTok + YouTube
Reddit mentions: {int(toy.reddit_mentions_7d or 0)} this week
Where to buy:    {', '.join(toy.retailers or [])}

PLATFORM RULES:

X/TWITTER (280 chars max)
Lead with the most shocking data point. 2 emojis minimum.
End with radar.toys. Max 2 hashtags.
Best formats:
"🚨 [shocking stat]. [why it matters]. [what to do]. radar.toys"
"💸 [retail price] at [store]. [resale price] on eBay. [implication]. radar.toys"

TIKTOK HOOK (15 words max, spoken)
Opens a video. Creates immediate curiosity. Makes them stop scrolling.
Best formats:
"This toy costs $X at Target. It's $X on eBay. Here's why."
"Every kid at school wants this right now. But it's almost gone."

TIKTOK CAPTION (100 chars + 5 hashtags)
Complements the video. Teases the reveal. Ends with radar.toys.

INSTAGRAM (2-3 sentences + 8-10 hashtags on new line)
Visual and aspirational. "Swipe to see where to buy."
Speaks to the parent who wants to be the hero.

FACEBOOK (3-4 sentences, conversational)
Parent-to-parent tone. Lead with empathy.
"Tired of missing out on the toy everyone wants?"
Longer is fine. End with radar.toys link.

TICKER (ALL CAPS, 10 words max)
For the scrolling ticker bar on the website.
Most shocking fact about this toy in 10 words.

Respond ONLY with JSON:
{{
  "twitter_post": "<primary tweet — most data-driven angle>",
  "twitter_hook": "<alternate tweet — different emotional angle>",
  "tiktok_hook": "<15-word spoken video opener>",
  "tiktok_caption": "<caption + hashtags>",
  "instagram_caption": "<caption + hashtags on new line>",
  "facebook_post": "<parent-friendly conversational post>",
  "ticker_hook": "<ALL CAPS 10-word ticker line>",
  "best_platform": "<'twitter' | 'tiktok' | 'instagram' | 'facebook'>",
  "post_urgency": "<'immediate' | 'today' | 'this week'>"
}}"""


def _build_daily_calendar_prompt(
    toys: list[ScoredToy],
    social_outputs: list[SocialContent]
) -> str:
    """Rank and schedule all posts into an optimal daily calendar."""
    lines = "\n".join([
        f"  - {s.toy_id} | urgency={s.post_urgency} | "
        f"best={s.best_platform} | "
        f"twitter='{s.twitter_post[:55]}…'"
        for s in social_outputs if s.twitter_post
    ])
    return f"""You are the social media manager for radar.toys.
Build today's optimal posting schedule. Goal: max reach, drive email signups.

AVAILABLE CONTENT:
{lines}

SCHEDULING RULES:
Twitter: 4-5 posts, spaced 2-3 hours. First post at 7AM.
TikTok:  1-2 hooks. Best urgency story first.
Instagram: 1 post. Most visual/aspirational story.
Facebook: 1 post. Most parent-friendly story.
Never post same brand twice in a row.
Lead with "immediate" urgency items first.
Mix categories throughout the day.

Respond ONLY with JSON:
{{
  "schedule": [
    {{
      "time": "7:00 AM",
      "platform": "twitter",
      "toy_id": "<toy_id>",
      "content": "<exact post text>",
      "reason": "<one sentence why this story at this time>"
    }}
  ],
  "top_story_of_day": "<toy name>",
  "editors_note": "<one sentence overall social strategy for today>"
}}"""

# ─────────────────────────────────────────────
# MAIN SYNTHESIZER
# ─────────────────────────────────────────────

class ToyRadarSynthesizer:

    def __init__(self):
        self.claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.db     = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

    def run(self) -> list[SynthesisOutput]:
        log.info("=" * 55)
        log.info("  ToyRadar Synthesis Run Starting")
        log.info(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        log.info("=" * 55)

        toys    = self._load_scored_toys()
        outputs = []

        for toy in toys:
            log.info(f"\n── {toy.name} ──")
            output = self._synthesize_toy(toy)
            outputs.append(output)
            self._save_content(output)

        # Daily social calendar
        log.info("\n── Daily Social Calendar ──")
        social_list = [o.social for o in outputs if o.social]
        calendar    = self._generate_social_calendar(toys, social_list)
        self._save_calendar(calendar)

        # Weekly digest — Mondays only
        if datetime.utcnow().weekday() == 0:
            log.info("\n── Weekly Digest ──")
            digest = self._generate_weekly_digest(toys)
            self._save_digest(digest)

        log.info(f"\n✅ Done — {len(outputs)} toys")
        return outputs

    def _synthesize_toy(self, toy: ScoredToy) -> SynthesisOutput:
        output = SynthesisOutput(
            toy_id=toy.toy_id, name=toy.name,
            generated_at=datetime.utcnow().isoformat(),
            card_description="", card_tag="", parent_tip="",
        )

        # 1. Card content
        card = self._call_claude(_build_card_prompt(toy), "card")
        if card:
            output.card_description = card.get("card_description", "")
            output.card_tag         = card.get("card_tag", "TRENDING")
            output.parent_tip       = card.get("parent_tip", "")

        # 2. Prediction — breakout only
        if toy.breakout_flag:
            pred = self._call_claude(_build_prediction_prompt(toy), "prediction")
            if pred:
                output.prediction_narrative = (
                    f"{pred.get('prediction_narrative', '')} "
                    f"Estimated breakout: {pred.get('estimated_breakout', 'soon')}."
                )

        # 3. Alert — threshold-triggered
        alert_type = self._determine_alert_type(toy)
        if alert_type:
            alert = self._call_claude(_build_alert_prompt(toy, alert_type), "alert")
            if alert:
                output.alert_subject = alert.get("subject", "")
                output.alert_body    = alert.get("body", "")

        # 4. Anomaly check
        anomaly = self._call_claude(_build_anomaly_prompt(toy), "anomaly")
        if anomaly and anomaly.get("anomaly_detected"):
            sev = anomaly.get("severity", "low")
            output.anomaly_flag = f"[{sev.upper()}] {anomaly.get('description', '')}"
            log.warning(f"  ⚠️  {output.anomaly_flag}")

        # 5. Social — post-worthy toys only
        if toy.heat_score >= SOCIAL_MIN_HEAT_SCORE or toy.resale_flag:
            output.social = self._synthesize_social(toy)

        return output

    def _synthesize_social(self, toy: ScoredToy) -> Optional[SocialContent]:
        result = self._call_claude(_build_social_prompt(toy), "social")
        if not result:
            return None
        return SocialContent(
            toy_id            = toy.toy_id,
            name              = toy.name,
            twitter_post      = result.get("twitter_post", ""),
            twitter_hook      = result.get("twitter_hook", ""),
            tiktok_hook       = result.get("tiktok_hook", ""),
            tiktok_caption    = result.get("tiktok_caption", ""),
            instagram_caption = result.get("instagram_caption", ""),
            facebook_post     = result.get("facebook_post", ""),
            ticker_hook       = result.get("ticker_hook", ""),
            best_platform     = result.get("best_platform", "twitter"),
            post_urgency      = result.get("post_urgency", "today"),
            generated_at      = datetime.utcnow().isoformat(),
        )

    def _generate_social_calendar(
        self,
        toys: list[ScoredToy],
        social_list: list[SocialContent]
    ) -> dict:
        if not social_list:
            return {}
        cal = self._call_claude(
            _build_daily_calendar_prompt(toys, social_list), "calendar"
        )
        if cal:
            log.info(f"  Top story: {cal.get('top_story_of_day')}")
            log.info(f"  Strategy:  {cal.get('editors_note')}")
            n = len(cal.get("schedule", []))
            log.info(f"  {n} posts scheduled today")
        return cal or {}

    def _generate_weekly_digest(self, toys: list) -> dict:
        week_ending = date.today().strftime("%B %d, %Y")
        digest = self._call_claude(
            _build_weekly_digest_prompt(toys, week_ending), "weekly_digest"
        )
        log.info(f"  Subject: {digest.get('subject', '(none)')}")
        return digest or {}

    def _determine_alert_type(self, toy: ScoredToy) -> Optional[str]:
        if (toy.heat_score >= ALERT_HEAT_THRESHOLD
                and toy.amz_stock_pct is not None
                and toy.amz_stock_pct < ALERT_STOCK_THRESHOLD):
            return "RESTOCK_ALERT"
        if (toy.resale_flag and toy.ebay_avg_sold_price
                and toy.ebay_avg_sold_price > toy.retail_price * RESALE_ALERT_MULTIPLIER):
            return "RESALE_SPIKE"
        if toy.breakout_flag:
            return "BREAKOUT_DETECTED"
        return None

    def _call_claude(self, prompt: str, task: str = "") -> Optional[dict]:
        try:
            log.info(f"  → Claude [{task}]")
            response = self.claude.messages.create(
                model=MODEL, max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as e:
            log.error(f"  Claude error [{task}]: {e}")
            return None

    def _load_scored_toys(self) -> list[ScoredToy]:
        if not self.db:
            return _sample_scored_toys()
        try:
            resp = self.db.table("toy_scores_latest").select("*").execute()
            return [_row_to_scored_toy(r) for r in resp.data]
        except Exception as e:
            log.error(f"DB load error: {e}")
            return _sample_scored_toys()

    def _save_content(self, output: SynthesisOutput):
        if not self.db:
            return
        try:
            self.db.table("toy_content").upsert({
                "toy_id":               output.toy_id,
                "card_description":     output.card_description,
                "card_tag":             output.card_tag,
                "parent_tip":           output.parent_tip,
                "prediction_narrative": output.prediction_narrative,
                "alert_subject":        output.alert_subject,
                "alert_body":           output.alert_body,
                "anomaly_flag":         output.anomaly_flag,
                "generated_at":         output.generated_at,
            }, on_conflict="toy_id").execute()

            if output.social:
                s = output.social
                self.db.table("toy_social").upsert({
                    "toy_id":           s.toy_id,
                    "twitter_post":     s.twitter_post,
                    "twitter_hook":     s.twitter_hook,
                    "tiktok_hook":      s.tiktok_hook,
                    "tiktok_caption":   s.tiktok_caption,
                    "instagram_caption": s.instagram_caption,
                    "facebook_post":    s.facebook_post,
                    "ticker_hook":      s.ticker_hook,
                    "best_platform":    s.best_platform,
                    "post_urgency":     s.post_urgency,
                    "generated_at":     s.generated_at,
                }, on_conflict="toy_id").execute()

            log.info("  ✓ Saved")
        except Exception as e:
            log.error(f"  Save error: {e}")

    def _save_calendar(self, calendar: dict):
        if not self.db or not calendar:
            return
        try:
            self.db.table("social_calendars").insert({
                "date":         date.today().isoformat(),
                "schedule":     json.dumps(calendar.get("schedule", [])),
                "top_story":    calendar.get("top_story_of_day"),
                "editors_note": calendar.get("editors_note"),
            }).execute()
            log.info("  ✓ Calendar saved")
        except Exception as e:
            log.error(f"  Calendar save error: {e}")

    def _save_digest(self, digest: dict):
        if not self.db or not digest:
            return
        try:
            self.db.table("weekly_digests").insert({
                "week_ending": date.today().isoformat(),
                "subject":     digest.get("subject"),
                "opening":     digest.get("opening"),
                "quick_hits":  json.dumps(digest.get("quick_hits", [])),
                "get_ahead":   digest.get("get_ahead_pick"),
                "signoff":     digest.get("signoff"),
            }).execute()
            log.info("  ✓ Digest saved")
        except Exception as e:
            log.error(f"  Digest save error: {e}")

# ─────────────────────────────────────────────
# SUPABASE SCHEMA — run once to add social tables
# ─────────────────────────────────────────────

SOCIAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS toy_social (
    toy_id             TEXT PRIMARY KEY,
    twitter_post       TEXT,
    twitter_hook       TEXT,
    tiktok_hook        TEXT,
    tiktok_caption     TEXT,
    instagram_caption  TEXT,
    facebook_post      TEXT,
    ticker_hook        TEXT,
    best_platform      TEXT,
    post_urgency       TEXT,
    generated_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS social_calendars (
    id            BIGSERIAL PRIMARY KEY,
    date          DATE NOT NULL,
    schedule      JSONB,
    top_story     TEXT,
    editors_note  TEXT,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
"""

# ─────────────────────────────────────────────
# SAMPLE DATA
# ─────────────────────────────────────────────

def _sample_scored_toys() -> list[ScoredToy]:
    return [
        ScoredToy(
            toy_id="needoh-nice-cube", name="NeeDoh Nice Cube",
            brand="Schylling", category="Sensory / Squishies",
            age_range="3+", retail_price=8.99,
            heat_score=97.2, status="Peak Demand",
            stock_risk="Critical", resale_flag=True, breakout_flag=False,
            search_velocity=92, search_acceleration=18,
            amz_stock_pct=8, ebay_avg_sold_price=24.00,
            tiktok_views_7d=4_200_000, youtube_views_7d=1_800_000,
            reddit_mentions_7d=312,
            retailers=["Five Below", "Target", "Amazon"],
        ),
        ScoredToy(
            toy_id="needoh-sugar-skull-cats", name="NeeDoh Sugar Skull Cool Cats",
            brand="Schylling", category="Sensory / Squishies",
            age_range="5+", retail_price=7.99,
            heat_score=48.5, status="Emerging",
            stock_risk="Medium", resale_flag=True, breakout_flag=True,
            search_velocity=41, search_acceleration=22,
            amz_stock_pct=55, ebay_avg_sold_price=95.00,
            tiktok_views_7d=380_000, youtube_views_7d=None,
            reddit_mentions_7d=47,
            retailers=["eBay", "specialty toy shops"],
        ),
        ScoredToy(
            toy_id="jellycat-lazulia-dragon", name="Jellycat Lazulia Dragon",
            brand="Jellycat", category="Collectible Plush",
            age_range="All ages", retail_price=75.00,
            heat_score=82.1, status="Rising Fast",
            stock_risk="High", resale_flag=False, breakout_flag=False,
            search_velocity=78, search_acceleration=15,
            amz_stock_pct=22, ebay_avg_sold_price=130.00,
            tiktok_views_7d=2_100_000, youtube_views_7d=540_000,
            reddit_mentions_7d=188,
            retailers=["Jellycat.com", "Nordstrom", "FAO Schwarz"],
        ),
    ]


def _row_to_scored_toy(row: dict) -> ScoredToy:
    return ScoredToy(
        toy_id               = row["toy_id"],
        name                 = row["name"],
        brand                = row.get("brand", ""),
        category             = row.get("category", ""),
        age_range            = row.get("age_range", ""),
        retail_price         = float(row.get("retail_price", 0)),
        heat_score           = float(row.get("heat_score", 0)),
        status               = row.get("status", "Emerging"),
        stock_risk           = row.get("stock_risk", "Unknown"),
        resale_flag          = bool(row.get("resale_flag", False)),
        breakout_flag        = bool(row.get("breakout_flag", False)),
        search_velocity      = row.get("search_velocity"),
        search_acceleration  = row.get("search_acceleration"),
        amz_stock_pct        = row.get("amz_stock_pct"),
        ebay_avg_sold_price  = row.get("ebay_avg_sold_price"),
        tiktok_views_7d      = row.get("tiktok_views_7d"),
        youtube_views_7d     = row.get("youtube_views_7d"),
        reddit_mentions_7d   = row.get("reddit_mentions_7d"),
        retailers            = row.get("retailers", []),
    )

# ─────────────────────────────────────────────
# CRON
# ─────────────────────────────────────────────

CRON_SCHEDULE = """
# ToyRadar — Synthesis + Social (2x daily)
0 8  * * *  cd /path/to/toyradar && python synthesizer.py >> logs/synthesizer.log 2>&1
0 20 * * *  cd /path/to/toyradar && python synthesizer.py >> logs/synthesizer.log 2>&1
"""

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    synth   = ToyRadarSynthesizer()
    outputs = synth.run()

    print("\n" + "═" * 65)
    print("  SYNTHESIS + SOCIAL OUTPUT")
    print("═" * 65)

    for o in outputs:
        print(f"\n  {o.name}")
        print(f"  {'─' * 45}")
        print(f"  Tag:         {o.card_tag}")
        print(f"  Description: {o.card_description}")
        print(f"  Parent tip:  {o.parent_tip}")
        if o.prediction_narrative:
            print(f"  Prediction:  {o.prediction_narrative}")
        if o.alert_subject:
            print(f"  Alert:       [{o.alert_subject}]")
        if o.anomaly_flag:
            print(f"  ⚠️  Anomaly: {o.anomaly_flag}")
        if o.social:
            print(f"\n  📱 SOCIAL")
            print(f"  🐦 Twitter:    {o.social.twitter_post}")
            print(f"  🎵 TikTok:     {o.social.tiktok_hook}")
            print(f"  📸 Instagram:  {o.social.instagram_caption[:80]}...")
            print(f"  👥 Facebook:   {o.social.facebook_post[:80]}...")
            print(f"  📺 Ticker:     {o.social.ticker_hook}")
            print(f"  Best platform: {o.social.best_platform} ({o.social.post_urgency})")

    print("\n" + "═" * 65 + "\n")
