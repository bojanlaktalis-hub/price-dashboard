"""Turns prices_log.csv into ../data/prices.json for the dashboard."""
import csv, json, os
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
out = {"updated": max((i["h"][-1][0] for i in items.values()), default=""), "items": list(items.values())}
os.makedirs("../data", exist_ok=True)
json.dump(out, open("../data/prices.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(items), "products")
