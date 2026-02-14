import json

d = json.load(open("tile_data.json", encoding="utf-8-sig"))
for t in d:
    if t["gen"] == 4:
        combos = ", ".join(f'{c["with"]}={c["produces"]}' for c in t["combinations"])
        cf = "+".join(t["createdFrom"]) if t["createdFrom"] else "(starting)"
        print(f'{t["name"]} (Gen {t["gen"]}): {cf} | combos: {combos}')
