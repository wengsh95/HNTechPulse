import json

with open("data/2026-05-28/content.json", "r", encoding="utf-8") as f:
    content = json.load(f)
failed_ids = {"48295679", "48293080"}
content["brief_indices"] = [
    i
    for i in content["brief_indices"]
    if content["items"][i]["source_id"] not in failed_ids
]
print(f"New brief_indices: {content['brief_indices']}")
with open("data/2026-05-28/content.json", "w", encoding="utf-8") as f:
    json.dump(content, f, ensure_ascii=False, indent=2)
print("Done")
