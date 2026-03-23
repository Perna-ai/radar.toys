"""
ToyRadar — Data Collection Layer

collectors.py

Five independent data collectors, one per signal source.
Each returns a standardized dict that feeds directly into
ToySignals in toy_scoring.py.

Collectors:

1. GoogleTrendsCollector   — search velocity + acceleration
2. AmazonCollector         — BSR movement + stock level
3. EbayCollector           — resale price (strongest leading signal)
4. SocialCollector         — TikTok + YouTube view velocity
5. RedditCollector         — forum mention count

Master runner:
DataCollectionRunner       — runs all five, merges, saves to DB

Setup:
pip install pytrends requests praw google-api-python-client supabase

Env vars required (.env):
RAPIDAPI_KEY         — for Amazon + TikTok endpoints
EBAY_APP_ID          — eBay Finding API
REDDIT_CLIENT_ID
REDDIT_CLIENT_SECRET
YOUTUBE_API_KEY
SUPABASE_URL
SUPABASE_KEY
"""

import os
import time
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, asdict

import requests
from pytrends.request import TrendReq
import praw
from googleapiclient.discovery import build
from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("toyradar.collectors")

# ─────────────────────────────────────────────
# SHARED CONFIG
# ─────────────────────────────────────────────

RAPIDAPI_KEY         = os.getenv("RAPIDAPI_KEY")
EBAY_APP_ID          = os.getenv("EBAY_APP_ID")
REDDIT_CLIENT_ID     = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
YOUTUBE_API_KEY      = os.getenv("YOUTUBE_API_KEY")
SUPABASE_URL         = os.getenv("SUPABASE_URL")
SUPABASE_KEY         = os.getenv("SUPABASE_KEY")


@dataclass
class RawSignals:
    """
    One row of raw collected data per toy.
    Mirrors ToySignals fields — fed directly into scorer.
    """
    toy_id:               str
    name:                 str
    retail_price:         float
    collected_at:         str             = ""

    # Google Trends
    search_velocity:      Optional[float] = None
    search_acceleration:  Optional[float] = None

    # Amazon
    amz_bsr_movement:     Optional[float] = None
    amz_stock_pct:        Optional[float] = None

    # eBay
    ebay_avg_sold_price:  Optional[float] = None

    # Social
    tiktok_views_7d:      Optional[float] = None
    youtube_views_7d:     Optional[float] = None

    # Reddit
    reddit_mentions_7d:   Optional[float] = None


# ─────────────────────────────────────────────
# 1. GOOGLE TRENDS
# ─────────────────────────────────────────────

class GoogleTrendsCollector:
    """
    Uses pytrends (unofficial Google Trends wrapper).
    Free, no API key needed.

    Returns:
      search_velocity     — current interest score (0–100)
      search_acceleration — week-over-week change
    """

    def __init__(self):
        self.pt = TrendReq(hl="en-US", tz=360, timeout=(10, 25), retries=3)

    def collect(self, toy_name: str) -> dict:
        try:
            log.info(f"Google Trends → {toy_name}")

            # Pull last 90 days weekly data
            self.pt.build_payload(
                kw_list=[toy_name],
                timeframe="today 3-m",
                geo="US",
            )
            df = self.pt.interest_over_time()

            if df.empty:
                log.warning(f"No Trends data for {toy_name}")
                return {}

            values = df[toy_name].tolist()

            # Current velocity = most recent week score
            current = float(values[-1])

            # Acceleration = delta between last two weeks
            prev  = float(values[-2]) if len(values) >= 2 else current
            accel = current - prev

            log.info(f"  velocity={current:.1f}  accel={accel:+.1f}")
            time.sleep(1.2)  # be polite to Google

            return {
                "search_velocity":     current,
                "search_acceleration": accel,
            }

        except Exception as e:
            log.error(f"Google Trends error for {toy_name}: {e}")
            return {}


# ─────────────────────────────────────────────
# 2. AMAZON
# ─────────────────────────────────────────────

class AmazonCollector:
    """
    Uses the Rainforest API via RapidAPI (paid, ~$50/mo for moderate use).
    Alternative: scraperapi.com or axesso.de

    Returns:
      amz_bsr_movement — BSR rank delta (positive = rank falling = demand rising)
      amz_stock_pct    — estimated % of stock remaining (0–100)
    """

    BASE_URL = "https://rainforest-api.p.rapidapi.com/request"
    HEADERS  = {
        "X-RapidAPI-Key":  RAPIDAPI_KEY,
        "X-RapidAPI-Host": "rainforest-api.p.rapidapi.com",
    }

    def collect(self, asin: str, prev_bsr: Optional[int] = None) -> dict:
        """
        asin     — Amazon product ID (e.g. "B07Q2P3JNH")
        prev_bsr — BSR from previous collection run, stored in DB
        """
        try:
            log.info(f"Amazon → ASIN {asin}")

            params = {"type": "product", "asin": asin, "amazon_domain": "amazon.com"}
            resp   = requests.get(self.BASE_URL, headers=self.HEADERS, params=params, timeout=15)
            resp.raise_for_status()
            data   = resp.json().get("product", {})

            # Best Seller Rank
            bsr_list = data.get("bestsellers_rank", [])
            bsr      = int(bsr_list[0].get("rank", 0)) if bsr_list else None

            # BSR movement: positive means rank number fell (product rising)
            bsr_movement = None
            if bsr and prev_bsr:
                bsr_movement = float(prev_bsr - bsr)  # positive = moving up

            # Stock level — Amazon rarely exposes exact counts
            # Use availability string as proxy
            availability = data.get("availability", {}).get("type", "")
            stock_pct    = self._parse_stock_pct(availability)

            log.info(f"  bsr={bsr}  movement={bsr_movement}  stock={stock_pct}%")
            return {
                "amz_bsr_movement": bsr_movement,
                "amz_stock_pct":    stock_pct,
                "amz_bsr_current":  bsr,  # store for next run's delta calc
            }

        except Exception as e:
            log.error(f"Amazon error for ASIN {asin}: {e}")
            return {}

    def _parse_stock_pct(self, availability: str) -> Optional[float]:
        """Map Amazon availability strings to estimated stock %."""
        availability = availability.lower()
        if "in stock"      in availability: return 75.0
        if "only"          in availability:
            # "Only 3 left in stock" → critically low
            try:
                n = int(''.join(filter(str.isdigit, availability)))
                return min(float(n) * 5, 20.0)  # rough proxy
            except:
                return 10.0
        if "out of stock"  in availability: return 0.0
        if "usually ships" in availability: return 50.0
        return None


# ─────────────────────────────────────────────
# 3. EBAY RESALE
# ─────────────────────────────────────────────

class EbayCollector:
    """
    Uses eBay Finding API (free with eBay developer account).
    Queries COMPLETED listings to get real sold prices —
    the strongest early-warning signal in the whole system.

    Returns:
      ebay_avg_sold_price — average price of completed sales, last 7 days
    """

    ENDPOINT = "https://svcs.ebay.com/services/search/FindingService/v1"

    def collect(self, search_term: str) -> dict:
        try:
            log.info(f"eBay → {search_term}")

            # Date range: last 7 days
            end_date   = datetime.utcnow()
            start_date = end_date - timedelta(days=7)

            params = {
                "OPERATION-NAME":                    "findCompletedItems",
                "SERVICE-VERSION":                   "1.0.0",
                "SECURITY-APPNAME":                  EBAY_APP_ID,
                "RESPONSE-DATA-FORMAT":              "JSON",
                "keywords":                          search_term,
                "itemFilter(0).name":                "SoldItemsOnly",
                "itemFilter(0).value":               "true",
                "itemFilter(1).name":                "StartTimeFrom",
                "itemFilter(1).value":               start_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "sortOrder":                         "EndTimeSoonest",
                "paginationInput.entriesPerPage":    "50",
            }

            resp = requests.get(self.ENDPOINT, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            items = (
                data.get("findCompletedItemsResponse", [{}])[0]
                    .get("searchResult", [{}])[0]
                    .get("item", [])
            )

            if not items:
                log.warning(f"No eBay sold data for {search_term}")
                return {}

            prices = []
            for item in items:
                try:
                    price = float(
                        item["sellingStatus"][0]["currentPrice"][0]["__value__"]
                    )
                    prices.append(price)
                except (KeyError, IndexError, ValueError):
                    continue

            if not prices:
                return {}

            avg_price = round(sum(prices) / len(prices), 2)
            log.info(f"  avg_sold=${avg_price:.2f}  ({len(prices)} sales)")

            return {"ebay_avg_sold_price": avg_price}

        except Exception as e:
            log.error(f"eBay error for {search_term}: {e}")
            return {}


# ─────────────────────────────────────────────
# 4. SOCIAL — TikTok + YouTube
# ─────────────────────────────────────────────

class SocialCollector:
    """
    TikTok: Uses TikTok Research API via RapidAPI.
    YouTube: Uses official YouTube Data API v3 (free, generous quota).

    Returns:
      tiktok_views_7d  — total views on toy-related content, last 7 days
      youtube_views_7d — same for YouTube
    """

    TIKTOK_URL     = "https://tiktok-api23.p.rapidapi.com/api/search/video"
    TIKTOK_HEADERS = {
        "X-RapidAPI-Key":  RAPIDAPI_KEY,
        "X-RapidAPI-Host": "tiktok-api23.p.rapidapi.com",
    }

    def collect(self, search_term: str) -> dict:
        result = {}
        result.update(self._tiktok(search_term))
        result.update(self._youtube(search_term))
        return result

    def _tiktok(self, search_term: str) -> dict:
        try:
            log.info(f"TikTok → {search_term}")
            params = {"keywords": search_term, "count": "30", "cursor": "0"}
            resp   = requests.get(self.TIKTOK_URL, headers=self.TIKTOK_HEADERS, params=params, timeout=15)
            resp.raise_for_status()
            videos = resp.json().get("data", {}).get("videos", [])

            cutoff      = datetime.utcnow() - timedelta(days=7)
            total_views = 0
            for v in videos:
                try:
                    created = datetime.utcfromtimestamp(v.get("createTime", 0))
                    if created >= cutoff:
                        total_views += int(v.get("stats", {}).get("playCount", 0))
                except:
                    continue

            log.info(f"  TikTok views 7d = {total_views:,}")
            return {"tiktok_views_7d": float(total_views)}

        except Exception as e:
            log.error(f"TikTok error for {search_term}: {e}")
            return {}

    def _youtube(self, search_term: str) -> dict:
        try:
            log.info(f"YouTube → {search_term}")
            youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
            cutoff  = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

            # Search for recent videos
            search_resp = youtube.search().list(
                q=search_term,
                type="video",
                part="id",
                maxResults=25,
                publishedAfter=cutoff,
                relevanceLanguage="en",
            ).execute()

            video_ids = [
                item["id"]["videoId"]
                for item in search_resp.get("items", [])
            ]

            if not video_ids:
                return {"youtube_views_7d": 0.0}

            # Batch fetch view counts
            stats_resp = youtube.videos().list(
                part="statistics",
                id=",".join(video_ids),
            ).execute()

            total_views = sum(
                int(item.get("statistics", {}).get("viewCount", 0))
                for item in stats_resp.get("items", [])
            )

            log.info(f"  YouTube views 7d = {total_views:,}")
            return {"youtube_views_7d": float(total_views)}

        except Exception as e:
            log.error(f"YouTube error for {search_term}: {e}")
            return {}


# ─────────────────────────────────────────────
# 5. REDDIT
# ─────────────────────────────────────────────

class RedditCollector:
    """
    Uses PRAW (official Reddit API wrapper, free).
    Searches key subreddits for organic toy mentions.
    Organic = parents and kids talking, not ads.

    Returns:
      reddit_mentions_7d — post + comment mention count, last 7 days
    """

    SUBREDDITS = [
        "Parenting", "toys", "toddlers", "Mommit", "daddit",
        "KidsAreFuckingStupid", "Teachers", "elementary",
    ]

    def __init__(self):
        self.reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent="ToyRadar/1.0 (trend research bot)",
        )

    def collect(self, search_term: str) -> dict:
        try:
            log.info(f"Reddit → {search_term}")
            cutoff = datetime.utcnow() - timedelta(days=7)
            count  = 0

            for subreddit_name in self.SUBREDDITS:
                try:
                    subreddit = self.reddit.subreddit(subreddit_name)
                    results   = subreddit.search(
                        search_term,
                        sort="new",
                        time_filter="week",
                        limit=50,
                    )
                    for post in results:
                        created = datetime.utcfromtimestamp(post.created_utc)
                        if created >= cutoff:
                            count += 1  # count the post
                            # Also count top-level comments that mention the toy
                            post.comments.replace_more(limit=0)
                            for comment in post.comments.list()[:20]:
                                if search_term.lower() in comment.body.lower():
                                    count += 1
                except Exception as sub_err:
                    log.warning(f"  Subreddit {subreddit_name} error: {sub_err}")
                    continue

            log.info(f"  Reddit mentions 7d = {count}")
            return {"reddit_mentions_7d": float(count)}

        except Exception as e:
            log.error(f"Reddit error for {search_term}: {e}")
            return {}


# ─────────────────────────────────────────────
# TOY CATALOG
# Add new toys here — everything else is automatic
# ─────────────────────────────────────────────

TOY_CATALOG = [
    {
        "toy_id":       "needoh-nice-cube",
        "name":         "NeeDoh Nice Cube",
        "retail_price": 8.99,
        "search_term":  "NeeDoh Nice Cube",
        "asin":         "B07Q2P3JNH",
        "ebay_query":   "NeeDoh Nice Cube squishy",
    },
    {
        "toy_id":       "needoh-dream-drop",
        "name":         "NeeDoh Dream Drop",
        "retail_price": 7.99,
        "search_term":  "NeeDoh Dream Drop",
        "asin":         "B09XK7MHZR",
        "ebay_query":   "NeeDoh Dream Drop",
    },
    {
        "toy_id":       "jellycat-lazulia-dragon",
        "name":         "Jellycat Lazulia Dragon",
        "retail_price": 75.00,
        "search_term":  "Jellycat Lazulia Dragon",
        "asin":         "B0CX7RBXYZ",
        "ebay_query":   "Jellycat Lazulia Dragon plush",
    },
    {
        "toy_id":       "jellycat-carrot-cake",
        "name":         "Jellycat Amuseables Carrot Cake",
        "retail_price": 30.00,
        "search_term":  "Jellycat Carrot Cake",
        "asin":         "B0DXQ3PLMN",
        "ebay_query":   "Jellycat Carrot Cake amuseable",
    },
    {
        "toy_id":       "pokemon-30th-booster",
        "name":         "Pokémon 30th Anniversary Booster",
        "retail_price": 15.99,
        "search_term":  "Pokemon 30th anniversary booster pack",
        "asin":         "B0D9XPQRST",
        "ebay_query":   "Pokemon 30th anniversary booster",
    },
    {
        "toy_id":       "needoh-sugar-skull-cats",
        "name":         "NeeDoh Sugar Skull Cool Cats",
        "retail_price": 7.99,
        "search_term":  "NeeDoh Sugar Skull Cool Cats",
        "asin":         "B0BXYZ1234",
        "ebay_query":   "NeeDoh Sugar Skull Cool Cats squishy",
    },
]


# ─────────────────────────────────────────────
# MASTER RUNNER
# ─────────────────────────────────────────────

class DataCollectionRunner:
    """
    Orchestrates all five collectors for every toy in the catalog.
    Merges results into RawSignals, saves to Supabase.
    Designed to run on a cron schedule (every 30–60 min).

    Usage:
        runner = DataCollectionRunner()
        runner.run()
    """

    def __init__(self):
        self.trends = GoogleTrendsCollector()
        self.amazon = AmazonCollector()
        self.ebay   = EbayCollector()
        self.social = SocialCollector()
        self.reddit = RedditCollector()
        self.db     = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None

    def run(self) -> list[RawSignals]:
        log.info("=" * 55)
        log.info("  ToyRadar Data Collection Run Starting")
        log.info(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
        log.info("=" * 55)

        results = []

        for toy in TOY_CATALOG:
            log.info(f"\n── {toy['name']} ──────────────────────")

            # Fetch previous BSR from DB for delta calculation
            prev_bsr = self._get_prev_bsr(toy["toy_id"])

            # Run all collectors — each returns partial dict, we merge
            signals = {}
            signals.update(self.trends.collect(toy["search_term"]))
            signals.update(self.amazon.collect(toy["asin"], prev_bsr))
            signals.update(self.ebay.collect(toy["ebay_query"]))
            signals.update(self.social.collect(toy["search_term"]))
            signals.update(self.reddit.collect(toy["search_term"]))

            raw = RawSignals(
                toy_id              = toy["toy_id"],
                name                = toy["name"],
                retail_price        = toy["retail_price"],
                collected_at        = datetime.utcnow().isoformat(),
                search_velocity     = signals.get("search_velocity"),
                search_acceleration = signals.get("search_acceleration"),
                amz_bsr_movement    = signals.get("amz_bsr_movement"),
                amz_stock_pct       = signals.get("amz_stock_pct"),
                ebay_avg_sold_price = signals.get("ebay_avg_sold_price"),
                tiktok_views_7d     = signals.get("tiktok_views_7d"),
                youtube_views_7d    = signals.get("youtube_views_7d"),
                reddit_mentions_7d  = signals.get("reddit_mentions_7d"),
            )

            results.append(raw)
            self._save(raw, signals.get("amz_bsr_current"))

            # Polite delay between toys
            time.sleep(2)

        log.info(f"\n✅ Collection complete — {len(results)} toys processed")
        return results

    def _get_prev_bsr(self, toy_id: str) -> Optional[int]:
        """Fetch last stored BSR from Supabase for delta calculation."""
        if not self.db:
            return None
        try:
            resp = (
                self.db.table("toy_signals")
                    .select("amz_bsr_current")
                    .eq("toy_id", toy_id)
                    .order("collected_at", desc=True)
                    .limit(1)
                    .execute()
            )
            rows = resp.data
            return int(rows[0]["amz_bsr_current"]) if rows else None
        except:
            return None

    def _save(self, raw: RawSignals, amz_bsr_current: Optional[int] = None):
        """Persist raw signals to Supabase toy_signals table."""
        if not self.db:
            log.info("  (No DB configured — skipping save)")
            return
        try:
            row = asdict(raw)
            if amz_bsr_current:
                row["amz_bsr_current"] = amz_bsr_current
            self.db.table("toy_signals").insert(row).execute()
            log.info(f"  ✓ Saved to DB")
        except Exception as e:
            log.error(f"  DB save error: {e}")


# ─────────────────────────────────────────────
# SUPABASE TABLE SCHEMA
# Run once to create the table
# ─────────────────────────────────────────────

SUPABASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS toy_signals (
    id                   BIGSERIAL PRIMARY KEY,
    toy_id               TEXT NOT NULL,
    name                 TEXT,
    retail_price         NUMERIC,
    collected_at         TIMESTAMPTZ DEFAULT NOW(),

    search_velocity      NUMERIC,
    search_acceleration  NUMERIC,
    amz_bsr_movement     NUMERIC,
    amz_bsr_current      INTEGER,
    amz_stock_pct        NUMERIC,
    ebay_avg_sold_price  NUMERIC,
    tiktok_views_7d      NUMERIC,
    youtube_views_7d     NUMERIC,
    reddit_mentions_7d   NUMERIC
);

-- Index for fast per-toy lookups
CREATE INDEX IF NOT EXISTS idx_toy_signals_toy_id
    ON toy_signals (toy_id, collected_at DESC);
"""

# ─────────────────────────────────────────────
# CRON SCHEDULE (add to crontab)
# ─────────────────────────────────────────────

CRON_SCHEDULE = """
# ToyRadar — Data Collection
# Runs every 30 minutes, 6am–midnight
*/30 6-23 * * *  cd /path/to/toyradar && python collectors.py >> logs/collectors.log 2>&1
"""

# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────

if __name__ == "__main__":
    runner = DataCollectionRunner()
    raw_signals = runner.run()

    # Print summary table
    print("\n" + "═" * 65)
    print("  COLLECTION SUMMARY")
    print("═" * 65)
    print(f"  {'Toy':<35} {'Search':>7} {'Stock%':>7} {'eBay$':>8} {'Reddit':>7}")
    print(f"  {'─'*35} {'─'*7} {'─'*7} {'─'*8} {'─'*7}")
    for r in raw_signals:
        print(
            f"  {r.name:<35}"
            f"  {r.search_velocity or '—':>6}"
            f"  {r.amz_stock_pct or '—':>6}"
            f"  {r.ebay_avg_sold_price or '—':>7}"
            f"  {r.reddit_mentions_7d or '—':>6}"
        )
    print("═" * 65 + "\n")
