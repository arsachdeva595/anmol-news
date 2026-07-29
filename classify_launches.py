#!/usr/bin/env python3
"""
classify_launches.py — reads feed.json (from harvester.py) and writes
launches.json containing ONLY genuine new-card-launch news: a bank actually
announcing, unveiling, or rolling out a new card. It filters OUT comparison
posts, upgrade-advice queries, reviews, guides, and "best cards" listicles
(e.g. "Regalia Gold vs Diners Club Privilege", "5 best travel cards in
2026", "HDFC Infinia review").

Runs right after harvester.py in the same GitHub Action:
    python harvester.py
    python classify_offers.py
    python classify_devaluations.py
    python classify_launches.py        # <-- add this line
...and make sure the commit step stages launches.json.

Output: launches.json -> {"generated_at", "count", "launches": [...]},
newest first. Each item keeps the issuers[] the harvester already tagged.
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FEED_PATH = Path(__file__).parent / "feed.json"
OUT_PATH = Path(__file__).parent / "launches.json"

# Community (Reddit/Twitter/forum) posts pass the same strict gate below.
# Flip to False if you want the widget to show only blog/news launches.
INCLUDE_SOCIAL = True

# A real launch must contain at least one of these signals.
POSITIVE = [
    r"\blaunch(?:es|ed|ing)?\b",
    r"\bintroduc(?:es|ed|ing)\b",
    r"\bdebuts?\b",
    r"\bunveil(?:s|ed|ing)?\b",
    r"\bnew\s+card\b",
    r"\bannounc(?:es|ed|ing)\b",
    r"\breleas(?:es|ed|ing)\b",
    r"\bnow\s+available\b",
    r"\brolls?\s+out\b",
    r"\bto\s+launch\b",
    r"\binvite[\s-]*only\b",
    r"\bwaitlist\b",
]

# If any of these appear it's a comparison / advice / review / guide /
# listicle — exclude.
NEGATIVE = [
    r"\bvs\.?\b", r"\bversus\b",
    r"\bshould\s+(?:i|you)\b",
    r"\bwhich\s+(?:card|is|one|credit)\b",
    r"\breview\b", r"\bcomparison\b", r"\bcompared?\b",
    r"\beligibilit",
    r"\bhow\s+to\b",
    r"\b(?:complete\s+)?guide\b",
    r"\bworth\s+it\b",
    r"\bbest\s+(?:\w+\s+){0,3}cards?\b",
    r"\bfeatures\s+of\b", r"\bbenefits\s+of\b",
    r"\bupgrade\b", r"\bdowngrade\b",
    r"\bwhat\s+to\s+do\b",
    # Rewards portals / promo campaigns often say "launched" but aren't a new card.
    r"\bportal\b", r"\baggregator\b", r"\bcampaign\b",
    # Devaluation news often says "announced"/"introduces" too — keep the two
    # categories mutually exclusive by excluding devaluation core signals here.
    r"\bdevaluat", r"\brevis(?:ed|ion)\b", r"\bcapp?ed\b", r"\bcap\s+reduced\b",
    r"\bdowngrad", r"\bnerf", r"\bdiscontinued\b", r"\bwithdrawn\b", r"\bslash(?:ed|es)?\b",
    # A bank "launching" a cashback/rewards campaign on an existing card is an
    # offer, not a new card — keep offers and launches mutually exclusive too.
    r"\d{1,3}\s*%\s*(?:off|cashback|discount|back|rewards?)\b",
    r"\bcashback\b",
    r"\bflat\s*(?:₹|rs\.?\s*)?\d",
    r"(?:₹|rs\.?\s*)\d[\d,]*\s*(?:off|cashback|back)\b",
    r"\bno[\s-]*cost\s+emi\b",
    r"\b(?:coupon|promo)\s*code\b",
    r"\bextra\s+\d",
    r"\binstant\s+discount\b",
    r"\bup\s+to\s+\d+\s*(?:%|x\b|air\s*miles?|points?|rewards?)",
    r"\b\d+\s*x\s+[a-z]",
]

POS_RE = [re.compile(p, re.I) for p in POSITIVE]
NEG_RE = [re.compile(n, re.I) for n in NEGATIVE]


def is_launch(text: str) -> bool:
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

    launches = []
    for it in items:
        if not INCLUDE_SOCIAL and it.get("category") == "social":
            continue
        text = f"{it.get('title', '')} {it.get('snippet', '')}"
        if not is_launch(text):
            continue
        launches.append({
            "uid": it.get("uid"),
            "title": it.get("title"),
            "url": it.get("url"),
            "source": it.get("source"),
            "issuers": it.get("issuers", []),
            "published": it.get("published"),
            "snippet": it.get("snippet", ""),
        })

    launches.sort(key=lambda x: x.get("published", ""), reverse=True)
    OUT_PATH.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(launches), "launches": launches}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(launches)} launches -> {OUT_PATH}")


if __name__ == "__main__":
    run()
