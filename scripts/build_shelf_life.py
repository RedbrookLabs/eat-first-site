#!/usr/bin/env python3
"""
Builds data/shelf_life.json from the USDA FoodKeeper dataset.

Runs monthly in GitHub Actions (see .github/workflows/update-data.yml), which opens a pull request.
You can also run it by hand on your Mac:
    python3 scripts/build_shelf_life.py

REVIEW THE DIFF before merging a pull request: merging publishes the list to the app.
The numbers are USDA guidance for quality and safety, not a guarantee, and the app tells
users to check the package. Each entry uses the SHORTEST time in USDA's range (the cautious end).

If USDA changes the file layout this script stops and prints what it found instead of guessing.
"""
import datetime, json, math, pathlib, sys, urllib.request

URL = "https://www.fsis.usda.gov/shared/data/EN/foodkeeper.json"
OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "shelf_life.json"

TO_DAYS = {"hours": lambda n: max(1, math.ceil(n / 24)), "day": lambda n: n, "days": lambda n: n,
           "week": lambda n: n * 7, "weeks": lambda n: n * 7,
           "month": lambda n: n * 30, "months": lambda n: n * 30,
           "year": lambda n: n * 365, "years": lambda n: n * 365}

def row_to_dict(row):
    out = {}
    for cell in row:
        out.update(cell)
    return out

def days_for(rec, prefix):
    """Prefers the 'date of purchase' columns (DOP_*), falls back to the plain ones."""
    for pre in ("DOP_" + prefix, prefix):
        low, metric = rec.get(pre + "_Min"), rec.get(pre + "_Metric")
        if low in (None, "") or not metric:
            continue
        convert = TO_DAYS.get(str(metric).strip().lower())
        if convert is None:
            continue
        try:
            return int(convert(float(low)))
        except (TypeError, ValueError):
            continue
    return None

def main():
    with urllib.request.urlopen(URL, timeout=60) as response:
        raw = json.load(response)

    sheet = next((s for s in raw.get("sheets", []) if s.get("name") == "Product"), None)
    if sheet is None:
        sys.exit("Could not find a 'Product' sheet. Sheets found: %s" % [s.get("name") for s in raw.get("sheets", [])])

    records = [row_to_dict(r) for r in sheet["data"]]
    if not records or "Name" not in records[0]:
        sys.exit("Unexpected layout. Fields in first record: %s" % list(records[0].keys() if records else []))

    entries, seen = [], set()
    for rec in records:
        name = str(rec.get("Name", "")).strip()
        subtitle = str(rec.get("Name_subtitle") or "").strip()
        full = f"{name}, {subtitle}" if subtitle else name
        if not name or full.lower() in seen:
            continue
        days, place = days_for(rec, "Refrigerate"), "Fridge"
        if days is None:
            days, place = days_for(rec, "Pantry"), "Pantry"
        if days is None or days <= 0:
            continue
        seen.add(full.lower())
        entries.append({"foodName": full, "days": days, "locationName": place})

    entries.sort(key=lambda e: e["foodName"].lower())
    if len(entries) < 50:
        sys.exit(f"Only {len(entries)} usable entries. The USDA layout probably changed; not writing anything.")

    previous = {}
    if OUT.exists():
        try:
            previous = json.loads(OUT.read_text())
        except ValueError:
            previous = {}
    if previous.get("entries") == entries:
        print("No changes in the USDA data.")
        return

    OUT.write_text(json.dumps({
        "version": int(previous.get("version", 0)) + 1,
        "updated": datetime.date.today().isoformat(),
        "source": "USDA FSIS FoodKeeper (" + URL + "). Shortest value of each range.",
        "entries": entries}, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {len(entries)} entries to {OUT}. Review the diff before merging.")

if __name__ == "__main__":
    main()
