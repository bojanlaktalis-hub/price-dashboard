"""Turns prices_log.csv into ../data/prices.json for the dashboard."""
import csv, json, os, re

UNITS = {"кг": ("kg", 1), "kg": ("kg", 1), "гр": ("kg", .001), "gr": ("kg", .001), "г": ("kg", .001), "g": ("kg", .001),
         "мл": ("l", .001), "ml": ("l", .001), "л": ("l", 1), "l": ("l", 1), "lt": ("l", 1)}
UNIT_RE = r"(кг|kg|гр|gr|мл|ml|lt|л|l|г|g)(?![a-zа-я])"


def parse_size(name):
    """'ЈОГУРТ 2,8% 1Л' -> (1.0, 'l'); '4х125гр' -> (0.5, 'kg'); None if no size in the name."""
    t = name.lower().replace(",", ".")
    m = re.search(r"(\d+)\s*[xх]\s*(\d+(?:\.\d+)?)\s*" + UNIT_RE, t)
    if m:
        kind, f = UNITS[m.group(3)]
        return round(int(m.group(1)) * float(m.group(2)) * f, 4), kind
    m = re.search(r"(\d+(?:\.\d+)?)\s*" + UNIT_RE, t)
    if m:
        kind, f = UNITS[m.group(2)]
        return round(float(m.group(1)) * f, 4), kind
    if re.search(r"(?<![\wа-я])кг\s*$", t):      # sold by weight: name ends with "КГ", price is per kg
        return 1.0, "kg"
    return None

items = {}
with open("prices_log.csv", encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        k = f'{r["store_chain"]}|{r["store_name"]}|{r["product_name_raw"]}'
        it = items.setdefault(k, {"id": r["product_name_raw"], "chain": r["store_chain"], "store": r["store_name"], "h": []})
        it.update(name=r["product_name"], category=r["category"], unit=r["unit"])
        if r.get("brand"):
            it["brand"] = r["brand"]
        sell = float(r["selling_price"] or 0) or None
        reg = float(r["regular_price"] or 0) or None
        it["h"].append([r["date"], sell, reg, r["discount_price"] != ""])
for it in items.values():
    it["h"].sort(key=lambda x: x[0])
    s = parse_size(it.get("name", ""))
    if s:
        it["size"], it["kind"] = s
out = {"updated": max((i["h"][-1][0] for i in items.values()), default=""), "items": list(items.values())}
os.makedirs("../data", exist_ok=True)
json.dump(out, open("../data/prices.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(items), "products")
