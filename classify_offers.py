#!/usr/bin/env python3
"""
classify_offers.py — reads feed.json (from harvester.py) and writes deals.json
containing ONLY genuine promotional offers: an extra discount, cashback, or an
added/complimentary benefit. It filters OUT comparison posts, upgrade-advice
queries, reviews and guides (e.g. "Regalia Gold vs Diners Club Privilege",
"should I upgrade from Millennia to Diners Club", "HDFC Infinia review").

Runs right after harvester.py in the same GitHub Action:
    python harvester.py
    python classify_offers.py          # <-- add this line
...and make sure the commit step stages deals.json (git add -A covers it).

Output: deals.json -> {"generated_at", "count", "deals": [...]}, newest first.
Each deal keeps the issuers[] the harvester already tagged, plus a deal_type
of "cashback" | "discount" | "benefit".
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FEED_PATH = Path(__file__).parent / "feed.json"
OUT_PATH = Path(__file__).parent / "deals.json"

# Community (Reddit/Twitter/forum) posts pass the same strict gate below.
# Flip to False if you want the widget to show only blog/news offers.
INCLUDE_SOCIAL = True

# A real offer must contain at least one of these promo / benefit signals.
POSITIVE = [
    r"\b\d{1,3}\s*%\s*(?:off|cashback|discount|back)\b",
    r"\bflat\s*(?:₹|rs\.?\s*)?\d",
    r"\bup\s*to\s*(?:₹|rs\.?\s*)?\d",
    r"(?:₹|rs\.?\s*)\d[\d,]*\s*(?:off|cashback|discount|back)\b",
    r"\binstant\s+discount\b",
    r"\bcashback\b",
    r"\bwelcome\s+(?:offer|benefit|bonus|voucher)\b",
    r"\bmilestone\s+(?:benefit|offer|reward|voucher)\b",
    r"\b(?:5x|10x|accelerated)\s+reward",
    r"\bbonus\s+(?:reward|point|offer)\b",
    r"\bno[\s-]*cost\s+emi\b",
    r"\b(?:coupon|promo)\s*code\b",
    r"\blimited[\s-]*time\b",
    r"\b(?:sale|voucher|gift\s*card)\b",
    r"\bextra\s+\d",
    r"\bcomplimentary\b",
    r"\bfree\s+(?:lounge|voucher|night|membership|movie)\b",
]

# If any of these appear it's a comparison / advice / review / guide — exclude.
NEGATIVE = [
    r"\bvs\.?\b", r"\bversus\b",
    r"\bshould\s+(?:i|you)\b",
    r"\bwhich\s+(?:card|is|one|credit)\b",
    r"\b(?:upgrade|downgrade)\b",
    r"\breview\b", r"\bcomparison\b", r"\bcompared?\b",
    r"\beligibilit",
    r"\bhow\s+to\b",
    r"\b(?:complete\s+)?guide\b",
    r"\bworth\s+it\b",
    r"\bbest\s+(?:\w+\s+){0,3}cards?\b",
    r"\bfeatures\s+of\b", r"\bbenefits\s+of\b",
    r"\btaxable\b", r"\bincome\s+tax\b", r"\bitr\s+filing\b", r"\btax\s+implications?\b",
]

POS_RE = [re.compile(p, re.I) for p in POSITIVE]
NEG_RE = [re.compile(n, re.I) for n in NEGATIVE]


def deal_type(text: str) -> str:
    t = text.lower()
    if "cashback" in t:
        return "cashback"
    if re.search(r"%|\bflat\b|discount|\bsale\b|\boff\b|voucher|coupon", t):
        return "discount"
    return "benefit"


def is_deal(text: str) -> bool:
    if not any(r.search(text) for r in POS_RE):
        return False
    if any(r.search(text) for r in NEG_RE):
        return False
    return True


def run() -> None:
    if not FEED_PATH.exists():
        print("feed.json not found — run harvester.py first.")
        return
    data = json.loads(FEED_PATH.read_text(encoding="utf-8"))
    items = data.get("items", [])

    deals = []
    for it in items:
        if not INCLUDE_SOCIAL and it.get("category") == "social":
            continue
        text = f"{it.get('title', '')} {it.get('snippet', '')}"
        if not is_deal(text):
            continue
        deals.append({
            "uid": it.get("uid"),
            "title": it.get("title"),
            "url": it.get("url"),
            "source": it.get("source"),
            "issuers": it.get("issuers", []),
            "deal_type": deal_type(text),
            "published": it.get("published"),
            "snippet": it.get("snippet", ""),
        })

    deals.sort(key=lambda x: x.get("published", ""), reverse=True)
    OUT_PATH.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(deals), "deals": deals}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(deals)} deals -> {OUT_PATH}")


if __name__ == "__main__":
    run()
