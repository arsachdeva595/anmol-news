#!/usr/bin/env python3
"""
classify_devaluations.py — reads feed.json (from harvester.py) and writes
devaluations.json containing ONLY genuine devaluation news: a benefit cut,
cap, reduction, or discontinuation that a bank actually made. It filters OUT
comparison posts, upgrade-advice queries, reviews, guides, and "is it still
worth it" discussion threads (e.g. "Regalia Gold vs Diners Club Privilege",
"should I upgrade from Millennia to Diners Club", "HDFC Infinia review").

Runs right after harvester.py in the same GitHub Action:
    python harvester.py
    python classify_offers.py
    python classify_devaluations.py    # <-- add this line
...and make sure the commit step stages devaluations.json.

Output: devaluations.json -> {"generated_at", "count", "devaluations": [...]},
newest first. Each item keeps the issuers[] the harvester already tagged,
plus a severity of "critical" | "major" | "minor".
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FEED_PATH = Path(__file__).parent / "feed.json"
OUT_PATH = Path(__file__).parent / "devaluations.json"

# Community (Reddit/Twitter/forum) posts pass the same strict gate below.
# Flip to False if you want the widget to show only blog/news devaluations.
INCLUDE_SOCIAL = True

# A real devaluation must contain at least one of these signals, graded by
# severity (checked in this order — first match wins).
CRITICAL = [
    r"\bdevalu(?:ation|ed|ing|es)\b",
    r"\bdiscontinued\b",
    r"\bwithdrawn\b",
    r"\bno\s+longer\b",
    r"\bremoved\b",
    r"\bkill(?:ed|s)?\b",
    r"\bscrapp?ed\b",
    r"\baxed\b",
]
MAJOR = [
    r"\brevis(?:ed|ion)\b",
    r"\bcapp?ed\b",
    r"\bcap\s+reduced\b",
    r"\breduc(?:ed|tion|es)\b",
    r"\bnerf(?:ed|s)?\b",
    r"\bdowngrad(?:e|ed|ing|es)\b",
    r"\bdegrad(?:e|ed|ing)\b",
    r"\bslash(?:ed|es)?\b",
    r"\bhalved\b",
    r"\bcut(?:s)?\s+(?:benefit|reward|point|lounge|milestone)",
]
MINOR = [
    r"\bt&c\s+update\b",
    r"\bterms?\s+updated\b",
    r"\bminor\s+change\b",
]
POSITIVE = CRITICAL + MAJOR + MINOR

# If any of these appear it's a comparison / advice / review / guide / opinion
# thread — exclude. Note: "upgrade"/"downgrade" are NOT here since downgrade
# is itself a positive devaluation signal above.
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
    r"\bopinion\b", r"\bthoughts\?",
    r"\bwhat\s+(?:to\s+do|should\s+(?:i|you))\b",
]

# Social-account admin/noise posts (channel migrations, pinned links, etc.)
# sometimes contain "no longer"/"devaluation" incidentally — exclude them.
NOISE = [
    r"\btelegram\s+channel\b", r"\bwhatsapp\s+community\b", r"\bsubscribers?\b",
    r"\btaken\s+over\b", r"\bmasterlink\b", r"\bpinned\b",
]

CRIT_RE = [re.compile(p, re.I) for p in CRITICAL]
MAJOR_RE = [re.compile(p, re.I) for p in MAJOR]
MINOR_RE = [re.compile(p, re.I) for p in MINOR]
POS_RE = [re.compile(p, re.I) for p in POSITIVE]
NEG_RE = [re.compile(n, re.I) for n in NEGATIVE]
NOISE_RE = [re.compile(n, re.I) for n in NOISE]


def severity(text: str) -> str:
    if any(r.search(text) for r in CRIT_RE):
        return "critical"
    if any(r.search(text) for r in MAJOR_RE):
        return "major"
    return "minor"


def is_devaluation(text: str) -> bool:
    if any(r.search(text) for r in NOISE_RE):
        return False
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

    devaluations = []
    for it in items:
        if not INCLUDE_SOCIAL and it.get("category") == "social":
            continue
        text = f"{it.get('title', '')} {it.get('snippet', '')}"
        if not is_devaluation(text):
            continue
        devaluations.append({
            "uid": it.get("uid"),
            "title": it.get("title"),
            "url": it.get("url"),
            "source": it.get("source"),
            "issuers": it.get("issuers", []),
            "severity": severity(text),
            "published": it.get("published"),
            "snippet": it.get("snippet", ""),
        })

    devaluations.sort(key=lambda x: x.get("published", ""), reverse=True)
    OUT_PATH.write_text(
        json.dumps({"generated_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(devaluations), "devaluations": devaluations}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(devaluations)} devaluations -> {OUT_PATH}")


if __name__ == "__main__":
    run()
