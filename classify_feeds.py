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

# Offer category taxonomy for deals.json — merchant name is the strongest
# signal (most offer titles name a merchant), so it's checked first; generic
# vertical words are the fallback for text that names no specific merchant;
# offer-mechanism words (EMI, reward multipliers) come last since they can
# co-occur with a merchant that should win instead (e.g. "Haier: Instant
# cashback... EMI" is an Electronics deal, not a generic "Card & EMI" one).
OFFER_CATEGORIES = [
    ("Travel Deals", [
        r"goibibo", r"makemytrip", r"\byatra\b", r"ixigo", r"cleartrip", r"easemytrip",
        r"\bindigo\b", r"air india", r"fabhotels", r"udchalo", r"\boyo\b", r"emirates",
        r"spicejet", r"redbus", r"treebo", r"airbnb", r"booking\.com", r"agoda", r"irctc",
        r"vistara", r"akasa", r"\bflight", r"\bhotel", r"\bholiday", r"vacation",
        r"train\s+ticket", r"cab\s+booking", r"\bforex\b", r"cathay pacific", r"\bairline",
        r"\bairways\b", r"\bcruise\b", r"intr?city\b",
    ]),
    ("Electronics Deals", [
        r"\bapple\b", r"\blenovo\b", r"\bsamsung\b", r"\bxiaomi\b", r"\boppo\b", r"\bvivo\b",
        r"\brealme\b", r"\bnothing\b", r"\bmotorola\b", r"\bhp\b", r"\bdell\b", r"\bacer\b",
        r"\basus\b", r"\bjbl\b", r"\bbose\b", r"\bcanon\b", r"\bnikon\b", r"\blg\b",
        r"\bpanasonic\b", r"\bwhirlpool\b", r"\bvoltas\b", r"\bdaikin\b", r"\bhaier\b",
        r"\bgodrej\b", r"bosch", r"\bifb\b", r"\btcl\b", r"reliance digital", r"\bcroma\b",
        r"vijay sales", r"electrokraft", r"smart[\s-]bazar", r"\bpatra\b", r"sivmor",
        r"\boneplus\b", r"\bboat\b", r"\bnoise\b", r"\bsony\b", r"laptop", r"mobile phone",
        r"eureka forbes", r"\bcarrier\b", r"\bmidea\b", r"ao smith", r"\blloyd\b",
        r"\bonida\b", r"electrolux", r"electronics?\b", r"\bktm\b", r"hero motorbikes",
        r"\bdyson\b", r"mobiles?\b",
    ]),
    ("Shopping Deals", [
        r"\bamazon\b", r"\bflipkart\b", r"\bmyntra\b", r"\bajio\b", r"\bsnitch\b",
        r"benetton", r"urban ladder", r"home\s*centre", r"\bbata\b", r"the pant project",
        r"\bnua\b", r"\bindriya\b", r"\btanishq\b", r"senco gold", r"malabar gold",
        r"kalyan jewellers", r"\bmeesho\b", r"\bnykaa\b", r"tata cliq", r"\bwestside\b",
        r"pantaloons", r"\blifestyle\b", r"shoppers stop", r"\bdecathlon\b", r"firstcry",
        r"valentino", r"pepperfry", r"hush puppies", r"\bgiva\b", r"colorplus",
        r"ferns n petals", r"raymond", r"l'?occitane", r"surat diamond", r"interflora",
        r"\bhometown\b", r"furnishka",
        r"fashion", r"apparel", r"footwear", r"jewellery", r"\bdiamond", r"furniture",
        r"home d[ée]cor", r"\bgift", r"\bbeauty\b", r"cosmetics", r"florists?\b", r"flowers?\b",
    ]),
    ("Dining & Food Deals", [
        r"\bswiggy\b", r"\bzomato\b", r"district by zomato", r"\bkfc\b", r"domino",
        r"starbucks", r"mcdonald", r"pizza", r"cafe coffee day", r"barbeque nation",
        r"eazydiner", r"\bdineout\b", r"restaurant", r"\bdining\b", r"food\s+delivery",
        r"biryani", r"oven story",
    ]),
    ("Grocery & Essentials", [
        r"\bnetmeds\b", r"apollo pharmacy", r"\bzepto\b", r"big\s*basket", r"\bdmart\b",
        r"\bblinkit\b", r"\bgrofers\b", r"\b1mg\b", r"pharmeasy", r"\bjiomart\b",
        r"\bspencer", r"dry fruits", r"satvik store",
        r"grocery", r"supermarket", r"\bpharmacy\b", r"medicines?\b",
    ]),
    ("Entertainment Deals", [
        r"bookmyshow", r"\bpvr\b", r"\binox\b", r"\bnetflix\b", r"hotstar", r"\bspotify\b",
        r"sonyliv", r"\bzee5\b", r"\bgaana\b", r"\bwynk\b", r"movie\s+ticket", r"\bcinema\b",
        r"\bott\b", r"streaming", r"concert", r"event\s+ticket",
    ]),
    ("Health & Wellness", [
        r"wellness\s+spa", r"yes madam", r"lakme salon", r"cult\.?fit", r"\bgym\b",
        r"\bsalon\b", r"\bspa\b", r"urban company", r"wellness", r"fitness",
        r"healthcare", r"doctor consultation", r"doconline", r"health\s+plans?",
        r"\bmuscleblaze\b", r"medibuddy",
    ]),
    ("Fuel & Utility", [
        r"\bpetrol\b", r"\bdiesel\b", r"\bhpcl\b", r"\bbpcl\b", r"\biocl\b",
        r"fuel\s+station", r"electricity\s+bill", r"dth\s+recharge", r"mobile\s+recharge",
        r"gas\s+cylinder", r"utility\s+bill",
    ]),
    ("Bonus & Reward Offers", [
        r"reward\s+point", r"membership\s+rewards", r"rewardxcelerator", r"\d+\s*x\s+rewards?",
        r"milestone", r"bonus\s+reward", r"on\s+your\s+(?:international\s+)?spends?",
        r"cashback\s+on\s+spends?",
    ]),
    ("Card & EMI Offers", [
        r"no[\s-]?cost\s+emi", r"joining\s+fee", r"annual\s+fee\s+waiver", r"renewal\s+fee",
        r"card\s+upgrade", r"welcome\s+benefit",
    ]),
]

def rc(l): return [re.compile(p, re.I) for p in l]
POS,NEG,DEV,NZ,LA,LNOT,DEVC = map(rc,[POSITIVE,NEGATIVE,DEVALUATION,NOISE,LAUNCH,LAUNCH_NOT,DEVALUATION_CRITICAL])
OFFER_CAT = [(label, rc(pats)) for label, pats in OFFER_CATEGORIES]

def offer_category(t):
    for label, pats in OFFER_CAT:
        if any(p.search(t) for p in pats): return label
    return "Exclusive Discounts"
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
            blob=f"{it.get('title','')} {it.get('snippet','')}"
            rec["deal_type"]=deal_type(blob)
            rec["offer_category"]=offer_category(blob)
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
