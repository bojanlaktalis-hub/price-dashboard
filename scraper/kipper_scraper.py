#!/usr/bin/env python3
"""
Kipper scraper (reference store: Kipper 083, Kumanovo).
The price table on Kipper's page is filled in by JavaScript, so this uses a real (headless) browser.

  python kipper_scraper.py --list-categories   # first run: shows the categories and a few sample rows
  python kipper_scraper.py                     # daily run: keeps only categories listed in kipper_categories.txt

Appends to prices_log.csv, same columns as the other scrapers.
"""
import argparse, csv, datetime as dt, os, re, sys
from collections import Counter

from pazarluk_scraper import COLUMNS, OUT_CSV, ensure_header, num

URL = "https://kipper.mk/mk/kipper-83-kumanove/"
CHAIN, STORE = "Kipper", "Kipper 083 Куманово"
CATEGORY_FILE = "kipper_categories.txt"
HEADERS = ["Име на артикал", "Продажна цена", "Единечна цена", "Опис на стока", "Достапност во маркет",
           "Редовна цена", "Акциска цена", "Вид на продажно поттикнување", "Времетраење на промоција"]


def to_records(rows, updated):
    out = []
    for name, sell, unit_price, desc, avail, reg, promo, ptype, period in rows:
        out.append({"product_name_raw": name, "product_name": name.strip(), "category": desc.strip(),
                    "unit": unit_price, "selling_price": num(sell), "regular_price": num(reg),
                    "discount_price": num(promo) if num(promo) else "", "discount_pct": "",
                    "promo_type": ptype, "promo_period": period, "available": avail,
                    "list_updated": updated, "url": URL, "brand": ""})
    return out


def scrape():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=90000)   # the page never gets fully "idle" (ads), so do not wait for that
        page.wait_for_selector("table tbody tr td", timeout=90000)
        heads = [h.inner_text().strip() for h in page.query_selector_all("table thead th")]
        if heads[:9] != HEADERS:
            sys.exit(f"The table columns are different from expected: {heads}")
        m = re.search(r"последно ажурирање на цените:\s*(.+)", page.inner_text("body"))
        updated = m.group(1).strip() if m else ""
        sel = page.query_selector("select[name$='_length']")      # "show N entries" box, if there is one
        if sel:
            vals = sel.eval_on_selector_all("option", "els=>els.map(e=>e.value)")
            sel.select_option("-1" if "-1" in vals else max(vals, key=lambda v: int(v) if v.isdigit() else 0))
            page.wait_for_timeout(1000)
        rows, seen = [], set()
        while True:
            for tr in page.query_selector_all("table tbody tr"):
                tds = tuple(td.inner_text().strip() for td in tr.query_selector_all("td"))
                if len(tds) >= 9 and tds not in seen:
                    seen.add(tds); rows.append(tds[:9])
            nxt = page.query_selector(".paginate_button.next:not(.disabled)")
            if not nxt:
                break
            nxt.click(); page.wait_for_timeout(700)
        browser.close()
    return to_records(rows, updated)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--list-categories", action="store_true")
    a = ap.parse_args()
    recs = scrape()
    if not recs:
        sys.exit("No rows found - the page layout may have changed.")
    if a.list_categories:
        print(f"{len(recs)} rows. Categories ('Опис на стока'):")
        for c, n in sorted(Counter(r["category"] for r in recs).items()):
            print(f"{n:6d}  {c}")
        print("\nSample rows:")
        for r in recs[:8]:
            print(r["product_name"], "|", r["selling_price"], "|", r["category"], "|", r["promo_type"])
        return
    if not os.path.exists(CATEGORY_FILE):
        sys.exit(f"{CATEGORY_FILE} not found. Run with --list-categories first.")
    wanted = {l.strip() for l in open(CATEGORY_FILE, encoding="utf-8") if l.strip() and not l.startswith("#")}
    kept = [r for r in recs if r["category"] in wanted]
    today = dt.date.today().isoformat()
    ensure_header()
    if os.path.exists(OUT_CSV):
        with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
            if any(r["date"] == today and r["store_name"] == STORE for r in csv.DictReader(f)):
                print(f"{STORE} already logged for {today} - nothing to add.")
                return
    new = not os.path.exists(OUT_CSV)
    with open(OUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new: w.writeheader()
        for r in kept:
            w.writerow({"date": today, "store_chain": CHAIN, "store_name": STORE, **r})
    print(f"Saved {len(kept)} of {len(recs)} rows to {OUT_CSV}")


if __name__ == "__main__":
    main()
