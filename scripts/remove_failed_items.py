import json

with open("data/2026-05-28/content.json", "r", encoding="utf-8") as f:
    content = json.load(f)

# Check current state
for item in content["items"]:
    if item["source_id"] in ("48295679", "48293080"):
        print(f"{item['source_id']}: enrichment_source={item['enrichment_source']}")
        url = item.get("url", "N/A")
        print(f"  URL: {url}")
        # Remove from items
        print("  Removing this item...")

# Remove failed items
failed_ids = {"48295679", "48293080"}
content["items"] = [
    item for item in content["items"] if item["source_id"] not in failed_ids
]

# Rebuild indices - now only 8 items remain
content["brief_indices"] = list(range(len(content["items"])))

print(f"\nItems remaining: {len(content['items'])}")
print(f"brief_indices: {content['brief_indices']}")

with open("data/2026-05-28/content.json", "w", encoding="utf-8") as f:
    json.dump(content, f, ensure_ascii=False, indent=2)
print("Done")
