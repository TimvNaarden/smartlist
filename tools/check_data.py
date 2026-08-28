#!/usr/bin/env python3
"""Controleert recipes.json en cocktails.json op fouten en inconsistenties.

Wat er wordt nagekeken, per record:
  - de stappen: genoeg stappen, geen "step 1" of eigen nummering, geen
    achtergebleven wikimarkup, elke stap begint met een hoofdletter
  - de ingrediënten: geen gaten in de reeks, geen maat zonder ingrediënt, geen
    naam met cijfers of leestekens aan het eind
  - de maten: alleen de canonieke eenheden, geen "tablespoon" of "grams"
  - de rest: geldige categorie, afbeelding aanwezig, geen dubbele id's

    python3 tools/check_data.py            # samenvatting per soort fout
    python3 tools/check_data.py --detail   # met de eerste voorbeelden erbij
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "API"

CATEGORIES = {"Beef", "Breakfast", "Chicken", "Dessert", "Goat", "Lamb", "Miscellaneous",
              "Pasta", "Pork", "Seafood", "Side", "Starter", "Vegan", "Vegetarian"}

# Eenheden die na normalisatie mogen voorkomen.
ALLOWED_UNITS = {
    "g", "kg", "ml", "l", "cl", "dl", "oz", "lb", "tsp", "tbsp", "cup", "cups", "pint", "pints",
    "quart", "quarts", "shot", "shots", "jigger", "jiggers", "part", "parts", "dash", "dashes",
    "drop", "drops", "splash", "splashes", "measure", "measures", "clove", "cloves", "sprig",
    "sprigs", "slice", "slices", "stick", "sticks", "stalk", "stalks", "leaf", "leaves", "floret",
    "florets", "piece", "pieces", "head", "heads", "bulb", "bulbs", "pod", "pods", "fillet",
    "fillets", "yolk", "yolks", "wedge", "wedges", "rasher", "rashers", "shank", "shanks", "strip",
    "strips", "can", "cans", "jar", "jars", "tub", "tubs", "pack", "packs", "bag", "bags", "bottle",
    "bottles", "pot", "pots", "scoop", "scoops", "bunch", "bunches", "handful", "handfuls", "pinch",
    "pinches", "knob", "knobs", "tail", "tails", "cm", "mm", "twist", "twists", "gallon", "gallons",
    "cube", "cubes", "glass", "glasses", "large", "medium", "small", "whole", "thin", "thick",
    "fresh", "extra", "jumbo", "baby", "big", "cm", "mm", "thumb-sized", "marble-sized",
    "portion", "portions", "cake", "cakes", "block", "blocks",
}

# Spellingen die niet meer mogen voorkomen omdat er een canonieke vorm voor is.
FORBIDDEN_IN_MEASURE = re.compile(
    r"(?i)\b(tablespoons?|teaspoons?|tbs|tbls|tblsp|grams?|kilograms?|litres?|liters?|"
    r"millilitres?|milliliters?|ounces?|pounds?|lbs|packets?|tins?|handfull|sprinking|spinkling)\b"
)

WIKI_LEFTOVER = re.compile(r"(\[\[|\]\]|\{\{|\}\}|<ref|</ref|File:|Image:|&nbsp;|&amp;|&#\d+;|'''|\|thumb)")


def measure_problems(measure):
    """Geeft de reden waarom een maat niet aan de vorm voldoet, of None."""
    if not measure:
        return None
    if FORBIDDEN_IN_MEASURE.search(measure):
        return "oude eenheidspelling in de maat"
    if measure != measure.strip():
        return "witruimte om de maat"
    if re.search(r"\s{2,}", measure):
        return "dubbele spatie in de maat"
    if measure[0].islower() and not re.match(r"^\d", measure):
        return "maat begint met een kleine letter"

    head = measure.split(",")[0].strip()
    if re.match(r"^\d", head):
        rest = re.sub(r"^[\d.\-/ ]+", "", head).strip()
        if rest:
            for word in rest.split(" "):
                if word.startswith("("):
                    break
                if word.lower() not in ALLOWED_UNITS:
                    return f"onbekende eenheid: {word!r}"
    return None


def check_record(record, slots, kind):
    problems = []
    name = record.get("strMeal") or record.get("strDrink") or "?"

    # ---- titel en afbeelding
    if not name or len(name) < 2:
        problems.append("titel ontbreekt")
    if WIKI_LEFTOVER.search(name):
        problems.append("wikimarkup in de titel")
    thumb = record.get("strMealThumb") or record.get("strDrinkThumb") or ""
    # Of een https-url, of een afbeelding die in de repo staat.
    if not (thumb.startswith("https://") or thumb.startswith("Images/")):
        problems.append("geen geldige afbeelding")
    elif thumb.startswith("Images/") and not (SRC.parent / thumb).exists():
        problems.append("afbeelding staat niet in de repo")

    if kind == "meal" and record.get("strCategory") not in CATEGORIES:
        problems.append(f"onbekende categorie: {record.get('strCategory')!r}")

    # ---- ingrediënten en maten
    seen_empty = False
    filled = 0
    for i in range(1, slots + 1):
        ingredient = (record.get(f"strIngredient{i}") or "").strip()
        measure = (record.get(f"strMeasure{i}") or "").strip()

        if not ingredient:
            if measure:
                problems.append(f"maat zonder ingrediënt op plek {i}")
            seen_empty = True
            continue
        if seen_empty:
            problems.append(f"gat in de ingrediëntenlijst voor plek {i}")
            seen_empty = False
        filled += 1

        if ingredient != ingredient.strip():
            problems.append("witruimte om een ingrediëntnaam")
        # Cijfers mogen in een naam (7-Up, 151 Proof Rum), een hoeveelheid niet.
        if re.search(r"(?i)(^|\s)[\d/.]+\s*(tsp|tbsp|cups?|grams?|g|kg|ounces?|oz|lb|ml|l)\b", ingredient):
            problems.append(f"hoeveelheid in de naam: {ingredient!r}")
        if re.search(r"[,;.]$", ingredient):
            problems.append(f"leesteken aan het eind van de naam: {ingredient!r}")
        if WIKI_LEFTOVER.search(ingredient):
            problems.append(f"wikimarkup in de naam: {ingredient!r}")
        if len(ingredient) > 45:
            problems.append(f"naam te lang: {ingredient!r}")
        if ingredient[0].islower():
            problems.append(f"naam begint met kleine letter: {ingredient!r}")

        reason = measure_problems(measure)
        if reason:
            problems.append(f"{reason} ({measure!r} bij {ingredient!r})")

    if filled < 2:
        problems.append("minder dan 2 ingrediënten")

    # ---- bereidingswijze
    instructions = record.get("strInstructions") or ""
    steps = [s for s in instructions.split("\n") if s.strip()]
    if not steps:
        problems.append("geen bereidingswijze")
    if kind == "meal" and len(steps) == 1 and len(steps[0]) > 300:
        problems.append("één stap met een heel lange tekst")
    for step in steps:
        if re.match(r"(?i)^step\s*\d", step):
            problems.append("stap begint nog met 'step N'")
            break
        if re.match(r"^\d+[.)]\s", step):
            problems.append("stap begint nog met een eigen nummer")
            break
        if re.fullmatch(r"\d+[.)]?", step.strip()):
            problems.append("stap bestaat alleen uit een cijfer")
            break
        if WIKI_LEFTOVER.search(step):
            problems.append("wikimarkup in een stap")
            break
        if step[0].islower():
            problems.append("stap begint met een kleine letter")
            break
        if len(step) > 900:
            problems.append("stap langer dan 900 tekens")
            break
        if re.search(r"\s{2,}", step):
            problems.append("dubbele spatie in een stap")
            break
    if "\r" in instructions:
        problems.append("CR in de bereidingswijze")

    return name, problems


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detail", action="store_true", help="voorbeelden per soort fout laten zien")
    parser.add_argument("--max-examples", type=int, default=4)
    args = parser.parse_args()

    total_problems = 0
    for filename, slots, kind, id_field in (("recipes.json", 20, "meal", "idMeal"),
                                            ("cocktails.json", 15, "drink", "idDrink")):
        path = SRC / filename
        rows = json.loads(path.read_text(encoding="utf-8"))
        counter = Counter()
        examples = defaultdict(list)
        bad_records = 0

        ids = Counter(row[id_field] for row in rows)
        duplicates = [i for i, c in ids.items() if c > 1]

        for row in rows:
            name, problems = check_record(row, slots, kind)
            if problems:
                bad_records += 1
            for problem in problems:
                label = re.sub(r"\s*\(.*\)$", "", problem)
                label = re.sub(r":.*$", "", label)
                counter[label] += 1
                if len(examples[label]) < args.max_examples:
                    examples[label].append(f"{name}: {problem}")

        print(f"\n{filename}: {len(rows)} records, {bad_records} met een opmerking")
        if duplicates:
            print(f"  DUBBELE ID'S: {duplicates[:10]}")
        if not counter:
            print("  geen problemen gevonden")
        for label, count in counter.most_common():
            print(f"  {count:>5}x {label}")
            if args.detail:
                for example in examples[label]:
                    print(f"          {example[:150]}")
        total_problems += sum(counter.values())

    return 1 if total_problems else 0


if __name__ == "__main__":
    sys.exit(main())
