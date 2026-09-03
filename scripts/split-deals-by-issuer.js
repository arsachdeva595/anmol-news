#!/usr/bin/env node
// Splits deals.json into per-issuer feeds under deals/by-issuer/<slug>.json
// for consumption by Payload CMS API Blocks on Monzy issuer pages.

const fs = require('fs');
const path = require('path');

const DEALS_PATH = path.join(__dirname, '..', 'deals.json');
const OUT_DIR = path.join(__dirname, '..', 'deals', 'by-issuer');

const ISSUER_SLUG_MAP = {
  // Axis Bank
  "Axis Bank": "axis-bank",

  // HDFC Bank
  "HDFC Bank": "hdfc-bank",
  "HDFC": "hdfc-bank",

  // HSBC India
  "HSBC": "hsbc-india",
  "HSBC India": "hsbc-india",

  // ICICI Bank
  "ICICI Bank": "icici-bank",
  "ICICI": "icici-bank",

  // SBI Card
  "SBI Card": "sbi-card",
  "SBI": "sbi-card",
  "SBI Cards": "sbi-card",

  // Bank of Baroda (BOBCard)
  "BOB Financial (BOBCard)": "bank-of-baroda",
  "BOB Financial": "bank-of-baroda",
  "BOBCard": "bank-of-baroda",
  "Bank of Baroda": "bank-of-baroda",

  // Kotak Mahindra Bank
  "Kotak": "kotak-mahindra-bank",
  "Kotak Mahindra Bank": "kotak-mahindra-bank",
  "Kotak Mahindra": "kotak-mahindra-bank",

  // IndusInd Bank
  "IndusInd Bank": "indusind-bank",
  "IndusInd": "indusind-bank",

  // RBL Bank
  "RBL Bank": "rbl-bank",
  "RBL": "rbl-bank",

  // IDFC First Bank
  "IDFC First Bank": "idfc-first-bank",
  "IDFC FIRST Bank": "idfc-first-bank",
  "IDFC First": "idfc-first-bank",

  // Yes Bank
  "Yes Bank": "yes-bank",
  "YES Bank": "yes-bank",

  // American Express (India)
  "American Express": "amex",
  "American Express (India)": "amex",
  "Amex": "amex",

  // Standard Chartered India
  "Standard Chartered": "standard-chartered-india",
  "Standard Chartered India": "standard-chartered-india",
  "SCB": "standard-chartered-india",

  // Small finance banks
  "AU Small Finance Bank": "au-sfb",
  "AU SFB": "au-sfb",
  "Equitas Small Finance Bank": "equitas-sfb",
  "Equitas SFB": "equitas-sfb",

  // Others
  "Federal Bank": "federal-bank",
  "DBS Bank India": "dbs-bank",
  "DBS Bank": "dbs-bank",
  "DBS": "dbs-bank",
  "Canara Bank": "canara-bank",
  "IDBI Bank": "idbi-bank",
  "PNB": "punjab-national-bank",
  "Punjab National Bank": "punjab-national-bank",
  "Union Bank of India": "union-bank-of-india",
  "Union Bank": "union-bank-of-india",
  "Bank of India": "bank-of-india",
  "BOI": "bank-of-india",
  "South Indian Bank": "south-indian-bank",
  "SIB": "south-indian-bank",
  "Karur Vysya Bank": "karur-vysya-bank",
  "KVB": "karur-vysya-bank"
};

function todayInKolkata() {
  // en-CA formatting gives YYYY-MM-DD directly.
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date());
}

function main() {
  const raw = fs.readFileSync(DEALS_PATH, 'utf8');
  const data = JSON.parse(raw);
  const deals = Array.isArray(data.deals) ? data.deals : [];

  const today = todayInKolkata();
  const unmapped = new Set();
  const byIssuer = new Map();

  let kept = 0;
  let droppedExpired = 0;
  let droppedNoIssuer = 0;
  let droppedUnmapped = 0;

  for (const deal of deals) {
    const issuers = deal.issuers;
    if (!Array.isArray(issuers) || issuers.length === 0) {
      droppedNoIssuer++;
      continue;
    }

    if (deal.valid_till && deal.valid_till < today) {
      droppedExpired++;
      continue;
    }

    let matchedAny = false;
    for (const name of issuers) {
      const slug = ISSUER_SLUG_MAP[name];
      if (!slug) {
        unmapped.add(name);
        continue;
      }
      matchedAny = true;
      if (!byIssuer.has(slug)) byIssuer.set(slug, []);
      byIssuer.get(slug).push(deal);
    }

    if (matchedAny) {
      kept++;
    } else {
      droppedUnmapped++;
    }
  }

  fs.mkdirSync(OUT_DIR, { recursive: true });

  const indexIssuers = [];
  for (const [slug, list] of [...byIssuer.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
    list.sort((a, b) => (b.published || '').localeCompare(a.published || ''));
    fs.writeFileSync(
      path.join(OUT_DIR, `${slug}.json`),
      JSON.stringify(list, null, 2) + '\n'
    );
    indexIssuers.push({ slug, count: list.length });
  }

  const index = {
    generated_at: new Date().toISOString(),
    source: 'deals.json',
    issuers: indexIssuers,
  };
  fs.writeFileSync(
    path.join(OUT_DIR, '_index.json'),
    JSON.stringify(index, null, 2) + '\n'
  );

  console.log('--- split-deals-by-issuer summary ---');
  console.log(`Total deals processed: ${deals.length}`);
  console.log(`Kept (fanned out across issuers): ${kept}`);
  console.log(`Dropped - expired (valid_till < ${today}): ${droppedExpired}`);
  console.log(`Dropped - missing issuers: ${droppedNoIssuer}`);
  console.log(`Dropped - unmapped issuer only: ${droppedUnmapped}`);
  console.log('Issuers written:');
  for (const { slug, count } of indexIssuers) {
    console.log(`  ${slug}: ${count}`);
  }
  if (unmapped.size > 0) {
    console.log('Unmapped issuer display names encountered:');
    for (const name of unmapped) {
      console.error(`Unknown issuer: ${name}`);
    }
  }
}

main();
