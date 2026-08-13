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
| Issuer offer pages | Axis Bank, HSBC, Kotak, BOBCard, SBI Card, ICICI Bank — scraped daily via `issuer_offers.py`, see below |

### Issuer offer pages (`issuer_offers.py`)

In addition to news/social sources, `harvester.py` scrapes each issuer's own
official "offers" page directly for live merchant deals (cashback, discount
codes, EMI offers, etc.), so `deals.json` reflects what banks are actually
advertising today, not just what bloggers wrote about.

**Scope: credit card offers only.** Several issuer pages mix in debit-card
and net-banking offers alongside credit card ones — each parser filters on
whatever payment-method signal that source exposes (Axis's per-card tag,
ICICI's `paymentGatewayValue` field, a text heuristic for HSBC). BOBCard and
SBI Card need no filtering since both entities issue credit cards only.
Kotak needed the opposite fix: its bare `/offers.html` silently defaults to
just the "Credit Card EMI" bucket, missing a second, entirely disjoint
"Credit Card" bucket — both are now fetched and merged, and
`paymentType=debit` is never queried.

A source qualifies if real offer data is reachable via a plain `requests`
call — no headless browser needed at run time — as server-rendered DOM
(Axis, HSBC, Kotak), a JSON/JS variable embedded in an inline `<script>`
(BOBCard, SBI Card), or a JSON API endpoint the page's own JS calls (ICICI —
found via a one-off Playwright network-inspection session; the endpoint
itself just takes a plain GET, so no browser is needed at run time):

| Issuer | Page |
|---|---|
| Axis Bank | https://www.axis.bank.in/offers/ |
| HSBC | https://www.hsbc.co.in/offers/ |
| Kotak | https://www.kotak.com/en/offers.html |
| BOBCard | https://www.bobcard.co.in/credit-card-offers |
| SBI Card | https://www.sbicard.com/en/personal/offers.page |
| ICICI Bank | icici.bank.in's offer-search JSON API (small, ~5 curated offers) |

Many issuers now also serve the same offers page from a newer
`<issuer>.bank.in` domain (RBI's bank-domain initiative). Axis, Kotak, HSBC,
and Amex were re-checked there and returned byte-identical content to their
`.com` equivalents — no functional difference.

The following issuers were checked and excluded — their offers pages either
block scrapers or genuinely have no merchant offer data available, on the
public web, in any form:

| Issuer | Reason excluded |
|---|---|
| HDFC Bank | Grid is client-side JS with nothing embedded (hdfcbank.com is also Akamai bot-blocked; hdfc.bank.in loads but is empty) |
| Yes Bank | SPA shell that resolves to a 404 template |
| IndusInd Bank | Confirmed via full headless-browser render (Playwright, networkidle wait) — zero offer content anywhere on any URL variant tried. Not a rendering problem, there's just nothing there. |
| AU Small Finance Bank | Bot-block (403) on every domain tried |
| RBL Bank | Confirmed via headless render — only the same static teaser banner; the real grid is genuinely mobile-app-only ("Visit RBL MyBank App" is the page's own text) |
| Standard Chartered | Offers page lists categories only, no real merchant offers in static HTML |
| IDFC First Bank | Confirmed via headless render — every `/offers` URL, including "credit-card-merchant-offers", only ever renders the card-product mega-menu, never a merchant-deals grid |
| American Express | Offers are gated behind card selection/login |
| Federal Bank | Radware bot-block (CAPTCHA wall) |
| IDBI Bank | `/offers` redirects to the homepage |

IndusInd, RBL, and IDFC First were specifically re-checked with a real
headless browser to rule out "just needs JS to render" as the explanation —
none of them have merchant offer data available on the public web at all,
so adding a browser dependency wouldn't help. Playwright was useful as a
one-off diagnostic tool (it's how ICICI's JSON endpoint was found, via its
network tab) but **is not a project dependency** — nothing here needs it at
run time, so `requirements.txt` and the GitHub Actions workflow are
unchanged.

Adding a new issuer later just means writing a `_parse_<issuer>()` function
in `issuer_offers.py` and registering it in `ISSUER_OFFER_SOURCES` — check
inline `<script>` tags *and* the browser network tab for a plain JSON blob
or API endpoint before assuming a JS-rendered grid is a dead end (that's how
BOBCard, SBI Card, and ICICI were all cracked without a runtime browser
dependency).
