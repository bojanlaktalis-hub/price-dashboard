#!/usr/bin/env python3
"""
Reads the chains' own published price lists (the "Проверка на цени" tables) with a headless browser.

  python chain_scraper.py --probe            # shows what each page looks like (run this first, and after a site changes)
  python chain_scraper.py [--only Zur]       # daily run: dairy products only, appended to prices_log.csv

One reference store per chain (see CHAINS). Product names are matched to the same categories Pazarluk uses.
"""
import argparse, csv, datetime as dt, os, re, sys
from pazarluk_scraper import COLUMNS, OUT_CSV, ensure_header, num

CHAINS = {  # "stores" = words (normalised) to look for in the store dropdown, best match first
    "Zur":    {"url": "https://ceni.zur.mk/", "stores": ["novolisice", "lisice"]},
    "Zito":   {"url": "https://zito.proverkanaceni.mk/", "stores": ["novolisice", "lisice"]},
    "Kam":    {"url": "https://kam.com.mk/ceni-vo-marketi.nspx", "stores": ["novolisice", "lisice"]},
    "Tamaro": {"url": "https://tamaro.mk/proverka-na-ceni/", "stores": []},
    "Spar":   {"url": "https://spar.mk/pricelist", "stores": []},
}
TR = dict(zip("абвгдѓежзѕијклљмнњопрстќуфхцчџш", ["a","b","v","g","d","g","e","z","z","z","i","j","k","l","l","m","n","n","o","p","r","s","t","k","u","f","h","c","c","d","s"]))
CATS = [("grck", "Грчки јогурт"), ("kiselomleko", "Кисело млеко"), ("jogurt", "Јогурти"), ("pavlaka", "Павлака"),
        ("puter", "Путер"), ("urda", "Урда"), ("namaz", "Млечен намаз"), ("sirene", "Сирење и кашкавал"),
        ("kaskaval", "Сирење и кашкавал"), ("mleko", "Млеко")]
HEAD = {"name": "име", "sell": "продажна", "unit": "единечна", "desc": "опис", "avail": "достап",
        "reg": "редовна", "promo": "акциска", "ptype": "вид", "period": "времетр"}


def nz(s):
    return re.sub(r"[^a-z0-9]", "", "".join(TR.get(c, c) for c in str(s).lower()))


def category_of(name):
    n = nz(name)
    if "mleko" in n and "cokolad" in n:
        return "Млеко чоколадно"
    return next((c for k, c in CATS if k in n), None)


def colmap(heads):
    m = {}
    for k, w in HEAD.items():
        for i, h in enumerate(heads):
            if w in h.lower() and i not in m.values():
                m[k] = i
                break
    return m


def to_records(rows, cm, updated, url):
    out = []
    for r in rows:
        g = lambda k: r[cm[k]] if k in cm and cm[k] < len(r) else ""
        cat = category_of(g("name"))
        if not cat:
            continue
        promo = num(g("promo"))
        out.append({"product_name_raw": g("name"), "product_name": g("name").strip(), "category": cat, "unit": g("unit"),
                    "selling_price": num(g("sell")), "regular_price": num(g("reg")), "discount_price": promo or "",
                    "discount_pct": "", "promo_type": g("ptype"), "promo_period": g("period"), "available": g("avail"),
                    "list_updated": updated, "url": url, "brand": ""})
    return out


def pick_store(page, hints):
    for hint in hints:
        for sel in page.query_selector_all("select"):
            for v, t in sel.eval_on_selector_all("option", "els=>els.map(e=>[e.value,e.textContent.trim()])"):
                if hint in nz(t):
                    sel.evaluate("(el,v)=>{el.value=v;el.dispatchEvent(new Event('change',{bubbles:true}));"
                                 "if(window.jQuery)jQuery(el).trigger('change')}", v)
                    page.wait_for_timeout(5000)
                    return t
    return ""


def open_chain(browser, cfg):
    page = browser.new_page()
    page.goto(cfg["url"], wait_until="domcontentloaded", timeout=90000)
    page.wait_for_timeout(4000)
    return page, pick_store(page, cfg["stores"])


def read_rows(page):
    page.wait_for_selector("table tbody tr td", timeout=90000)
    heads = [h.inner_text().strip() for h in page.query_selector_all("table thead th")]
    sel = page.query_selector("select[name$='_length']")
    if sel:
        vals = sel.eval_on_selector_all("option", "els=>els.map(e=>e.value)")
        sel.select_option("-1" if "-1" in vals else max(vals, key=lambda v: int(v) if v.isdigit() else 0))
        page.wait_for_timeout(1500)
    rows, seen = [], set()
    while True:
        for tr in page.query_selector_all("table tbody tr"):
            tds = tuple(td.inner_text().strip() for td in tr.query_selector_all("td"))
            if tds and tds not in seen:
                seen.add(tds); rows.append(list(tds))
        nxt = page.query_selector(".paginate_button.next:not(.disabled)")
        if not nxt:
            break
        nxt.click(); page.wait_for_timeout(700)
    m = re.search(r"ажурирање[^:\n]*:\s*(.+)", page.inner_text("body"))
    return heads, rows, (m.group(1).strip() if m else "")


def probe(browser, chain, cfg):
    print(f"\n===== {chain}  {cfg['url']}")
    try:
        page, store = open_chain(browser, cfg)
        print("title:", page.title(), "| store chosen:", store or "(none)")
        for i, sel in enumerate(page.query_selector_all("select")):
            opts = sel.eval_on_selector_all("option", "els=>els.map(e=>e.textContent.trim())")
            print(f" select #{i}: {len(opts)} options:", opts[:12])
        print(" tables:", len(page.query_selector_all("table")))
        try:
            heads, rows, upd = read_rows(page)
            print(" headers:", heads, "| mapped:", colmap(heads), "| rows:", len(rows), "| updated:", upd)
            for r in rows[:3]:
                print("  ", r)
        except Exception as e:
            print(" no table read:", str(e)[:150])
    except Exception as e:
        print(" FAILED:", str(e)[:200])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright
    today = dt.date.today().isoformat()
    ensure_header()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for chain, cfg in CHAINS.items():
            if a.only and a.only.lower() != chain.lower():
                continue
            if a.probe:
                probe(browser, chain, cfg); continue
            try:
                page, store = open_chain(browser, cfg)
                heads, rows, upd = read_rows(page)
                cm = colmap(heads)
                if "name" not in cm or "sell" not in cm:
                    print(chain, "skipped, unexpected columns:", heads); continue
                recs = to_records(rows, cm, upd, cfg["url"])
                label = store or "референтна продавница"
                if os.path.exists(OUT_CSV):
                    with open(OUT_CSV, encoding="utf-8-sig", newline="") as f:
                        if any(r["date"] == today and r["store_chain"] == chain and r["store_name"] == label for r in csv.DictReader(f)):
                            print(chain, "already logged today"); continue
                new = not os.path.exists(OUT_CSV)
                with open(OUT_CSV, "a", encoding="utf-8-sig", newline="") as f:
                    w = csv.DictWriter(f, fieldnames=COLUMNS, restval="")
                    if new: w.writeheader()
                    for r in recs:
                        w.writerow({"date": today, "store_chain": chain, "store_name": label, **r})
                print(f"{chain}: saved {len(recs)} dairy rows of {len(rows)} ({label})")
            except Exception as e:
                print(chain, "FAILED:", str(e)[:200])
        browser.close()


if __name__ == "__main__":
    main()
