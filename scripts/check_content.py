import json

with open("data/2026-05-28/content.json", "r", encoding="utf-8") as f:
    content = json.load(f)
print("Items in content.json:", len(content["items"]))
ids = [item["source_id"] for item in content["items"]]
print("Source IDs:", ids)
