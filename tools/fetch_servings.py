#!/usr/bin/env python3
"""Haalt het aantal personen en de bereidingstijd uit de bronpagina van elk gerecht.

TheMealDB heeft geen veld voor het aantal personen, en het zelf schatten uit de
hoeveelheden bleek waardeloos: die schatting was niet beter dan altijd "4" gokken
(26 procent precies goed tegen 27 procent). Daarom halen we het echte getal op.

Bijna elke kooksite zet schema.org-gegevens in de pagina, met `recipeYield` en
`totalTime`. Eén parser werkt daardoor voor bbcgoodfood, allrecipes, simplyrecipes
en de rest. De Wikibooks-gerechten hebben het aantal in hun eigen samenvatting staan; dat
leest dit script uit de pagina-cache van de import.

De antwoorden worden gecachet, dus een tweede run vraagt niets opnieuw op. Er zit
een pauze tussen de verzoeken; het is één verzoek per recept.

    python3 tools/fetch_servings.py --cache <map>            # ophalen en wegschrijven
    python3 tools/fetch_servings.py --cache <map> --dry-run

Velden die worden gezet:
    strServings        aantal, als tekst
    strServingsUnit    "personen" of "stuks"
    strServingsSource  "source" (de bron zei het) of leeg
    strTotalTime       totale tijd in minuten, als tekst
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEALS = ROOT / "src" / "API" / "recipes.json"

PAUSE = 1.0
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SmartList/1.0; personal recipe project)",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en",
}

# Woorden die zeggen dat de opbrengst in stuks is en niet in personen.
PIECES = re.compile(r"(?i)\b(cookies?|biscuits?|pieces?|muffins?|cupcakes?|slices?|bars?|balls?|"
                    r"rolls?|buns?|loaf|loaves|jars?|dozen|patties|pancakes?|waffles?|scones?|"
                    r"tarts?|truffles?|fritters?|dumplings?|samosas?|skewers?|drinks?)\b")


def fetch(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as err:
            if err.code in (404, 410, 403, 401):
                return None  # niet meer aanwezig of geblokkeerd, niet blijven proberen
            time.sleep(2 * (attempt + 1))
        except Exception:
            time.sleep(2 * (attempt + 1))
    return None


def find_recipes(node, found):
    """Zoekt alle schema.org Recipe-objecten in een json-ld boom."""
    if isinstance(node, dict):
        types = node.get("@type")
        types = types if isinstance(types, list) else [types]
        if "Recipe" in types:
            found.append(node)
        for value in node.values():
            find_recipes(value, found)
    elif isinstance(node, list):
        for value in node:
            find_recipes(value, found)
    return found


def read_schema(html):
    """Geeft {yield, time} uit de schema.org-gegevens in de pagina."""
    blocks = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
                        html, re.S | re.I)
    for block in blocks:
        try:
            data = json.loads(block.strip())
        except json.JSONDecodeError:
            continue
        for recipe in find_recipes(data, []):
            return {
                "yield": recipe.get("recipeYield"),
                "totalTime": recipe.get("totalTime"),
                "cookTime": recipe.get("cookTime"),
                "prepTime": recipe.get("prepTime"),
            }
    return None


def parse_yield(value):
    """Geeft (aantal, eenheid) uit recipeYield, of (None, None)."""
    options = value if isinstance(value, list) else [value]
    texts = [str(option) for option in options if option is not None]

    for text in texts:
        # Een kaal getal is het aantal personen of stuks
        match = re.match(r"^\s*(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*$", text)
        if match:
            low = int(match.group(1))
            high = int(match.group(2)) if match.group(2) else low
            amount = round((low + high) / 2)
            if 1 <= amount <= 60:
                # Een kaal getal zonder eenheid: boven de twaalf gaat het vrijwel
                # altijd om stuks. "60" bij een koekjesrecept zijn 60 koekjes en
                # geen 60 personen.
                pieces = any(PIECES.search(other) for other in texts) or amount > 12
                return amount, "stuks" if pieces else "personen"

    for text in texts:
        match = re.search(r"(?i)\b(\d+)(?:\s*(?:-|–|to)\s*(\d+))?\s*(servings?|portions?|people|persons)\b", text)
        if match:
            low = int(match.group(1))
            high = int(match.group(2)) if match.group(2) else low
            amount = round((low + high) / 2)
            if 1 <= amount <= 60:
                return amount, "personen"

    for text in texts:
        if PIECES.search(text):
            match = re.search(r"\b(\d+)\b", text)
            if match and 1 <= int(match.group(1)) <= 60:
                return int(match.group(1)), "stuks"

    return None, None


def parse_duration(value):
    """PT1H30M -> 90 minuten."""
    if not value or not isinstance(value, str):
        return None
    match = re.match(r"(?i)^P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", value.strip())
    if not match:
        return None
    days, hours, minutes = (int(group) if group else 0 for group in match.groups())
    total = days * 1440 + hours * 60 + minutes
    return total if 0 < total <= 2880 else None


def wikibooks_servings(cache):
    """Leest het servings-veld uit de opgehaalde Wikibooks-pagina's."""
    path = Path(cache) / "wb_pages.json"
    if not path.exists():
        print(f"geen wb_pages.json in {cache}, Wikibooks-aantallen overgeslagen", file=sys.stderr)
        return {}

    pages = json.loads(path.read_text(encoding="utf-8"))
    result = {}
    for title, page in pages.items():
        match = re.search(r"(?i)\|\s*servings?\s*=\s*([^|}\n]+)", page["wikitext"])
        if not match:
            continue
        amount, unit = parse_yield(match.group(1).strip())
        if amount:
            result[title.replace("Cookbook:", "").strip()] = (amount, unit)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", required=True, help="map voor het antwoordbestand")
    parser.add_argument("--dry-run", action="store_true", help="niets wegschrijven naar recipes.json")
    parser.add_argument("--limit", type=int, default=0, help="stop na zoveel verzoeken")
    args = parser.parse_args()

    cache_path = Path(args.cache) / "source_schema.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
    print(f"al opgehaald: {len(cache)}")

    meals = json.loads(MEALS.read_text(encoding="utf-8"))
    urls = []
    for meal in meals:
        url = (meal.get("strSource") or "").strip()
        if url.startswith("http") and "wikibooks.org" not in url and url not in cache:
            urls.append(url)
    urls = list(dict.fromkeys(urls))
    print(f"nog op te halen: {len(urls)}")

    done = 0
    for url in urls:
        if args.limit and done >= args.limit:
            break
        html = fetch(url)
        cache[url] = read_schema(html) if html else None
        done += 1
        if done % 25 == 0:
            gelukt = sum(1 for v in cache.values() if v)
            print(f"  {done}/{len(urls)} opgehaald, met gegevens: {gelukt}")
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        time.sleep(PAUSE)

    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    from_wikibooks = wikibooks_servings(args.cache)
    print(f"aantallen uit Wikibooks: {len(from_wikibooks)}")

    counts = Counter()
    for meal in meals:
        # Geen verzonnen getallen: zelf schatten uit de hoeveelheden bleek niet
        # beter dan altijd "4" gokken, dus wat de bron niet zegt blijft leeg.
        meal.setdefault("strServings", None)
        meal.setdefault("strServingsUnit", None)
        meal.setdefault("strServingsSource", None)
        meal.setdefault("strTotalTime", None)

        wiki = from_wikibooks.get(meal["strMeal"])
        if wiki:
            meal["strServings"] = str(wiki[0])
            meal["strServingsUnit"] = wiki[1]
            meal["strServingsSource"] = "source"
            counts[f"Wikibooks, in {wiki[1]}"] += 1

        url = (meal.get("strSource") or "").strip()
        schema = cache.get(url)
        if not schema:
            if not meal["strServings"]:
                counts["geen gegevens"] += 1
            continue

        amount, unit = parse_yield(schema.get("yield"))
        if amount:
            meal["strServings"] = str(amount)
            meal["strServingsUnit"] = unit
            meal["strServingsSource"] = "source"
            counts[f"aantal in {unit}"] += 1

        minutes = (parse_duration(schema.get("totalTime"))
                   or (parse_duration(schema.get("cookTime")) or 0) + (parse_duration(schema.get("prepTime")) or 0))
        if minutes:
            meal["strTotalTime"] = str(minutes)
            counts["tijd"] += 1

    # Bij gebak en bijgerechten is een "serving" boven de twaalf een stuk en geen
    # persoon: bij 60 koekjes bedoelt de bron 60 koekjes.
    for meal in meals:
        if (meal.get("strServingsUnit") == "personen"
                and meal.get("strServings")
                and int(meal["strServings"]) > 12
                and meal.get("strCategory") in ("Dessert", "Breakfast", "Side", "Starter")):
            meal["strServingsUnit"] = "stuks"
            counts["gebak: personen -> stuks"] += 1

    met_aantal = sum(1 for m in meals if m["strServings"])
    met_tijd = sum(1 for m in meals if m["strTotalTime"])
    print("\nresultaat:")
    for key, value in counts.most_common():
        print(f"  {value:>5} {key}")
    print(f"\n  {met_aantal} van {len(meals)} gerechten hebben een aantal, {met_tijd} een tijd")

    if not args.dry_run:
        MEALS.write_text(json.dumps(meals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nweggeschreven naar {MEALS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
