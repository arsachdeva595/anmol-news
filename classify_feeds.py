#!/usr/bin/env python3
"""
classify_feeds.py — one router, three mutually-exclusive outputs.
Each item lands in exactly ONE of: devaluations.json, launches.json, deals.json
(or is dropped). Priority: devaluation > launch(new card) > deal. This removes
deals<->launches overlap and stops offers that merely contain the word "launch"
from polluting launches.json.
"""
import json, re
from datetime import datetime, timezone
from pathlib import Path

D = Path(__file__).parent
FEED = D / "feed.json"

POSITIVE = [r"\b\d{1,3}\s*%\s*(?:off|cashback|discount|back|rewards?)\b", r"\bflat\s*(?:₹|rs\.?\s*)?\d",
    r"\bup\s*to\s*(?:₹|rs\.?\s*)?\d", r"(?:₹|rs\.?\s*)\d[\d,]*\s*(?:off|cashback|back)\b", r"\binstant\s+discount\b",
    r"\bcashback\b", r"\bwelcome\s+(?:offer|benefit|bonus|voucher)\b", r"\bmilestone\s+(?:benefit|offer|reward|voucher)\b",
    r"\b\d+\s*x\s+[a-z]", r"\bearn\s+(?:up\s+to\s+)?\d", r"\bno[\s-]*cost\s+emi\b", r"\b(?:coupon|promo)\s*code\b",
    r"\blimited[\s-]*time\b", r"\b(?:sale|voucher|gift\s*card)\b", r"\bextra\s+\d", r"\bcomplimentary\b",
    r"\bfree\s+(?:lounge|voucher|night|membership|movie|esim)\b"]
HARD = re.compile(r"\d{1,3}\s*%\s*(?:off|cashback|discount|back|rewards?)|(?:₹|rs\.?\s*)\d[\d,]*\s*(?:off|cashback|back)|\binstant\s+discount\b|\bflat\s*\d|\bno[\s-]*cost\s+emi\b", re.I)
NEGATIVE = [r"\bvs\.?\b", r"\bversus\b", r"\bshould\s+(?:i|you)\b", r"\bwhich\s+(?:card|is|one|credit)\b", r"\breview\b",
    r"\bcomparison\b", r"\bcompared?\b", r"\beligibilit", r"\bhow\s+to\b", r"\b(?:complete\s+)?guide\b", r"\bworth\s+it\b",
    r"\bbest\b[^.\n]{0,30}\bcards?\b", r"\btop\s+\d+\b[^.\n]{0,30}\bcards?\b", r"\bfeatures\s+of\b", r"\bbenefits\s+of\b",
    r"\bmy\s+experience\b", r"\bstatus\s+match\b", r"\btrip\s+report\b", r"\bdid\s+you\s+know\b", r"\d+\s+credit cards with"]
DEVALUATION = [r"devalu", r"\bnerf", r"\bcapp?ed\b", r"\bcaps\b", r"\brevis(?:ed|ion|ing)\b", r"\breduc(?:e|ed|tion|ing)\b",
    r"\bremov(?:e|ed|al|ing)\b", r"\bwithdraw", r"\bdiscontinu", r"\bno\s+longer\b", r"\bnew\s+rules\b", r"\brule\s+changes?\b",
    r"\bno\s+major\s+blow\b", r"\bdowngrad", r"\bno\s+airport\s+lounge\b", r"cut(?:s|ting)?\s+(?:cashback|reward|lounge|benefit)",
    r"(?:cashback|lounge|reward)[^.\n]{0,25}(?:revis|remov|capp|reduc|slash|ends?\b)", r"golden\s+era[^.\n]{0,25}end",
    r"late\s+payment\s+charge"]
# Higher-severity subset of DEVALUATION — a card feature was actually killed,
# not just capped/revised. Drives the dashboard's critical ticker + pill.
DEVALUATION_CRITICAL = [r"devalu", r"\bwithdraw", r"\bdiscontinu", r"\bno\s+longer\b",
    r"\bremov(?:e|ed|al|ing)\b", r"golden\s+era[^.\n]{0,25}end"]
NOISE = [r"\bmasterlink\b", r"\bgrab\s+if\s+needed\b", r"\bfollow\s+@", r"\bpinned\b", r"^\s*rt\b", r"\br\s+to\s+@"]
# A LAUNCH = a NEW card appearing. Exclude "launches sale/offer/emi" (that's a deal).
LAUNCH = [r"\b(?:launch(?:es|ed|ing)?|introduc(?:es|ed|ing)|unveil(?:s|ed)?|debut(?:s|ed)?|rolls?\s+out)\b[^.\n]{0,45}\b(?:credit\s+card|card)\b",
    r"\bco[-\s]?branded\b[^.\n]{0,30}\bcard\b", r"\bnew\b[^.\n]{0,20}\bcredit\s+card\b"]
LAUNCH_NOT = [r"\b(?:launch(?:es|ed|ing)?|introduc\w*)\b[^.\n]{0,15}\b(?:sale|offer|discount|deal|emi|cashback|campaign)\b"]

def rc(l): return [re.compile(p, re.I) for p in l]
POS,NEG,DEV,NZ,LA,LNOT,DEVC = map(rc,[POSITIVE,NEGATIVE,DEVALUATION,NOISE,LAUNCH,LAUNCH_NOT,DEVALUATION_CRITICAL])
def hit(res,t): return any(r.search(t) for r in res)
def severity(t): return "critical" if hit(DEVC,t) else "major"

def is_social(it,title):
    s=(it.get("source") or "").lower()
    return s.startswith("twitter") or s.startswith("reddit") or bool(re.search(r"\brt\s+by\s+@|\brt\s+@|^\s*r\s+to\s+@",title,re.I))
def is_noise(title,t):
    if hit(NZ,t): return True
    w=[x for x in title.split() if not x.startswith("#") and not x.startswith("@")]
    return title.count("#")>=3 and len(w)<=4
def deal_type(t):
    t=t.lower()
    if "cashback" in t: return "cashback"
    if re.search(r"%|\bflat\b|discount|\bsale\b|\boff\b|voucher|coupon",t): return "discount"
    return "benefit"
def is_launch(t): return hit(LA,t) and not hit(LNOT,t)
def is_deal(it,title,t):
    if hit(NEG,t): return False
    if is_social(it,title): return bool(HARD.search(t))
    return hit(POS,t)

def route(it):
    title=it.get("title","") or ""; t=f"{title} {it.get('snippet','')}"
    if is_noise(title,t): return None
    # Check comparison/listicle/review exclusions BEFORE devaluation signals —
    # a listicle that mentions "devaluations" in passing is still a listicle.
    if hit(NEG,t): return None
    if hit(DEV,t): return "devaluations"
    if is_launch(t): return "launches"
    if is_deal(it,title,t): return "deals"
    return None

def run():
    items=json.loads(FEED.read_text(encoding="utf-8")).get("items",[])
    out={"devaluations":[], "launches":[], "deals":[]}
    for it in items:
        b=route(it)
        if not b: continue
        rec={"uid":it.get("uid"),"title":it.get("title"),"url":it.get("url"),"source":it.get("source"),
             "issuers":it.get("issuers",[]),"published":it.get("published"),"snippet":it.get("snippet","")}
        if b=="deals":
            rec["deal_type"]=deal_type(f"{it.get('title','')} {it.get('snippet','')}")
            if it.get("valid_till"): rec["valid_till"]=it.get("valid_till")
        if b=="devaluations": rec["severity"]=severity(f"{it.get('title','')} {it.get('snippet','')}")
        out[b].append(rec)
    for b,rows in out.items():
        rows.sort(key=lambda x:x.get("published",""),reverse=True)
        (D/f"{b}.json").write_text(json.dumps({"generated_at":datetime.now(timezone.utc).isoformat(),"count":len(rows),b:rows},indent=2,ensure_ascii=False),encoding="utf-8")
    return out

o=run()
print("routed (mutually exclusive):", {k:len(v) for k,v in o.items()})
ids={k:set(x['uid'] for x in v) for k,v in o.items()}
print("overlap deals&launches:", len(ids['deals']&ids['launches']))
print()
print("=== launches.json after routing (should be new cards only) ===")
for x in o['launches'][:14]: print("  -",(x['title'] or '')[:80])
