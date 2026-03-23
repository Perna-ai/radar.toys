# radar.toys — Full Project Summary

## 💡 The Idea

- Build a website that tracks toy trends for kids and parents
- Surfaces what’s hot **right now**, what’s **about to blow up**, and **where to buy** before it sells out
- Primary users: both kids and parents equally
- Core features: trend tracking, prediction, availability alerts
- Monetization: TBD, eventually affiliate links and retailer partnerships

-----

## 🎯 The Strategy

### Three-Phase Business Plan

1. **Phase 1 (Months 1–6)** — Be the source of truth. Track what’s hot now, build the audience
1. **Phase 2 (Months 6–12)** — Add the intelligence layer. Use your own traffic data to predict breakouts
1. **Phase 3 (Month 12+)** — Monetize. Affiliate links → retailer partnerships → trend data licensing

### Monetization Roadmap

- Affiliate links (Amazon Associates) — start here, invisible to users
- Retailer partnerships — “Trending on radar.toys” becomes a badge brands want
- Email alert premium tier
- B2B trend data licensing to toy brands and retailers

### Signal Sources

- Google Trends (search velocity + acceleration)
- eBay sold listings (resale premium — strongest leading indicator)
- Amazon BSR movement + stock levels
- TikTok + YouTube view velocity
- Reddit/parenting forum mentions

-----

## 🧸 Real Trending Toys (Research)

- **NeeDoh Nice Cube** by Schylling — #1 trending, $5–15 retail, selling out nationwide
- **NeeDoh Dream Drop** — teardrop variant, certain colorways already gone
- **NeeDoh Sugar Skull Cool Cats** — $7 retail, $95 on eBay resale — massive breakout signal
- **Jellycat Lazulia Dragon** — Spring 2026 drop, ~$75, already a collector must-have
- **Jellycat Amuseables Carrot Cake** — ~$30, from London/Paris pop-up to global release
- **Pokémon 30th Anniversary Booster Packs** — $15–45, selling out in minutes at Target/Walmart

-----

## 🎨 Design & Mockups Built

### Coming Soon Page (`index.html`)

- Mobile-first single HTML file, ready to deploy
- **Logo:** RADAR in violet/purple gradient · .TOYS in coral/orange gradient · Bebas Neue font
- **Tagline:** “Know first. Buy first.”
- **Headline:** “Know what kids want before they ask.”
- **CTA Button:** “I Want Early Access →”
- **Social proof chips:** Real urgency statements (NeeDoh selling out, $7 vs $95 eBay)
- **Ticker:** Purple gradient bar, yellow Bebas Neue text, coral bullet separators — 9 punchy hooks auto-scrolling
- **Animated blob background** with noise texture overlay
- **Email signup** connected to Mailchimp (API ready)

### Main Site Mockup (`toyradar-colorful.jsx`)

- Mobile-first React component
- Live ticker, sticky nav, hero card, age filter chips, toy cards, predictions section, email signup
- Toy cards show: trend heat bar, status tag, price, where to buy (tap to expand)
- Color system: violet/purple, coral/orange, yellow

### Architecture Diagram (`toyradar-architecture.jsx`)

- Interactive 4-layer diagram
- Tap each layer to expand details
- Includes tech stack and estimated monthly cost (~$110–220/mo)

-----

## 🤖 The AI Agent Architecture

### Four Automated Layers

1. **Data Collection** — Python scripts, cron every 15–60 min
1. **Trend Scoring Engine** — Weighted z-score composite, runs after each data pull
1. **Claude Synthesis** — Writes all content, runs 2x daily
1. **Publishing & Alerts** — Fully automated, zero human needed

### What Still Needs a Human

- Weekly quality review (~30 min)
- Retailer and brand partnerships
- Fixing broken data sources
- New signal source strategy

### Estimated Monthly Cost

- Claude API (Sonnet): ~$30–60/mo
- Data APIs: ~$50–100/mo
- Hosting + database: ~$20–40/mo
- Email platform: ~$10–20/mo
- **Total: ~$110–220/mo**

-----

## 🐍 Code Built

### `toy_scoring.py` — Trend Scoring Engine

- 7 signals across 5 sources, weights summing to 1.0
- Z-score normalization across toy population (same pattern as Rook’s `credit_stress.py`)
- Outputs: heat score (0–100), status, stock risk, resale flag, breakout flag
- Missing data handled gracefully — weights redistributed
- Thresholds: Peak Demand (80+), Rising Fast (55+), Emerging (0–54)

### `collectors.py` — Data Collection Layer

- `GoogleTrendsCollector` — free, no API key, search velocity + acceleration
- `AmazonCollector` — BSR movement + stock level via RapidAPI (~$50/mo)
- `EbayCollector` — sold listings avg price, free eBay developer account
- `SocialCollector` — TikTok + YouTube view velocity
- `RedditCollector` — mention count across 8 parenting subreddits, free
- `DataCollectionRunner` — master orchestrator, saves to Supabase
- `TOY_CATALOG` — add a new toy in 5 seconds, everything else is automatic
- Cron schedule: every 30 min, 6am–midnight

### `synthesizer.py` — Claude Synthesis Layer

- Reads heat scores from Supabase, calls Claude Sonnet for all content
- **4 tasks per toy:** card description, prediction narrative, alert email, anomaly check
- Prompts are tightly constrained — JSON only, never invent facts
- Alert logic: only fires on 3 specific thresholds (stock critical, resale spike, breakout)
- Weekly digest auto-generated every Monday
- Cron schedule: 8am and 8pm daily

### Full Pipeline

```
collectors.py → Supabase → toy_scoring.py → synthesizer.py → site
  every 30min     (DB)        on each run       2x daily     auto-publish
```

-----

## 🌐 Domain & Brand

- **Domain registered:** `radar.toys` ✅
- **Tagline:** Know first. Buy first.
- **Color system:** Violet/purple, coral/orange, yellow
- **Fonts:** Bebas Neue (logo + ticker), Syne (headlines), DM Sans (body), Space Mono (labels)
- Domains checked and rejected: toyradar.com (taken), thetoyradar.com (taken), toyradar.it.com (not a real TLD)

-----

## 🛠️ Tech Stack

|Layer          |Technology                         |
|---------------|-----------------------------------|
|Frontend       |React (JSX)                        |
|Hosting        |Vercel (free tier)                 |
|Database       |Supabase (Postgres, free tier)     |
|Data scripts   |Python + cron                      |
|Scoring        |Python (weighted z-score)          |
|AI synthesis   |Claude Sonnet via Anthropic API    |
|Email          |Mailchimp (free to 500 subscribers)|
|Version control|GitHub                             |

-----

## 🚀 Launch Plan

### While on Vacation (Browser Only)

- [ ] Create GitHub account + radar-toys repo
- [ ] Upload all 5 project files + CLAUDE.md
- [ ] Create Vercel account, deploy index.html, connect radar.toys domain
- [ ] Create Mailchimp account, create audience list, save API key + Audience ID
- [ ] Create Supabase account, create project, run schema, save credentials
- [ ] Post in one parenting Facebook group
- [ ] Share the $7 vs $95 eBay story on personal social

### When Back on Mac Mini (Claude Code)

- Wire React site to Supabase (live data)
- Connect Mailchimp to email signup form
- Get collectors.py running — Google Trends + Reddit first (free)
- Add eBay collector
- Set up cron jobs
- Deploy full site, replace coming soon page

-----

## 🤖 Claude Code Plan

- **No developer needed** — Claude Code handles all technical execution
- Runs in terminal on Mac mini, integrates with Claude Desktop (already installed)
- $20/month on Claude Pro — likely already have access
- CLAUDE.md file gives it full project context automatically on every session
- First session instruction: *“Read all files, connect Supabase, wire up Mailchimp, deploy the main site”*

### Division of Labor

- **Claude Code** — all technical wiring, deployment, debugging, API connections
- **You** — judgment calls, toy curation, copy decisions, brand relationships, strategy
- **Claude in conversation** — thinking partner, architecture, content, refinements

-----

## 📁 Files Built Today

|File                       |Description                           |
|---------------------------|--------------------------------------|
|`index.html`               |Coming soon page — ready to deploy    |
|`toyradar-colorful.jsx`    |Full mobile site mockup with real toys|
|`toyradar-architecture.jsx`|Interactive agent architecture diagram|
|`toy_scoring.py`           |Heat score engine                     |
|`collectors.py`            |5-source data collection layer        |
|`synthesizer.py`           |Claude synthesis + content generation |
|`checklist.html`           |Interactive vacation launch checklist |
