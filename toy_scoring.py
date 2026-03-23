"""
ToyRadar — Trend Scoring Engine

toy_scoring.py

Computes a composite Heat Score (0–100) for each toy by aggregating
signals across five data sources. Architecture mirrors Rook's
credit_stress.py: raw inputs → z-score normalization → weighted
composite → threshold classification.

Signal Sources (7 indicators):

1. Google Trends search velocity
2. Google Trends acceleration (rate of change)
3. Amazon Best Seller Rank movement
4. Amazon stock level
5. eBay resale premium (resale vs. retail price)
6. Social view velocity (TikTok/YouTube combined views)
7. Reddit/forum mention spike

Output per toy:

- heat_score       : float 0–100
- status           : "Emerging" | "Rising Fast" | "Peak Demand"
- stock_risk       : "Low" | "Medium" | "High" | "Critical"
- resale_flag      : bool — true when resale > 2x retail
- breakout_flag    : bool — true when emerging score crosses threshold
- signal_breakdown : dict of individual weighted contributions
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Optional

# ─────────────────────────────────────────────
# SIGNAL WEIGHTS
# Must sum to 1.0
# Tuned to prioritize search + social as leading
# indicators, with resale as a strong early signal
# ─────────────────────────────────────────────

WEIGHTS = {
    "search_velocity":     0.20,   # Google Trends: current interest level
    "search_acceleration": 0.15,   # Google Trends: rate of change (leading)
    "amz_bsr_movement":    0.15,   # Amazon BSR delta — falling rank = rising demand
    "amz_stock_level":     0.10,   # Low stock amplifies demand signal
    "resale_premium":      0.20,   # eBay resale vs retail — strongest early signal
    "social_velocity":     0.15,   # TikTok + YouTube combined view momentum
    "forum_mentions":      0.05,   # Reddit/parenting forums — organic grassroots signal
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1.0"

# ─────────────────────────────────────────────
# THRESHOLDS
# ─────────────────────────────────────────────

HEAT_THRESHOLDS = {
    "Peak Demand":  80,   # 80–100
    "Rising Fast":  55,   # 55–79
    "Emerging":      0,   # 0–54
}

STOCK_RISK_THRESHOLDS = {
    "Critical": 10,   # <10% stock remaining
    "High":     25,   # <25%
    "Medium":   50,   # <50%
    "Low":     100,   # anything above
}

RESALE_FLAG_MULTIPLIER = 2.0    # flag if eBay price > 2x retail
BREAKOUT_THRESHOLD     = 45     # heat score above this in "Emerging" = breakout candidate

# ─────────────────────────────────────────────
# DATA STRUCTURE
# ─────────────────────────────────────────────

@dataclass
class ToySignals:
    """
    Raw input signals for one toy.
    All values should be non-negative.
    Missing data → None (excluded from composite, weights redistributed).
    """
    toy_id:              str
    name:                str
    retail_price:        float                   # USD — used for resale premium calc

    # Google Trends (0–100 scale, Google's native output)
    search_velocity:     Optional[float] = None  # current interest score
    search_acceleration: Optional[float] = None  # week-over-week delta

    # Amazon
    amz_bsr_movement:    Optional[float] = None  # positive = rank falling (good)
    amz_stock_pct:       Optional[float] = None  # % of typical stock remaining

    # eBay resale
    ebay_avg_sold_price: Optional[float] = None  # average sold price last 7 days

    # Social
    tiktok_views_7d:     Optional[float] = None  # total views last 7 days
    youtube_views_7d:    Optional[float] = None  # total views last 7 days

    # Forums
    reddit_mentions_7d:  Optional[float] = None  # mention count last 7 days


@dataclass
class ToyScore:
    """Output for one toy after scoring."""
    toy_id:           str
    name:             str
    heat_score:       float
    status:           str
    stock_risk:       str
    resale_flag:      bool
    breakout_flag:    bool
    signal_breakdown: dict = field(default_factory=dict)
    missing_signals:  list = field(default_factory=list)

# ─────────────────────────────────────────────
# NORMALIZATION HELPERS
# ─────────────────────────────────────────────

def _z_score_normalize(values: np.ndarray) -> np.ndarray:
    """
    Normalize a population of raw signal values to z-scores,
    then clip to [-3, 3] and rescale to [0, 100].
    This is the same normalization pattern used in Rook's
    credit_stress.py composite.
    """
    mean = np.nanmean(values)
    std  = np.nanstd(values)

    if std == 0:
        # All values identical — return neutral 50 for all
        return np.full(len(values), 50.0)

    z = (values - mean) / std
    z = np.clip(z, -3, 3)
    normalized = (z + 3) / 6 * 100   # rescale [-3,3] → [0,100]
    return normalized


def _resale_premium(retail_price: float, ebay_price: Optional[float]) -> Optional[float]:
    """
    Compute resale premium as a percentage above retail.
    Returns None if no eBay data available.
    Example: retail $10, eBay $25 → 150.0 (150% premium)
    """
    if ebay_price is None or retail_price <= 0:
        return None
    return max(0.0, (ebay_price - retail_price) / retail_price * 100)


def _social_combined(tiktok: Optional[float], youtube: Optional[float]) -> Optional[float]:
    """Combine TikTok and YouTube views. Use whichever are available."""
    if tiktok is None and youtube is None:
        return None
    return (tiktok or 0) + (youtube or 0)

# ─────────────────────────────────────────────
# POPULATION-LEVEL SCORER
# Normalizes signals across the full toy catalog
# before computing individual scores.
# ─────────────────────────────────────────────

class ToyScorer:
    """
    Score a catalog of toys against each other.

    Usage:
        scorer = ToyScorer()
        scores = scorer.score_all(toy_signals_list)
    """

    def score_all(self, toys: list[ToySignals]) -> list[ToyScore]:
        """
        Main entry point. Takes a list of ToySignals,
        normalizes across the population, computes composite
        heat scores, and returns ToyScore objects.
        """
        if not toys:
            return []

        # ── Step 1: Extract raw signal arrays ──────────────────
        raw = {
            "search_velocity":     np.array([t.search_velocity     or np.nan for t in toys]),
            "search_acceleration": np.array([t.search_acceleration or np.nan for t in toys]),
            "amz_bsr_movement":    np.array([t.amz_bsr_movement    or np.nan for t in toys]),
            "amz_stock_level":     np.array([
                # Invert stock % — low stock = high signal
                (100 - t.amz_stock_pct) if t.amz_stock_pct is not None else np.nan
                for t in toys
            ]),
            "resale_premium":      np.array([
                _resale_premium(t.retail_price, t.ebay_avg_sold_price) or np.nan
                for t in toys
            ]),
            "social_velocity":     np.array([
                _social_combined(t.tiktok_views_7d, t.youtube_views_7d) or np.nan
                for t in toys
            ]),
            "forum_mentions":      np.array([t.reddit_mentions_7d or np.nan for t in toys]),
        }

        # ── Step 2: Normalize each signal across the population ─
        normalized = {}
        for signal_name, values in raw.items():
            normalized[signal_name] = _z_score_normalize(values)

        # ── Step 3: Score each toy ──────────────────────────────
        results = []
        for i, toy in enumerate(toys):
            results.append(
                self._score_single(toy, i, normalized, raw)
            )

        return results


    def _score_single(
        self,
        toy: ToySignals,
        idx: int,
        normalized: dict,
        raw: dict,
    ) -> ToyScore:
        """Compute heat score and all flags for one toy."""

        # ── Weighted composite (with missing signal redistribution) ──
        total_weight   = 0.0
        weighted_sum   = 0.0
        missing        = []
        breakdown      = {}

        for signal_name, weight in WEIGHTS.items():
            raw_val = raw[signal_name][idx]

            if np.isnan(raw_val):
                missing.append(signal_name)
                continue   # skip — weight redistributed below

            norm_val      = normalized[signal_name][idx]
            contribution  = norm_val * weight
            weighted_sum += contribution
            total_weight += weight
            breakdown[signal_name] = round(contribution, 2)

        # Redistribute missing weights proportionally
        if total_weight == 0:
            heat_score = 0.0
        else:
            heat_score = min(100.0, max(0.0, weighted_sum / total_weight))
            heat_score = round(heat_score, 1)

        # ── Status classification ────────────────────────────────
        if heat_score >= HEAT_THRESHOLDS["Peak Demand"]:
            status = "Peak Demand"
        elif heat_score >= HEAT_THRESHOLDS["Rising Fast"]:
            status = "Rising Fast"
        else:
            status = "Emerging"

        # ── Stock risk ───────────────────────────────────────────
        stock_pct = toy.amz_stock_pct
        if stock_pct is None:
            stock_risk = "Unknown"
        elif stock_pct < STOCK_RISK_THRESHOLDS["Critical"]:
            stock_risk = "Critical"
        elif stock_pct < STOCK_RISK_THRESHOLDS["High"]:
            stock_risk = "High"
        elif stock_pct < STOCK_RISK_THRESHOLDS["Medium"]:
            stock_risk = "Medium"
        else:
            stock_risk = "Low"

        # ── Resale flag ──────────────────────────────────────────
        premium = _resale_premium(toy.retail_price, toy.ebay_avg_sold_price)
        resale_flag = (premium is not None) and (
            toy.ebay_avg_sold_price > toy.retail_price * RESALE_FLAG_MULTIPLIER
        )

        # ── Breakout flag ────────────────────────────────────────
        # Emerging toy that's accelerating = get ahead of it
        breakout_flag = (
            status == "Emerging"
            and heat_score >= BREAKOUT_THRESHOLD
        )

        return ToyScore(
            toy_id           = toy.toy_id,
            name             = toy.name,
            heat_score       = heat_score,
            status           = status,
            stock_risk       = stock_risk,
            resale_flag      = resale_flag,
            breakout_flag    = breakout_flag,
            signal_breakdown = breakdown,
            missing_signals  = missing,
        )


# ─────────────────────────────────────────────
# EXAMPLE USAGE / SMOKE TEST
# Run: python toy_scoring.py
# ─────────────────────────────────────────────

if __name__ == "__main__":

    # Simulated signals — replace with live API data in production
    sample_toys = [
        ToySignals(
            toy_id="needoh-nice-cube",
            name="NeeDoh Nice Cube",
            retail_price=8.99,
            search_velocity=92,
            search_acceleration=28,
            amz_bsr_movement=450,
            amz_stock_pct=8,              # critically low
            ebay_avg_sold_price=24.00,    # ~2.7x retail → resale flag
            tiktok_views_7d=4_200_000,
            youtube_views_7d=1_800_000,
            reddit_mentions_7d=312,
        ),
        ToySignals(
            toy_id="jellycat-lazulia-dragon",
            name="Jellycat Lazulia Dragon",
            retail_price=75.00,
            search_velocity=78,
            search_acceleration=15,
            amz_bsr_movement=210,
            amz_stock_pct=22,
            ebay_avg_sold_price=130.00,   # ~1.7x retail
            tiktok_views_7d=2_100_000,
            youtube_views_7d=540_000,
            reddit_mentions_7d=188,
        ),
        ToySignals(
            toy_id="needoh-sugar-skull-cats",
            name="NeeDoh Sugar Skull Cool Cats",
            retail_price=7.99,
            search_velocity=41,
            search_acceleration=22,       # accelerating fast despite low base
            amz_bsr_movement=80,
            amz_stock_pct=55,
            ebay_avg_sold_price=95.00,    # ~11.9x retail → massive resale flag
            tiktok_views_7d=380_000,
            youtube_views_7d=None,        # no YouTube data yet
            reddit_mentions_7d=47,
        ),
        ToySignals(
            toy_id="pokemon-30th-booster",
            name="Pokémon 30th Anniversary Booster",
            retail_price=15.99,
            search_velocity=85,
            search_acceleration=10,
            amz_bsr_movement=320,
            amz_stock_pct=12,
            ebay_avg_sold_price=28.00,    # ~1.75x retail
            tiktok_views_7d=3_500_000,
            youtube_views_7d=2_200_000,
            reddit_mentions_7d=540,
        ),
    ]

    scorer = ToyScorer()
    scores = scorer.score_all(sample_toys)

    print("\n" + "═" * 62)
    print("  TOYRADAR — HEAT SCORE REPORT")
    print("═" * 62)

    for s in sorted(scores, key=lambda x: x.heat_score, reverse=True):
        print(f"\n  {s.name}")
        print(f"  {'─' * 40}")
        print(f"  Heat Score   : {s.heat_score:.1f} / 100")
        print(f"  Status       : {s.status}")
        print(f"  Stock Risk   : {s.stock_risk}")
        print(f"  Resale Flag  : {'⚠️  YES' if s.resale_flag else 'No'}")
        print(f"  Breakout Flag: {'🌱 YES' if s.breakout_flag else 'No'}")
        if s.missing_signals:
            print(f"  Missing Data : {', '.join(s.missing_signals)}")
        print(f"  Signal Breakdown:")
        for sig, val in s.signal_breakdown.items():
            bar = "█" * int(val * 20)
            print(f"    {sig:<22} {val:5.2f}  {bar}")

    print("\n" + "═" * 62 + "\n")
