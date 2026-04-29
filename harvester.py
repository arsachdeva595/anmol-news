#!/usr/bin/env python3
"""
CreditCardNewsHarvester — India
Scrapes RSS feeds, Google News, Reddit, and Nitter (Twitter mirrors)
for Indian credit card news and writes a deduplicated feed.json.

Usage:
    python harvester.py

Output:
    feed.json  —  list of items sorted newest-first
"""

import hashlib
import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import feedparser
import requests
from bs4 import BeautifulSoup

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
OUTPUT_PATH = Path(__file__).parent / "feed.json"
USER_AGENT  = "CreditCardNewsHarvester/0.1 (+https://github.com/yourname/cc-news)"
REQUEST_TIMEOUT = 15

# RSS / Atom feeds
RSS_SOURCES = [
    {
        "name": "CardExpert",
        "url":  "https://cardexpert.in/feed/",
        "default_category": "devaluation",
    },
    {
        "name": "CardInsider",
        "url":  "https://cardinsider.com/feed/",
        "default_category": "launch",
    },
    {
        "name": "CardTrail News",
        "url":  "https://cardtrail.in/news/feed/",
        "default_category": "launch",
    },
    {
        "name": "LiveFromALounge",
        "url":  "https://livefromalounge.com/feed/",
        "default_category": "benefit",
    },
    {
        "name": "SpendWisely",
        "url":  "https://spendwisely.in/feed/",
        "default_category": "offer",
    },
    {
        "name": "SaveSage Blog",
        "url":  "https://savesage.club/blogs/feed/",
        "default_category": "benefit",
    },
    {
        "name": "CardInfo",
        "url":  "https://cardinfo.in/feed/",
        "default_category": "offer",
    },
    {
        "name": "CreditCardz",
        "url":  "https://creditcardz.in/feed/",
        "default_category": "launch",
    },
    {
        "name": "CardMaven",
        "url":  "https://cardmaven.in/feed/",
        "default_category": "benefit",
    },
    {
        "name": "DesiPoints",
        "url":  "https://desipoints.com/feed/",
        "default_category": "benefit",
    },
    {
        "name": "Monzy Blog",
        "url":  "https://blog.monzy.co/feed/",
        "default_category": "devaluation",
    },
    {
        "name": "Desidime Credit Cards",
        "url":  "https://www.desidime.com/forums/hot-deals-online/credit-cards-and-banking.atom",
        "default_category": "offer",
    },
    {
        "name": "Business Standard – Credit Card",
        "url":  "https://www.business-standard.com/rss/topic/credit-card.rss",
        "default_category": "launch",
    },
    {
        "name": "Economic Times – Credit Card",
        "url":  "https://economictimes.indiatimes.com/topic/credit-card/rss",
        "default_category": "launch",
    },
    {
        "name": "Mint – Credit Card",
        "url":  "https://www.livemint.com/rss/money",
        "default_category": "launch",
    },
    {
        "name": "BankBazaar Blog",
        "url":  "https://www.bankbazaar.com/blog/feed/",
        "default_category": "offer",
    },
    {
        "name": "Paisabazaar Blog",
        "url":  "https://www.paisabazaar.com/blog/feed/",
        "default_category": "offer",
    },
]

# Google News RSS — multiple targeted queries
GOOGLE_NEWS_QUERIES = [
    ("launch",      '"credit card" India launch'),
    ("devaluation", '"credit card" India devaluation OR revision OR "T&C update"'),
    ("offer",       '"credit card" India offer OR cashback OR sale'),
    ("benefit",     '"credit card" India lounge OR milestone OR "new benefit"'),
    ("devaluation", "HDFC credit card changes"),
    ("devaluation", "Axis credit card revision"),
    ("devaluation", "SBI card devaluation"),
    ("launch",      "new credit card launch India 2025"),
    ("offer",       "credit card cashback offer India bank"),
]

# Reddit subs (JSON endpoints, no auth needed)
REDDIT_SUBS = [
    "CreditCardsIndia",
    "IndiaInvestments",
    "personalfinanceindia",
]

# Twitter / X handles (via Nitter mirrors — best effort)
TWITTER_HANDLES = [
    "amazingcreditc",   # Amazing Credit Cards
    "DoBaniye",         # DoBaniye
    "TechnoFino",       # TechnoFino
    "SpendWiselyX",     # SpendWisely
    "cardexpert_in",    # CardExpert
    "cardtrailin",      # CardTrail
]

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
    "https://nitter.poast.org",
    "https://nitter.1d4.us",
]

# TechnoFino community forum (scraped HTML — best effort)
TECHNOFINO_URLS = [
    "https://technofino.in/community/categories/credit-cards.42/",
]

# -----------------------------------------------------------------------------
# Keyword dictionaries
# -----------------------------------------------------------------------------
KW_CRITICAL = ["devaluation", "discontinued", "withdrawn", "no longer", "removed"]
KW_MAJOR    = ["revision", "revised", "capped", "cap reduced", "reduction"]
KW_MINOR    = ["t&c update", "terms updated", "minor change"]

ISSUERS = {
    "HDFC":                  ["hdfc"],
    "Axis Bank":             ["axis", "magnus", "atlas", "burgundy", "neo"],
    "ICICI Bank":            ["icici", "emeralde", "amazon pay icici"],
    "SBI Card":              ["sbi card", "sbi cards", "aurum", "elite", "prime", "cashback sbi"],
    "Yes Bank":              ["yes bank", "yes private"],
    "IndusInd Bank":         ["indusind", "pinnacle", "indusind legend"],
    "AU Small Finance Bank": ["au bank", "au lit", "au small finance", "au zenith"],
    "RBL Bank":              ["rbl", "lumiere", "shaurya"],
    "Standard Chartered":    ["standard chartered", "stanchart", "smart sc"],
    "Kotak":                 ["kotak", "811", "league infinite"],
    "IDFC First":            ["idfc", "idfc first", "wow black"],
    "American Express":      ["amex", "american express", "platinum amex"],
    "Federal Bank":          ["federal bank", "scapia"],
    "OneCard":               ["onecard", "one card"],
    "HSBC":                  ["hsbc"],
    "Flipkart / Axis":       ["flipkart axis"],
    "Swiggy / HDFC":         ["swiggy hdfc"],
    "Air India / SBI":       ["air india sbi", "air india maharaja"],
    "IndiGo / SBI":          ["indigo sbi", "ka-ching"],
}

CATEGORY_KEYWORDS = {
    "devaluation": KW_CRITICAL + KW_MAJOR + KW_MINOR + ["nerf", "downgrade", "degrade"],
    "offer":       ["cashback", "discount", "off", "deal", "offer", "sale", "bogo", "extra",
                    "voucher code", "promo", "reward bonus", "limited time"],
    "launch":      ["launch", "introducing", "debut", "unveil", "new card", "launches",
                    "announced", "releases", "now available"],
    "benefit":     ["lounge", "milestone", "voucher", "benefit added", "complimentary",
                    "insurance", "golf", "concierge", "reward rate"],
    "social":      [],  # reddit/twitter only
}

# Keywords that confirm an item is about credit cards.
# Items from broad sources (ET, Mint, BS) must match at least one of these.
CC_RELEVANCE = (
    ["credit card", "creditcard", "debit card", "reward point", "reward points",
     "joining fee", "annual fee", "forex markup", "lounge access", "airport lounge",
     "cashback card", "miles card", "travel card", "co-branded card"]
    + [kw for kws in ISSUERS.values() for kw in kws]
    + [kw for cat, kws in CATEGORY_KEYWORDS.items() if cat != "offer" for kw in kws]
)

# -----------------------------------------------------------------------------
# Relevance filtering
# -----------------------------------------------------------------------------
# Terms that strongly signal credit-card content. Used to filter out off-topic
# articles from broad financial sources (BankBazaar, Paisabazaar, Mint, etc.).
CC_RELEVANCE_KEYWORDS = [
    "credit card", "creditcard",
    "cashback", "reward point", "reward rate", "reward program",
    "lounge access", "airport lounge",
    "annual fee", "joining fee",
    "forex markup", "fuel surcharge",
    "milestone benefit", "welcome benefit",
    "card launch", "card devaluation", "card revision",
    "hdfc card", "axis card", "icici card", "sbi card", "amex card",
    "magnus", "atlas", "infinia", "regalia", "tata neu",
]

# RSS source names and Reddit subs that are not CC-specific — filter these.
BROAD_RSS_SOURCES: set[str] = {
    "Mint – Credit Card",
    "BankBazaar Blog",
    "Paisabazaar Blog",
}
BROAD_REDDIT_SUBS: set[str] = {
    "IndiaInvestments",
    "personalfinanceindia",
}


def cc_relevance_score(title: str, snippet: str) -> int:
    """Count how many CC relevance keywords appear in title+snippet."""
    text = f"{title} {snippet}".lower()
    return sum(1 for k in CC_RELEVANCE_KEYWORDS if k in text)


def is_cc_relevant(title: str, snippet: str) -> bool:
    """Return True if the item is plausibly about credit cards."""
    return cc_relevance_score(title, snippet) > 0

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("harvester")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

def uid(url: str, title: str) -> str:
    """Stable dedup key."""
    raw = (url or title or "").strip().lower()
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def is_credit_card_relevant(title: str, snippet: str) -> bool:
    """Return True only if the item is actually about credit cards."""
    text = f"{title} {snippet}".lower()
    return any(k in text for k in CC_RELEVANCE)


def detect_issuers(text: str) -> list[str]:
    text_l = text.lower()
    return [issuer for issuer, kws in ISSUERS.items() if any(k in text_l for k in kws)]


def detect_category(text: str, default: str) -> str:
    text_l = text.lower()
    for cat, kws in CATEGORY_KEYWORDS.items():
        if kws and any(k in text_l for k in kws):
            return cat
    return default


def detect_severity(text: str) -> Optional[str]:
    text_l = text.lower()
    if any(k in text_l for k in KW_CRITICAL):
        return "critical"
    if any(k in text_l for k in KW_MAJOR):
        return "major"
    if any(k in text_l for k in KW_MINOR):
        return "minor"
    return None


def normalize_dt(entry) -> str:
    """Extract ISO-8601 UTC datetime string from a feedparser entry."""
    for field in ("published_parsed", "updated_parsed", "created_parsed"):
        t = getattr(entry, field, None)
        if t:
            try:
                return datetime(*t[:6], tzinfo=timezone.utc).isoformat()
            except Exception:
                pass
    return datetime.now(timezone.utc).isoformat()


def make_item(title, url, source, category, published, snippet="", extra=None) -> Optional[dict]:
    if not title.strip():
        return None
    if not is_credit_card_relevant(title, snippet):
        return None
    text = f"{title} {snippet}"
    return {
        "uid":             uid(url, title),
        "title":           title.strip(),
        "url":             url.strip(),
        "source":          source,
        "category":        detect_category(text, category),
        "issuers":         detect_issuers(text),
        "severity":        detect_severity(text),
        "published":       published,
        "snippet":         snippet[:300],
        "relevance_score": cc_relevance_score(title, snippet),
        **(extra or {}),
    }


def safe_get(url: str, headers: dict = None, timeout: int = REQUEST_TIMEOUT) -> Optional[requests.Response]:
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    try:
        r = requests.get(url, headers=h, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning("GET failed (%s): %s", url, e)
        return None


# -----------------------------------------------------------------------------
# Scrapers
# -----------------------------------------------------------------------------

def fetch_rss(source: dict) -> list[dict]:
    log.info("RSS → %s", source["name"])
    broad = source["name"] in BROAD_RSS_SOURCES
    items = []
    try:
        feed = feedparser.parse(
            source["url"],
            request_headers={"User-Agent": USER_AGENT},
        )
        for e in feed.entries[:30]:
            title   = getattr(e, "title",   "") or ""
            link    = getattr(e, "link",    "") or ""
            summary = getattr(e, "summary", "") or ""
            snippet = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
            items.append(make_item(
                title=title,
                url=link,
                source=source["name"],
                category=source["default_category"],
                published=normalize_dt(e),
                snippet=snippet,
            )
            if item:
                items.append(item)
    except Exception as e:
        log.warning("RSS parse error (%s): %s", source["name"], e)
    return items


def fetch_google_news(label: str, query: str) -> list[dict]:
    log.info("Google News → %s (%s)", label, query)
    items = []
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url, request_headers={"User-Agent": USER_AGENT})
        for e in feed.entries[:20]:
            title   = getattr(e, "title",   "") or ""
            link    = getattr(e, "link",    "") or ""
            summary = getattr(e, "summary", "") or ""
            snippet = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
            item = make_item(
                title=title,
                url=link,
                source=f"Google News / {label}",
                category=label,
                published=normalize_dt(e),
                snippet=snippet,
            )
            if item:
                items.append(item)
    except Exception as e:
        log.warning("Google News error (%s): %s", query, e)
    return items


def fetch_reddit(sub: str) -> list[dict]:
    log.info("Reddit → r/%s", sub)
    items = []
    url = f"https://www.reddit.com/r/{sub}/new.json?limit=25"
    r = safe_get(url, headers={"User-Agent": f"{USER_AGENT} (reddit scraper)"})
    if not r:
        return items
    broad = sub in BROAD_REDDIT_SUBS
    try:
        posts = r.json().get("data", {}).get("children", [])
        for p in posts:
            d = p.get("data", {})
            title  = d.get("title", "")
            link   = "https://reddit.com" + d.get("permalink", "")
            body   = d.get("selftext", "")[:300]
            ts     = d.get("created_utc")
            pub    = datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() if ts else datetime.now(timezone.utc).isoformat()
            items.append(make_item(
                title=title,
                url=link,
                source=f"Reddit / r/{sub}",
                category="social",
                published=pub,
                snippet=body,
                extra={"score": d.get("score", 0), "comments": d.get("num_comments", 0)},
            )
            if item:
                items.append(item)
    except Exception as e:
        log.warning("Reddit parse error (r/%s): %s", sub, e)
    return items


def fetch_nitter(handle: str) -> list[dict]:
    """Try each Nitter instance until one works."""
    items = []
    for base in NITTER_INSTANCES:
        url = f"{base}/{handle}/rss"
        r = safe_get(url, timeout=10)
        if not r:
            continue
        try:
            feed = feedparser.parse(r.text)
            if not feed.entries:
                continue
            log.info("Nitter (%s) → @%s — %d tweets", base, handle, len(feed.entries))
            for e in feed.entries[:15]:
                title   = getattr(e, "title",   "") or ""
                link    = getattr(e, "link",    "") or ""
                summary = getattr(e, "summary", "") or ""
                snippet = BeautifulSoup(summary, "html.parser").get_text(" ", strip=True)
                items.append(make_item(
                    title=title,
                    url=link,
                    source=f"Twitter / @{handle}",
                    category="social",
                    published=normalize_dt(e),
                    snippet=snippet,
                )
                if item:
                    items.append(item)
            break  # success — no need to try next instance
        except Exception as ex:
            log.warning("Nitter parse error (%s @%s): %s", base, handle, ex)
    if not items:
        log.warning("All Nitter instances failed for @%s", handle)
    return items


def fetch_technofino() -> list[dict]:
    """Scrape TechnoFino community thread listings."""
    items = []
    for url in TECHNOFINO_URLS:
        log.info("TechnoFino scrape → %s", url)
        r = safe_get(url)
        if not r:
            continue
        try:
            soup = BeautifulSoup(r.text, "html.parser")
            # XenForo thread list structure
            for thread in soup.select("div.structItem--thread")[:20]:
                title_el = thread.select_one("div.structItem-title a[data-tp-primary]") or \
                           thread.select_one("div.structItem-title a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href  = title_el.get("href", "")
                link  = f"https://technofino.in{href}" if href.startswith("/") else href
                items.append(make_item(
                    title=title,
                    url=link,
                    source="TechnoFino Forum",
                    category="social",
                    published=datetime.now(timezone.utc).isoformat(),
                    snippet="",
                )
                if item:
                    items.append(item)
        except Exception as e:
            log.warning("TechnoFino scrape error: %s", e)
    return items


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def run() -> None:
    all_items: list[dict] = []

    # 1. RSS feeds
    for src in RSS_SOURCES:
        all_items.extend(fetch_rss(src))
        time.sleep(0.5)

    # 2. Google News
    for label, query in GOOGLE_NEWS_QUERIES:
        all_items.extend(fetch_google_news(label, query))
        time.sleep(0.5)

    # 3. Reddit
    for sub in REDDIT_SUBS:
        all_items.extend(fetch_reddit(sub))
        time.sleep(1)

    # 4. Twitter / Nitter
    for handle in TWITTER_HANDLES:
        all_items.extend(fetch_nitter(handle))
        time.sleep(1)

    # 5. TechnoFino community
    all_items.extend(fetch_technofino())

    # Deduplicate by uid
    seen: set[str] = set()
    deduped: list[dict] = []
    for item in all_items:
        if item["uid"] not in seen:
            seen.add(item["uid"])
            deduped.append(item)

    # Sort newest-first, then by relevance score descending within the same timestamp
    deduped.sort(key=lambda x: (x.get("published", ""), x.get("relevance_score", 0)), reverse=True)

    # Write output
    OUTPUT_PATH.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(), "items": deduped}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("Done. %d items → %s", len(deduped), OUTPUT_PATH)


if __name__ == "__main__":
    run()
