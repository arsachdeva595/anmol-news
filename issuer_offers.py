#!/usr/bin/env python3
"""
issuer_offers.py — scrapes official issuer "offers" pages for live
credit-card deals and returns feed-item dicts compatible with feed.json.

Coverage note
-------------
Every major Indian card issuer's public offers page was checked for
feasibility. A source qualifies if real offer data is reachable via a
plain `requests` call — no headless browser needed at run time — as
server-rendered DOM (Axis, HSBC, Kotak, and ICICI's second source,
campaigns/bonanza), a JSON/JS variable embedded in an inline <script>
(BOBCard, SBI Card), or a JSON API endpoint the page's own JS calls
(ICICI's first source, /offers — found via a one-off Playwright
network-inspection session, not a rendering *requirement*: the endpoint
itself takes a plain GET, so no browser is needed at run time):

    Axis Bank, HSBC, Kotak, BOB Financial (BOBCard), SBI Card, ICICI Bank

ICICI has two independent sources: /offers (a small ~5-offer curated
JSON feed) and /campaigns/bonanza (a much larger ~100-offer static HTML
page, user-supplied) — both feed into deals.json under the same issuer.

Scope: credit card offers only. Several issuer pages mix in debit-card
and net-banking offers, so each parser filters on whatever payment-method
signal is available — Axis's per-card tag, ICICI's `paymentGatewayValue`
field, a text heuristic for HSBC (no tag exposed there). BOBCard and SBI
Card need no filtering: both entities issue credit cards only, and
neither's data has any debit/net-banking offers to filter out. Kotak
needed the opposite fix — its bare /offers.html silently defaults to
just the "Credit Card EMI" bucket, missing the disjoint plain "Credit
Card" bucket entirely (both are now fetched via `urls`, see
ISSUER_OFFER_SOURCES; `paymentType=debit` is never fetched).

Also confirmed: many issuers now serve the *same* offers page from a
newer "<issuer>.bank.in" domain (RBI's bank-domain initiative) — Axis,
Kotak, HSBC, Amex were all re-checked there and returned byte-identical
content to their .com equivalents, so no functional difference. HDFC's
`.bank.in` offers page is the one exception: it's no longer bot-blocked
there (unlike hdfcbank.com), but the grid is still client-side JS with
no usable data embedded anywhere in the response, so it stays excluded.

Checked and excluded, with reason:
    HDFC Bank              — offers grid is client-side JS, no embedded
                              data (hdfcbank.com is Akamai bot-blocked;
                              hdfc.bank.in loads but has nothing static)
    Yes Bank                 — SPA shell that resolves to a 404 template;
                                no offer data anywhere in the response
    IndusInd Bank            — confirmed via full headless-browser render
                                (networkidle wait): zero offer content
                                anywhere in the rendered page. Not a
                                rendering problem — there's just nothing
                                there on any URL variant tried.
    AU Small Finance Bank    — bot-block (403) on every domain tried
    RBL Bank                 — confirmed via headless render: only the
                                same static teaser banner. The real grid
                                is genuinely mobile-app-only content
                                ("Visit RBL MyBank App" is the page's own
                                text), not a web scraping problem.
    Standard Chartered       — offers page lists categories only, no
                                actual merchant offers in static HTML
    IDFC First Bank          — confirmed via headless render: every
                                /offers URL tried, including the
                                "credit-card-merchant-offers" path, only
                                ever renders the card-product mega-menu,
                                never an actual merchant-deals grid.
    American Express         — offers are gated behind card selection
    Federal Bank             — Radware bot-block (CAPTCHA wall)
    IDBI Bank                 — /offers redirects to the homepage

IndusInd, RBL, and IDFC First were re-checked with a real headless
browser (Playwright + networkidle wait, scrolling, "load more" probing)
specifically to rule out "just needs JS" as the explanation — none of
them have merchant offer data available on the public web at all, so a
browser dependency wouldn't help. Playwright was useful as a one-off
diagnostic (it's how ICICI's JSON endpoint was found via its network
tab) but isn't a project dependency — nothing here needs it at run time.

If any of the above later exposes a scrapable offers page (bank sites
change often — worth checking inline <script> tags and the browser
network tab for a plain JSON blob/endpoint before assuming a JS-rendered
grid is a dead end), add a `_parse_<issuer>()` function following the
same pattern and register it in ISSUER_OFFER_SOURCES.
"""
import hashlib
import json
import logging
import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin

import requests
import urllib3
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

log = logging.getLogger("issuer_offers")

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")
REQUEST_TIMEOUT = 20


def _get(url: str):
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except requests.exceptions.SSLError as e:
        # A handful of issuer sites (e.g. bobcard.co.in) serve only the leaf
        # cert and omit the intermediate — browsers/curl tolerate this via
        # OS-level AIA chasing, Python's ssl module does not. Retry once
        # without verification rather than dropping a known-good source.
        log.warning("SSL chain issue (%s), retrying without verification: %s", url, e)
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT, verify=False)
            r.raise_for_status()
            return r.text
        except Exception as e2:
            log.warning("GET failed (%s): %s", url, e2)
            return None
    except Exception as e:
        log.warning("GET failed (%s): %s", url, e)
        return None


def _parse_valid_till(text: str):
    """Best-effort free-text date -> ISO date string, or None."""
    if not text:
        return None
    try:
        d = dateparser.parse(text, fuzzy=True, dayfirst=True)
        return d.date().isoformat()
    except Exception:
        return None


def _is_expired(valid_till_iso: str) -> bool:
    if not valid_till_iso:
        return False
    try:
        return date.fromisoformat(valid_till_iso) < date.today()
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Per-issuer parsers
# Each returns a list of dicts: title, description, url, promo_code, valid_till
# -----------------------------------------------------------------------------

def _parse_axis(html_text: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for card in soup.select("div.compare-card"):
        title_el = card.select_one("p.Hide-Title")
        desc_el = card.select_one("p.section-desc")
        promo_el = card.select_one("div.offers-code p.code-cont")
        valid_el = card.select_one("span.valid-date-cont")
        tag_el = card.select_one("span.span-cont")
        link_el = card.select_one("a.knowmore[href]")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue
        # Cards are tagged with which payment methods qualify, e.g.
        # "Credit Card | Travel" or "Shopping | Credit Card | Debit Card" —
        # credit-card-only scope, so skip anything not tagged for it (e.g.
        # a pure "Debit Card | ..." or "Net Banking | ..." offer).
        tags = tag_el.get_text(" ", strip=True).lower() if tag_el else ""
        if tags and "credit card" not in tags:
            continue
        promo = promo_el.get_text(strip=True) if promo_el else None
        if promo and promo.lower() == "not available":
            promo = None
        out.append({
            "title": title,
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "url": urljoin(base_url, link_el["href"]) if link_el else base_url,
            "promo_code": promo,
            "valid_till": _parse_valid_till(valid_el.get_text(" ", strip=True) if valid_el else ""),
        })
    return out


def _parse_hsbc(html_text: str, base_url: str) -> list[dict]:
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for card in soup.select("div.crh-master-cards__card"):
        title_el = card.select_one("h3 .link.text") or card.select_one("h3")
        desc_el = card.select_one(".master-card__text p")
        link_el = card.select_one("h3 a[href]")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue
        desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        # No explicit payment-type tag is exposed per card here (unlike
        # Axis), so this is a text heuristic: skip anything that reads as
        # debit/net-banking-specific and never actually mentions credit card.
        combined = f"{title} {desc}".lower()
        if re.search(r"\bdebit card\b|\bnet[\s-]?banking\b", combined) and "credit card" not in combined:
            continue
        m = re.search(r"(offer\s+valid\s+(?:till|until)\s+[^.]*)", desc, re.I)
        out.append({
            "title": title,
            "description": desc,
            "url": urljoin(base_url, link_el["href"]) if link_el else base_url,
            "promo_code": None,
            "valid_till": _parse_valid_till(m.group(1)) if m else None,
        })
    return out


def _parse_kotak(html_text: str, base_url: str) -> list[dict]:
    # Kotak's card markup separates the merchant name (h4.card-heading, e.g.
    # "Haier") from the actual offer terms (div.card-desc, e.g. "Instant
    # cashback up to ₹25,000 on Kotak Credit Card EMI"). Neither alone is a
    # useful headline, so the title combines both — same "brand: terms"
    # shape Axis/BOBCard titles already have baked into their own text.
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for card in soup.select("div.sif-card"):
        merchant_el = card.select_one("h4.card-heading")
        desc_el = card.select_one("div.card-desc")
        valid_el = card.select_one("div.article-date")
        link_el = card.select_one("a[data-href]")
        merchant = merchant_el.get_text(strip=True) if merchant_el else None
        if not merchant:
            continue
        desc = desc_el.get_text(strip=True) if desc_el else ""
        out.append({
            "title": f"{merchant}: {desc}" if desc else merchant,
            "description": desc,
            "url": urljoin(base_url, link_el["data-href"]) if link_el else base_url,
            "promo_code": None,
            "valid_till": _parse_valid_till(valid_el.get_text(" ", strip=True) if valid_el else ""),
        })
    return out


def _parse_sbicard(html_text: str, base_url: str) -> list[dict]:
    # sbicard.com's offers page renders its grid client-side, but the data
    # driving it ships as a plain JS variable assignment
    # (`var offerData={"offers":{"offer":[...]}}`) in an inline <script> —
    # a genuine JSON payload, not markup to scrape.
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for script in soup.find_all("script"):
        if not script.string or "offerData" not in script.string:
            continue
        m = re.search(r"var\s+offerData\s*=\s*(\{)", script.string)
        if not m:
            continue
        try:
            data, _ = json.JSONDecoder().raw_decode(script.string, m.start(1))
        except Exception:
            continue
        for o in data.get("offers", {}).get("offer", []):
            brand = (o.get("brandName") or "").strip()
            terms = (o.get("text") or o.get("discountBlock") or "").strip()
            if not brand or not terms:
                continue
            # offerId (e.g. "Vishal-Mega-Mart-19aug26.page") is itself the
            # URL slug — verified live: sbicard.com/en/personal/offer/<id>
            # resolves with a 200 for every sampled id.
            offer_id = (o.get("offerId") or "").strip()
            out.append({
                "title": f"{brand.title()}: {terms}",
                "description": terms,
                "url": urljoin("https://www.sbicard.com/en/personal/offer/", offer_id) if offer_id else base_url,
                "promo_code": None,
                "valid_till": o.get("endDate") or None,
            })
        break
    return out


def _parse_icici(json_text: str, base_url: str) -> list[dict]:
    # icicibank.com's /offers page renders its grid client-side, but that
    # grid is itself just fetching this JSON endpoint (found via network
    # inspection, not present anywhere in the page's HTML/scripts) — so it's
    # called directly, no browser involved. Small catalog (~5 offers): this
    # looks like a curated "featured" set rather than ICICI's full partner
    # list, and the `start` param doesn't actually paginate past it.
    try:
        data = json.loads(json_text)
    except Exception:
        return []
    out = []
    for c in data.get("cards", []):
        title = (c.get("offerTitle") or "").strip()
        if not title:
            continue
        # paymentGatewayValue is a comma-separated eligible-payment-methods
        # list, e.g. "Credit Card,Debit Card" or "Net Banking,Debit Card" —
        # credit-card-only scope, so drop offers that don't list it at all.
        if "credit card" not in (c.get("paymentGatewayValue") or "").lower():
            continue
        promo = (c.get("offerPromoCode") or "").strip()
        if promo.upper() in ("", "NA"):
            promo = None
        link = c.get("ctalink") or c.get("pagePath") or ""
        out.append({
            "title": title,
            "description": (c.get("offerDesp1") or "").strip(),
            "url": urljoin("https://www.icici.bank.in/", link) if link else base_url,
            "promo_code": promo,
            "valid_till": _parse_valid_till(c.get("endDate") or ""),
        })
    return out


def _parse_icici_bonanza(html_text: str, base_url: str) -> list[dict]:
    # A second, much larger ICICI offers page (campaigns/bonanza) — fully
    # static HTML, unlike /offers. Each div.offertext holds one or more
    # offers as (h6 title, p validity/payment-method, a.track-offer[href]
    # or h3.nobtndiv "visit store" text) sibling groups, not one-per-container.
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for block in soup.select("div.offertext"):
        # The "podium" highlight boxes at the top of the page put the
        # product name only in a sibling logo image's alt text (e.g. "iPhone
        # 17"), never in the visible h6/p copy — without this, several
        # offers there collapse into indistinguishable bare amounts like
        # "₹3,000 instant cashback".
        logo_img = block.parent.select_one("div.offerlogo img[alt]") if block.parent else None
        merchant = (logo_img.get("alt") or "").strip() if logo_img else ""

        children = block.find_all(["h6", "p", "a", "h3"], recursive=False)
        i = 0
        while i < len(children):
            if children[i].name != "h6":
                i += 1
                continue
            title_el = children[i]
            i += 1
            p_el, link_el = None, None
            while i < len(children) and children[i].name != "h6":
                if children[i].name == "p" and p_el is None:
                    p_el = children[i]
                elif children[i].name == "a" and link_el is None:
                    link_el = children[i]
                i += 1

            title_text = title_el.get_text(" ", strip=True)
            promo = None
            if "Use Code:" in title_text:
                title_text, _, code = title_text.partition("Use Code:")
                title_text = title_text.strip()
                promo = code.strip() or None
            # Space-insensitive check: alt text is sometimes squashed
            # ("AppleWatch" for a title already saying "Apple Watch ...").
            if merchant and merchant.lower().replace(" ", "") not in title_text.lower().replace(" ", ""):
                title_text = f"{title_text} on {merchant}"

            desc = p_el.get_text(" ", strip=True) if p_el else ""
            # Credit-card-only scope: the payment-methods line (e.g. "Valid
            # on Credit Card EMIs" / "Valid on Cardless EMI") is the signal.
            if "credit card" not in desc.lower():
                continue

            m = re.search(r"\bto\s+([A-Za-z]+\s+\d{1,2},?\s*\d{4})", desc)
            valid_till = _parse_valid_till(m.group(1)) if m else _parse_valid_till(desc)

            href = link_el.get("href") if link_el else None
            out.append({
                "title": title_text,
                "description": desc,
                "url": urljoin(base_url, href) if href else base_url,
                "promo_code": promo,
                "valid_till": valid_till,
            })
    return out


_BOBCARD_OFFER_RE = re.compile(
    r'"OfferId":"(?P<id>[^"]*)".*?'
    r'"OfferTitle":"(?P<title>.*?)","OfferShortDescription":"(?P<desc>.*?)",'
    r'"Promocode":"(?P<promo>.*?)","Validity":"(?P<validity>.*?)",'
    r'"OfferImage":"[^"]*","OfferCTA":[^,]*,"OfferPageCTA":"(?P<cta>[^"]*)"'
)


def _json_unescape(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s


def _parse_bobcard(html_text: str, base_url: str) -> list[dict]:
    # Offer data ships inside a Next.js RSC stream as a double-escaped JSON
    # blob, not as plain DOM — regex-extract the repeated offer objects
    # rather than trying to find a single parseable JSON document.
    unescaped = html_text.replace('\\"', '"')
    seen_ids = set()
    out = []
    for m in _BOBCARD_OFFER_RE.finditer(unescaped):
        d = m.groupdict()
        if d["id"] in seen_ids:
            continue
        seen_ids.add(d["id"])
        promo = _json_unescape(d["promo"])
        if promo.strip().upper() == "NA":
            promo = None
        out.append({
            "title": _json_unescape(d["title"]),
            "description": _json_unescape(d["desc"]),
            "url": urljoin(base_url, d["cta"]) if d["cta"] else base_url,
            "promo_code": promo,
            "valid_till": _parse_valid_till(d["validity"]),
        })
    return out


ISSUER_OFFER_SOURCES = [
    {
        "name": "Axis Bank Offers",
        "issuer": "Axis Bank",
        "url": "https://www.axis.bank.in/offers/",
        "parser": _parse_axis,
    },
    {
        "name": "HSBC Offers",
        "issuer": "HSBC",
        "url": "https://www.hsbc.co.in/offers/",
        "parser": _parse_hsbc,
    },
    {
        "name": "Kotak Offers",
        "issuer": "Kotak",
        "url": "https://www.kotak.com/en/offers.html?paymentType=credit",
        # The bare /offers.html page silently defaults to just the "Credit
        # Card EMI" bucket — it and the plain "Credit Card" bucket are two
        # disjoint sets (verified zero title overlap), so both must be
        # fetched explicitly or ~30% of Kotak's actual credit-card offers
        # go missing. Excludes paymentType=debit entirely (never fetched).
        "urls": [
            "https://www.kotak.com/en/offers.html?paymentType=credit",
            "https://www.kotak.com/en/offers.html?paymentType=credit+card+emi",
        ],
        "parser": _parse_kotak,
    },
    {
        "name": "BOBCard Offers",
        "issuer": "BOB Financial (BOBCard)",
        "url": "https://www.bobcard.co.in/credit-card-offers",
        "parser": _parse_bobcard,
    },
    {
        "name": "SBI Card Offers",
        "issuer": "SBI Card",
        "url": "https://www.sbicard.com/en/personal/offers.page",
        "parser": _parse_sbicard,
    },
    {
        "name": "ICICI Bank Offers",
        "issuer": "ICICI Bank",
        "url": "https://www.icici.bank.in/content/icicibank.offersearch.json?searchPath=/content/icicibank/in/en/offers&start=0",
        "parser": _parse_icici,
    },
    {
        "name": "ICICI Bank Bonanza Offers",
        "issuer": "ICICI Bank",
        "url": "https://www.icici.bank.in/campaigns/bonanza/index",
        "parser": _parse_icici_bonanza,
    },
]


def uid(url: str, title: str) -> str:
    # Unlike harvester.py's uid(), always combine url+title: several issuer
    # pages (e.g. HSBC) don't expose a per-offer link for every card, so
    # multiple distinct offers can share the same fallback page URL.
    raw = f"{(url or '').strip().lower()}|{(title or '').strip().lower()}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


def fetch_issuer_offers() -> list[dict]:
    """Fetch all configured issuer offer pages and return feed-item dicts."""
    items = []
    now = datetime.now(timezone.utc).isoformat()
    for src in ISSUER_OFFER_SOURCES:
        log.info("Issuer offers → %s", src["name"])
        offers = []
        for url in src.get("urls") or [src["url"]]:
            html_text = _get(url)
            if not html_text:
                continue
            try:
                offers.extend(src["parser"](html_text, url))
            except Exception as e:
                log.warning("Parse error (%s, %s): %s", src["name"], url, e)
        added = 0
        for o in offers:
            if _is_expired(o.get("valid_till")):
                continue
            title = (o.get("title") or "").strip()
            if not title:
                continue
            snippet = (o.get("description") or "").strip()
            if o.get("promo_code"):
                snippet = f"{snippet} (Code: {o['promo_code']})".strip()
            items.append({
                "uid": uid(o["url"], title),
                "title": title,
                "url": o["url"],
                "source": src["name"],
                "category": "offer",
                "issuers": [src["issuer"]],
                "severity": None,
                "published": now,
                "snippet": snippet[:300],
                "relevance_score": 1,
                "valid_till": o.get("valid_till"),
            })
            added += 1
        log.info("  → %d live offers", added)
    return items


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    result = fetch_issuer_offers()
    print(f"Fetched {len(result)} issuer offers")
    for it in result[:10]:
        print(" -", it["source"], "|", it["title"], "|", it.get("valid_till"))
