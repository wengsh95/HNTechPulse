import json

with open("data/2026-05-28/content.json", "r", encoding="utf-8") as f:
    content = json.load(f)
for item in content["items"]:
    if item["source_id"] in ("48295679", "48293080"):
        item["enrichment_source"] = "downloaded_page"
        item["enrichment_error"] = None
        print(f"Marked {item['source_id']} as downloaded_page")
with open("data/2026-05-28/content.json", "w", encoding="utf-8") as f:
    json.dump(content, f, ensure_ascii=False, indent=2)
print("Done")
