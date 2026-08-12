# CC News Desk

India credit card intelligence dashboard — live feed of devaluations, offers, launches, social buzz, and benefit updates.

## How it works

1. **GitHub Actions** runs `harvester.py` every 2 hours, scraping 17 RSS feeds, Google News, Reddit, Twitter/Nitter, and TechnoFino Forum.
2. The output (`feed.json`) is committed back to the repo automatically.
3. **GitHub Pages** serves `index.html`, which fetches `feed.json` on load and auto-refreshes every 30 minutes.

## Setup

### 1. Create the repo
Push this folder to a new **private** GitHub repository.

```bash
git init
git add .
git commit -m "init"
gh repo create cc-news-desk --private --source=. --push
```

### 2. Enable GitHub Pages
Go to **Settings → Pages → Source → Deploy from branch → main / (root)** and save.

> GitHub Pages on private repos requires **GitHub Pro** ($4/mo). If you're on the free plan, either make the repo public or connect it to Netlify/Vercel (both have free tiers with private repo support).

### 3. Populate feed.json for the first time
Go to **Actions → Harvest CC News → Run workflow** and click **Run workflow**. This runs the harvester immediately and commits the first `feed.json`. After that it runs automatically every 2 hours.

### 4. Open the dashboard
Your dashboard will be live at:
```
https://<your-github-username>.github.io/cc-news-desk/
```

## Running the harvester locally

```bash
pip install -r requirements.txt
python harvester.py
```

This writes `feed.json` in the same directory. Open `index.html` in a browser to view it (you may need a local server due to CORS — `python -m http.server 8080` works).

## Data sources

| Type | Sources |
|------|---------|
| RSS feeds | CardExpert, CardInsider, CardTrail, LiveFromALounge, SpendWisely, SaveSage, CardInfo, CreditCardz, CardMaven, DesiPoints, Monzy, Desidime, Business Standard, Economic Times, Mint, BankBazaar, Paisabazaar |
| Google News | 9 targeted queries for launches, devaluations, offers, and benefits |
| Reddit | r/CreditCardsIndia, r/IndiaInvestments, r/personalfinanceindia |
| Twitter/X | 6 handles via Nitter mirrors (best-effort) |
| Forum | TechnoFino Community |
| Issuer offer pages | Axis Bank, HSBC, Kotak, BOBCard — scraped daily via `issuer_offers.py`, see below |

### Issuer offer pages (`issuer_offers.py`)

In addition to news/social sources, `harvester.py` scrapes each issuer's own
official "offers" page directly for live merchant deals (cashback, discount
codes, EMI offers, etc.), so `deals.json` reflects what banks are actually
advertising today, not just what bloggers wrote about.

Only issuers whose offers page returns real offer data in the initial HTTP
response (no bot-protection, no client-side JS rendering) are wired up:

| Issuer | Page |
|---|---|
| Axis Bank | https://www.axisbank.com/offers |
| HSBC | https://www.hsbc.co.in/offers/ |
| Kotak | https://www.kotak.com/en/offers.html |
| BOBCard | https://www.bobcard.co.in/credit-card-offers |

The following issuers were checked and excluded — their offers pages either
block scrapers or require a browser to render:

| Issuer | Reason excluded |
|---|---|
| HDFC Bank | Akamai bot-block (403 on every request) |
| ICICI Bank | Offers grid loads client-side via JS |
| SBI Card | Offers grid loads client-side via JS |
| Yes Bank | SPA shell — "requires JavaScript" |
| IndusInd Bank | Offers URL 404s; no working path found |
| AU Small Finance Bank | Bot-block (403) |
| RBL Bank | Only a static teaser banner; real grid is JS-rendered |
| Standard Chartered | Offers page lists categories only, no real merchant offers in static HTML |
| IDFC First Bank | `/offers` is a card-product page, not a merchant-deals listing |
| American Express | Offers are gated behind card selection/login |
| Federal Bank | Radware bot-block (CAPTCHA wall) |
| IDBI Bank | `/offers` redirects to the homepage |

Adding a new issuer later just means writing a `_parse_<issuer>()` function
in `issuer_offers.py` and registering it in `ISSUER_OFFER_SOURCES` — the
excluded ones above would need a headless-browser fetch (e.g. Playwright),
which isn't part of this project yet.
