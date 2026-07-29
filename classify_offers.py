#!/usr/bin/env python3
"""
classify_offers.py — reads feed.json (from harvester.py) and writes deals.json
containing ONLY genuine promotional offers: an extra discount, cashback, or an
added/complimentary benefit. It filters OUT:
  - comparison / upgrade-advice / review / guide / listicle posts
  - devaluation & rule-change posts (those are CHANGES, not offers)
  - social cruft (retweets, replies, hashtag-only posts, follow/pin/masterlink spam)

Community (Twitter/Reddit) posts are kept ONLY if they carry a hard numeric
signal (a % or ₹ off/cashback), which strips the chatter while keeping real
community-sourced deals.

Run after harvester.py in the same Action:
    python harvester.py
    python classify_offers.py
Output: deals.json -> {"generated_at","count","deals":[...]} newest first,
each with a deal_type of "cashback" | "discount" | "benefit".
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FEED_PATH = Path(__file__).parent / "feed.json"
OUT_PATH = Path(__file__).parent / "deals.json"

# Keep community posts, but only when they carry a hard number (see HARD below).
INCLUDE_SOCIAL = True

# Soft promo/benefit signals — enough on their own for a blog/news item.
POSITIVE = [
    r"\b\d{1,3}\s*%\s*(?:off|cashback|discount|back|rewards?)\b",
    r"\bflat\s*(?:₹|rs\.?\s*)?\d", r"\bup\s*to\s*(?:₹|rs\.?\s*)?\d",
    r"(?:₹|rs\.?\s*)\d[\d,]*\s*(?:off|cashback|back)\b",
    r"\binstant\s+discount\b", r"\bcashback\b",
    r"\bwelcome\s+(?:offer|benefit|bonus|voucher)\b",
    r"\bmilestone\s+(?:benefit|offer|reward|voucher)\b",
    r"\b\d+\s*x\s+[a-z]", r"\bearn\s+(?:up\s+to\s+)?\d",
    r"\bno[\s-]*cost\s+emi\b", r"\b(?:coupon|promo)\s*code\b",
    r"\blimited[\s-]*time\b", r"\b(?:sale|voucher|gift\s*card)\b",
    r"\bextra\s+\d", r"\bcomplimentary\b",
    r"\bfree\s+(?:lounge|voucher|night|membership|movie|esim)\b",
]

# Hard numeric signal — the only thing that lets a social post through.
HARD = re.compile(
    r"\d{1,3}\s*%\s*(?:off|cashback|discount|back|rewards?)"
    r"|(?:₹|rs\.?\s*)\d[\d,]*\s*(?:off|cashback|back)"
    r"|\binstant\s+discount\b|\bflat\s*\d|\bno[\s-]*cost\s+emi\b", re.I)

# Comparison / advice / review / guide / listicle — exclude.
NEGATIVE = [
    r"\bvs\.?\b", r"\bversus\b", r"\bshould\s+(?:i|you)\b",
    r"\bwhich\s+(?:card|is|one|credit)\b", r"\breview\b",
    r"\bcomparison\b", r"\bcompared?\b", r"\beligibilit", r"\bhow\s+to\b",
    r"\b(?:complete\s+)?guide\b", r"\bworth\s+it\b",
    r"\bbest\b[^.\n]{0,30}\bcards?\b", r"\btop\s+\d+\b[^.\n]{0,30}\bcards?\b",
    r"\bfeatures\s+of\b", r"\bbenefits\s+of\b",
    r"\bmy\s+experience\b", r"\bstatus\s+match\b", r"\btrip\s+report\b",
    r"\bdid\s+you\s+know\b",
]

# Devaluation / rule-change — a change, not an offer. Exclude from deals.
DEVALUATION = [
    r"devalu", r"\bnerf", r"\bcapp?ed\b", r"\bcaps\b",
    r"\brevis(?:ed|ion|ing)\b", r"\breduc(?:e|ed|tion|ing)\b",
    r"\bremov(?:e|ed|al|ing)\b", r"\bwithdraw", r"\bdiscontinu",
    r"\bno\s+longer\b", r"\bnew\s+rules\b", r"\brule\s+changes?\b",
    r"\bno\s+major\s+blow\b", r"\bdowngrad", r"\bno\s+airport\s+lounge\b",
    r"cut(?:s|ting)?\s+(?:cashback|reward|lounge|benefit)",
    r"(?:cashback|lounge|reward)[^.\n]{0,25}(?:revis|remov|capp|reduc|slash|ends?\b)",
    r"golden\s+era[^.\n]{0,25}end",
]

# Social cruft.
NOISE = [
    r"\bmasterlink\b", r"\bgrab\s+if\s+needed\b",
    r"\bfollow\s+@", r"\bpinned\b", r"^\s*rt\b", r"\br\s+to\s+@",
]

POS_RE = [re.compile(p, re.I) for p in POSITIVE]
NEG_RE = [re.compile(n, re.I) for n in NEGATIVE]
DEV_RE = [re.compile(d, re.I) for d in DEVALUATION]
NOISE_RE = [re.compile(n, re.I) for n in NOISE]


def any_match(res, text):
    return any(r.search(text) for r in res)


def is_noise(title, text):
    if any_match(NOISE_RE, text):
        return True
    words = [w for w in title.split() if not w.startswith("#") and not w.startswith("@")]
    if title.count("#") >= 3 and len(words) <= 4:   # hashtag-only posts
        return True
    return False


def is_social(item, title):
    src = (item.get("source") or "").lower()
    return src.startswith("twitter") or src.startswith("reddit") or \
        bool(re.search(r"\brt\s+by\s+@|\brt\s+@|^\s*r\s+to\s+@", title, re.I))


def deal_type(text):
    t = text.lower()
    if "cashback" in t:
        return "cashback"
    if re.search(r"%|\bflat\b|discount|\bsale\b|\boff\b|voucher|coupon", t):
        return "discount"
    return "benefit"


def classify(item):
    title = item.get("title", "") or ""
    text = f"{title} {item.get('snippet', '')}"
    if any_match(DEV_RE, text):      return None    # devaluation / rule change
    if is_noise(title, text):        return None    # social cruft
    if any_match(NEG_RE, text):      return None    # comparison / advice / guide
    if is_social(item, title):
        if not INCLUDE_SOCIAL or not HARD.search(text):
            return None                             # community needs a hard number
    elif not any_match(POS_RE, text):
        return None                                 # blog/news needs a promo signal
    return deal_type(text)


def run():
    if not FEED_PATH.exists():
        print("feed.json not found — run harvester.py first."); return
    items = json.loads(FEED_PATH.read_text(encoding="utf-8")).get("items", [])
    deals = []
    for it in items:
        dt = classify(it)
        if not dt:
            continue
        deals.append({
            "uid": it.get("uid"), "title": it.get("title"), "url": it.get("url"),
            "source": it.get("source"), "issuers": it.get("issuers", []),
            "deal_type": dt, "published": it.get("published"), "snippet": it.get("snippet", ""),
        })
    deals.sort(key=lambda x: x.get("published", ""), reverse=True)
    OUT_PATH.write_text(json.dumps(
        {"generated_at": datetime.now(timezone.utc).isoformat(), "count": len(deals), "deals": deals},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(deals)} deals -> {OUT_PATH}")


if __name__ == "__main__":
    run()
