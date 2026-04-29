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
