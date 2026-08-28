#!/usr/bin/env python3
"""Haalt de afbeeldingen van de Wikibooks-gerechten binnen en zet ze in de repo.

Wikimedia Commons knijpt het aantal verzoeken per adres af (http 429). Bij het
doorbladeren van 1110 kaarten vraagt een bezoeker er tientallen achter elkaar op,
en dan lopen die tegen die grens aan. Daarom staan de afbeeldingen van de
geïmporteerde gerechten in de repo zelf, verkleind tot wat de kaarten nodig
hebben. De bronvermelding blijft in strImageSource staan.

    python3 tools/fetch_images.py            # alleen wat nog niet binnen is
    python3 tools/fetch_images.py --force    # alles opnieuw ophalen

Alleen id's vanaf 90000 (de Wikibooks-import) worden lokaal opgeslagen; de
gerechten van TheMealDB blijven naar themealdb.com wijzen.
"""

import argparse
import json
import sys
import time
import urllib.request
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
MEALS = ROOT / "src" / "API" / "recipes.json"
IMAGE_DIR = ROOT / "src" / "Images" / "recipes"
RELATIVE = "Images/recipes"

MAX_WIDTH = 500
MAX_HEIGHT = 500
QUALITY = 80
PAUSE = 1.2  # seconden tussen twee verzoeken, om niet afgeknepen te worden


def download(url, tries=4):
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "SmartList/1.0 (https://smartlist.vannaarden.dev; recipe image import)",
            })
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as err:
            wait = 5 * (attempt + 1)
            print(f"    nieuwe poging over {wait}s: {err}", file=sys.stderr)
            time.sleep(wait)
    return None


def save_resized(data, target):
    """Schaalt de afbeelding naar wat de kaart nodig heeft en slaat hem op als jpeg."""
    image = Image.open(BytesIO(data))
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    image.thumbnail((MAX_WIDTH, MAX_HEIGHT), Image.LANCZOS)
    image.save(target, "JPEG", quality=QUALITY, optimize=True, progressive=True)
    return target.stat().st_size


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--force", action="store_true", help="ook opnieuw ophalen wat er al staat")
    parser.add_argument("--limit", type=int, default=0, help="stop na zoveel afbeeldingen (om te testen)")
    args = parser.parse_args()

    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    meals = json.loads(MEALS.read_text(encoding="utf-8"))

    todo = []
    for meal in meals:
        if int(meal["idMeal"]) < 90000:
            continue
        target = IMAGE_DIR / f"{meal['idMeal']}.jpg"
        local = f"{RELATIVE}/{meal['idMeal']}.jpg"
        if target.exists() and not args.force:
            meal["strMealThumb"] = local
            continue
        if meal["strMealThumb"].startswith(RELATIVE):
            # al lokaal, maar het bestand is er niet meer: url niet meer bekend
            print(f"  {meal['idMeal']}: staat als lokaal in de json maar het bestand mist", file=sys.stderr)
            continue
        todo.append((meal, target, local))

    print(f"op te halen: {len(todo)} afbeeldingen")
    done, failed, total_bytes = 0, [], 0
    for meal, target, local in todo:
        if args.limit and done >= args.limit:
            break
        data = download(meal["strMealThumb"])
        if not data:
            failed.append(meal["idMeal"])
            print(f"  MISLUKT {meal['idMeal']} {meal['strMeal'][:40]}")
            time.sleep(PAUSE)
            continue
        try:
            size = save_resized(data, target)
        except Exception as err:
            failed.append(meal["idMeal"])
            print(f"  ONLEESBAAR {meal['idMeal']}: {err}")
            time.sleep(PAUSE)
            continue

        meal["strMealThumb"] = local
        total_bytes += size
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(todo)} ({total_bytes // 1024} kB tot nu toe)")
        time.sleep(PAUSE)

    MEALS.write_text(json.dumps(meals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"opgeslagen: {done}, mislukt: {len(failed)}, totaal {total_bytes // 1024} kB")
    if failed:
        print(f"mislukte id's: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
