import json

with open("data/2026-05-28/content.json", "r", encoding="utf-8") as f:
    content = json.load(f)
failed_ids = {"48295679", "48293080"}
for item in content["items"]:
    if item["source_id"] in failed_ids:
        item["enrichment_source"] = "manual_override"
        print(f"Marked {item['source_id']} as manual_override")
with open("data/2026-05-28/content.json", "w", encoding="utf-8") as f:
    json.dump(content, f, ensure_ascii=False, indent=2)
print("Done")
