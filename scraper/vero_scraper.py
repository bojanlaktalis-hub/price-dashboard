#!/usr/bin/env python3
"""
Vero price-list scraper (reference store: Vero 2).

Usage
  pip install requests beautifulsoup4
  python vero_scraper.py --list-categories     # first run: shows every category in the store list
  python vero_scraper.py                       # daily run: keeps only categories in dairy_categories.txt

Output: prices_log.csv (appended; a store is not written twice for the same date).
Be polite: one run per day, delay between pages. Check the site's terms before use.
"""
import argparse, csv, datetime as dt, os, re, sys, time
from collections import Counter
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE = "https://pricelist.vero.com.mk/"
STORE_NAME_MATCH = "ВЕРО 2"          # link text on the index page
CHAIN = "Vero"
CATEGORY_FILE = "dairy_categories.txt"  # one category per line, exactly as printed by --list-categories
OUT_CSV = "prices_log.csv"
DELAY_SECONDS = 2
HEADERS = {"User-Agent": "Mozilla/5.0 (price-survey research script)"}

COLUMNS = ["date", "store_chain", "store_name", "product_name_raw", "product_name", "category",
           "unit", "selling_price", "regular_price", "discount_price", "discount_pct",
           "promo_type", "promo_period", "available", "list_updated", "url"]

# Legacy encoding seen in Vero names (Cyrillic typed on a Latin layout). Extend after checking more data.
LEGACY = {"@": "Ж", "[": "Ш", "^": "Ч"}


def fix_name(raw: str) -> str:
    """Replace the legacy special characters. Plain Latin letters are left as they are."""
    return "".join(LEGACY.get(ch, ch) for ch in raw).strip()


def num(text):
    """'1.879' / '126' / '126,50' -> float, or None."""
    t = (text or "").replace("\xa0", " ").strip()
    m = re.search(r"\d[\d.,]*", t)
    if not m:
        return None
    s = m.group(0)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):   # 1.879 = thousands separator
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def get(url, session):
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def find_store_url(session):
    soup = BeautifulSoup(get(BASE, session), "html.parser")
    for a in soup.find_all("a"):
        if a.get_text(strip=True).upper() == STORE_NAME_MATCH:
            return urljoin(BASE, a["href"])
    sys.exit(f"Could not find a link named '{STORE_NAME_MATCH}' on {BASE}")


def parse_page(html, url):
    """Return (rows, list_updated, next_url)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Последно ажурирање:\s*([\d/]+\s+[\d:]+)", text)
    updated = m.group(1) if m else ""
    rows = []
    for tr in soup.find_all("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(tds) < 10:
            continue
        name, sell, unit_price, avail, cat, reg, disc, disc_pct, promo, period = tds[:10]
        unit = unit_price.split("ден/")[-1].strip() if "ден/" in unit_price else ""
        rows.append({
            "product_name_raw": name, "product_name": fix_name(name), "category": cat.strip(),
            "unit": unit, "selling_price": num(sell), "regular_price": num(reg),
            "discount_price": num(disc), "discount_pct": num(disc_pct),
            "promo_type": promo, "promo_period": period,
            "available": avail, "list_updated": updated, "url": url,
        })
    next_url = None
    for a in soup.find_all("a"):
        if "🠊" in a.get_text() and a.get("href"):
            next_url = urljoin(url, a["href"])
    return rows, updated, next_url


def scrape_store(session):
    url = find_store_url(session)
    store_label = STORE_NAME_MATCH.title()
    all_rows, seen = [], set()
    while url and url not in seen:
        seen.add(url)
        print("Fetching", url)
        rows, _, nxt = parse_page(get(url, session), url)
        all_rows += rows
        url = nxt
        time.sleep(DELAY_SECONDS)
    return store_label, all_rows


def load_categories():
    if not os.path.exists(CATEGORY_FILE):
        sys.exit(f"{CATEGORY_FILE} not found. Run with --list-categories first, then put the dairy "
                 f"categories (one per line) into {CATEGORY_FILE}.")
    with open(CATEGORY_FILE, encoding="utf-8") as f:
        return {l.strip() for l in f if l.strip() and not l.startswith("#")}


def already_logged(today, store):
    if not os.path.exists(OUT_CSV):
        return False
    with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
        return any(r["date"] == today and r["store_chain"] == CHAIN and r["store_name"] == store
                   for r in csv.DictReader(f))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-categories", action="store_true")
    args = ap.parse_args()
    session = requests.Session()
    store, rows = scrape_store(session)
    if not rows:
        sys.exit("No product rows found - the page layout may have changed.")

    if args.list_categories:
        for cat, n in sorted(Counter(r["category"] for r in rows).items()):
            print(f"{n:6d}  {cat}")
        return

    wanted = load_categories()
    kept = [r for r in rows if r["category"] in wanted]
    today = dt.date.today().isoformat()
    if already_logged(today, store):
        sys.exit(f"{store} already logged for {today}.")
    new_file = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new_file:
            w.writeheader()
        for r in kept:
            w.writerow({"date": today, "store_chain": CHAIN, "store_name": store, **r})
    print(f"Saved {len(kept)} of {len(rows)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
