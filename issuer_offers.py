#!/usr/bin/env python3
"""
issuer_offers.py — scrapes official issuer "offers" pages for live
credit-card deals and returns feed-item dicts compatible with feed.json.

Coverage note
-------------
Every major Indian card issuer's public offers page was checked for
feasibility (plain HTTP GET, no headless browser). Only sources that
return real offer data in the *initial* HTML response — no bot wall,
no client-side rendering — are wired up here:

    Axis Bank, HSBC, Kotak, BOB Financial (BOBCard)

Checked and excluded, with reason:
    HDFC Bank              — Akamai bot-block (403 on every request)
    ICICI Bank              — offers grid is loaded client-side (JS)
    SBI Card                — offers grid is loaded client-side (JS)
    Yes Bank                 — SPA shell, "requires JavaScript" page
    IndusInd Bank            — offers URL 404s; no working path found
    AU Small Finance Bank    — bot-block (403)
    RBL Bank                 — only a single teaser banner is static
    Standard Chartered       — offers page lists categories only, no
                                actual merchant offers in static HTML
    IDFC First Bank          — /offers is a card-product page, not a
                                merchant-deals listing
    American Express         — offers are gated behind card selection
    Federal Bank             — Radware bot-block (CAPTCHA wall)
    IDBI Bank                 — /offers redirects to the homepage

If any of the above later exposes a scrapable offers page (bank sites
change often), add a `_parse_<issuer>()` function following the same
pattern and register it in ISSUER_OFFER_SOURCES.
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
        link_el = card.select_one("a.knowmore[href]")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
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
    soup = BeautifulSoup(html_text, "html.parser")
    out = []
    for card in soup.select("div.sif-card"):
        title_el = card.select_one("h4.card-heading")
        desc_el = card.select_one("div.card-desc")
        valid_el = card.select_one("div.article-date")
        link_el = card.select_one("a[data-href]")
        title = title_el.get_text(strip=True) if title_el else None
        if not title:
            continue
        out.append({
            "title": title,
            "description": desc_el.get_text(strip=True) if desc_el else "",
            "url": urljoin(base_url, link_el["data-href"]) if link_el else base_url,
            "promo_code": None,
            "valid_till": _parse_valid_till(valid_el.get_text(" ", strip=True) if valid_el else ""),
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
        "url": "https://www.axisbank.com/offers",
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
        "url": "https://www.kotak.com/en/offers.html",
        "parser": _parse_kotak,
    },
    {
        "name": "BOBCard Offers",
        "issuer": "BOB Financial (BOBCard)",
        "url": "https://www.bobcard.co.in/credit-card-offers",
        "parser": _parse_bobcard,
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
        html_text = _get(src["url"])
        if not html_text:
            continue
        try:
            offers = src["parser"](html_text, src["url"])
        except Exception as e:
            log.warning("Parse error (%s): %s", src["name"], e)
            offers = []
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
