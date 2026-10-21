#!/usr/bin/env python3
"""
Pazarluk.mk dairy scraper: one price per retail chain for every dairy product.

  pip install requests beautifulsoup4
  python pazarluk_scraper.py --only jogurti --limit 5     # small test first
  python pazarluk_scraper.py                              # full daily run

Appends to prices_log.csv (same columns as vero_scraper.py).
Be polite: one run per day. Ask Pazarluk.mk for permission or a data feed (see their Contact page).
"""
import argparse, csv, datetime as dt, os, re, sys, time
from urllib.parse import urljoin, unquote
import requests
from bs4 import BeautifulSoup

BASE = "https://pazarluk.mk/"
CATEGORIES = {  # slug -> category name
    "sirenje-i-kashkaval": "Сирење и кашкавал", "mlechen-namaz": "Млечен намаз", "jogurti": "Јогурти",
    "mleko": "Млеко", "pavlaka": "Павлака", "grchki-jogurt": "Грчки јогурт", "puter": "Путер",
    "ovoshen-jogurt": "Овошен јогурт", "kiselo-mleko": "Кисело млеко",
    "mleko-chokoladno": "Млеко чоколадно", "urda": "Урда"}
STORE = "цена по синџир"
OUT_CSV, DELAY, MAX_PAGES = "prices_log.csv", 1.0, 80
HEADERS = {"User-Agent": "Mozilla/5.0 (price-survey research script)"}
COLUMNS = ["date", "store_chain", "store_name", "product_name_raw", "product_name", "category",
           "unit", "selling_price", "regular_price", "discount_price", "discount_pct",
           "promo_type", "promo_period", "available", "list_updated", "url", "brand"]


def ensure_header():
    """Old log files have no brand column: add it (empty) so new rows line up."""
    if not os.path.exists(OUT_CSV):
        return
    with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        if "brand" in (rd.fieldnames or []):
            return
        old = list(rd)
    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, restval="")
        w.writeheader()
        w.writerows(old)


def num(t):
    m = re.search(r"\d[\d.,]*", t or "")
    if not m:
        return None
    s = m.group(0)
    if "," in s and "." in s: s = s.replace(".", "").replace(",", ".")
    elif "," in s: s = s.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s): s = s.replace(".", "")
    try: return float(s)
    except ValueError: return None


def get(url, session):
    r = session.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    r.encoding = "utf-8"
    return r.text


def product_links(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.find_all("a", href=True):
        u = urljoin(page_url, a["href"])
        if "/products/" in u and u not in out:
            out.append(u)
    return out


def category_products(slug, session, limit=None):
    seen = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{BASE}{slug}" + (f"?page={page}" if page > 1 else "")
        new = [u for u in product_links(get(url, session), url) if u not in seen]
        if not new:
            break
        seen += new
        print(f"  {slug} page {page}: {len(seen)} products")
        if limit and len(seen) >= limit:
            return seen[:limit]
        time.sleep(DELAY)
    return seen


def parse_product(html, url):
    """Return (title, updated_text, [(chain, price, is_promo)], min30, max30, brand)."""
    soup = BeautifulSoup(html, "html.parser")
    brand = ""                                            # the first brand link after the words "од брендот"
    t = soup.find(string=re.compile("од брендот"))
    if t:
        a = t.find_next("a", href=re.compile("/brand/"))
        if a:
            brand = (a.get_text(strip=True) or (a.find("img") or {}).get("alt", "")).strip()
    for img in soup.find_all("img"):                      # chain logos carry the chain name in alt
        img.replace_with(f" @@{(img.get('alt') or '').strip()}@@ ")
    h1 = soup.find("h1")
    title = h1.get_text(" ", strip=True) if h1 else unquote(url.rsplit("/", 1)[-1])
    text = soup.get_text(" ", strip=True)
    m = re.search(r"Последно ажурирано:\s*(.+?)\s+@@", text)
    updated = m.group(1) if m else ""
    start = text.find("Последно ажурирано")
    end = text.find("Просечна цена низ време")
    region = text[start:end] if start >= 0 and end > start else text
    chains, parts = [], re.split(r"@@([^@]*)@@", region)
    for i in range(1, len(parts) - 1, 2):
        chunk = parts[i + 1]
        pm = re.search(r"(\d[\d.,]*)\s*ден", chunk)
        if parts[i] and pm:
            chains.append((parts[i], num(pm.group(1)), "Акциска цена" in chunk))
    mm = re.search(r"Минимум:\s*([\d.,]+)\s*ден\s*Максимум:\s*([\d.,]+)", text)
    return title, updated, chains, (num(mm.group(1)) if mm else None), (num(mm.group(2)) if mm else None), brand


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="one category slug, e.g. jogurti")
    ap.add_argument("--limit", type=int, help="max products per category (for testing)")
    ap.add_argument("--replace-today", action="store_true", help="delete today's Pazarluk rows and scrape them again")
    a = ap.parse_args()
    today = dt.date.today().isoformat()
    ensure_header()
    if a.replace_today and os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
            keep = [r for r in csv.DictReader(f) if not (r["date"] == today and r["store_name"] == STORE)]
        with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLUMNS, restval="")
            w.writeheader()
            w.writerows(keep)
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
            if any(r["date"] == today and r["store_name"] == STORE for r in csv.DictReader(f)):
                print(f"Pazarluk already logged for {today} - nothing to add.")
                return
    s, rows, done = requests.Session(), [], set()
    for slug, cat in CATEGORIES.items():
        if a.only and slug != a.only:
            continue
        print("Category", cat)
        for url in category_products(slug, s, a.limit):
            if url in done:
                continue
            done.add(url)
            try:
                title, upd, chains, _, _, brand = parse_product(get(url, s), url)
            except Exception as e:
                print("  skipped", url, e); continue
            if a.limit:
                print("  ", title, "| brand:", brand or "(none found)")
            if not chains:
                print("  no prices found:", url)
            for chain, price, promo in chains:
                rows.append({"date": today, "store_chain": chain, "store_name": STORE,
                             "product_name_raw": unquote(url.rsplit("/", 1)[-1]), "product_name": title,
                             "category": cat, "unit": "", "selling_price": price, "regular_price": "",
                             "discount_price": price if promo else "", "discount_pct": "",
                             "promo_type": "Акциска цена" if promo else "", "promo_period": "",
                             "available": "", "list_updated": upd, "url": url, "brand": brand})
            time.sleep(DELAY)
    if not rows:
        sys.exit("No rows collected - the page layout may have changed.")
    new = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new: w.writeheader()
        w.writerows(rows)
    print(f"Saved {len(rows)} price rows for {len(done)} products to {OUT_CSV}")


if __name__ == "__main__":
    main()
