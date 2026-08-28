#!/usr/bin/env python3
"""Haalt de volledige TheCocktailDB op en schrijft die naar src/API/cocktails.json.

De site leest de cocktails uit een lokaal json-bestand, zodat er tijdens het
gebruik geen enkele aanvraag naar TheCocktailDB nodig is. Dit script bouwt dat
bestand opnieuw op.

    python3 tools/fetch_cocktails.py

De gratis api geeft per zoekletter maximaal 25 resultaten terug. Daarom wordt er
na de letters ook per categorie, glas, ingrediënt en soort gefilterd, en worden
de id's die daarbij nieuw opduiken los opgevraagd.
"""

import json
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.thecocktaildb.com/api/json/v1/1"
DOEL = Path(__file__).resolve().parent.parent / "src" / "API" / "cocktails.json"

# Alleen deze velden gebruikt de site. De vertaalde instructies (ES, DE, FR, IT,
# ZH) laten we weg: die maken het bestand ruim twee keer zo groot.
VELDEN = [
    "idDrink",
    "strDrink",
    "strCategory",
    "strIBA",
    "strAlcoholic",
    "strGlass",
    "strTags",
    "strVideo",
    "strInstructions",
    "strDrinkThumb",
]

MAX_INGREDIENTEN = 15


def haal(url, pogingen=4):
    for poging in range(pogingen):
        try:
            verzoek = urllib.request.Request(url, headers={"User-Agent": "SmartList/1.0"})
            with urllib.request.urlopen(verzoek, timeout=30) as antwoord:
                return json.loads(antwoord.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as fout:
            print(f"  nieuwe poging {poging + 1} voor {url}: {fout}", file=sys.stderr)
            time.sleep(2 * (poging + 1))
    return None


def per_letter():
    drankjes = {}
    for teken in list(string.ascii_lowercase) + list(string.digits):
        data = haal(f"{BASE}/search.php?f={teken}")
        aantal = 0
        for drank in (data or {}).get("drinks") or []:
            drankjes[drank["idDrink"]] = drank
            aantal += 1
        print(f"letter {teken}: +{aantal} (totaal {len(drankjes)})")
        time.sleep(0.3)
    return drankjes


def ontbrekende_ids(bekend):
    ontbreekt = set()
    filters = [
        ("c", "strCategory"),
        ("g", "strGlass"),
        ("i", "strIngredient1"),
        ("a", "strAlcoholic"),
    ]

    for sleutel, veld in filters:
        lijst = haal(f"{BASE}/list.php?{sleutel}=list")
        waarden = [rij[veld] for rij in (lijst or {}).get("drinks") or [] if rij.get(veld)]
        print(f"filter {sleutel}: {len(waarden)} waarden")

        for waarde in waarden:
            resultaat = haal(f"{BASE}/filter.php?{sleutel}={urllib.parse.quote(waarde)}")
            rijen = (resultaat or {}).get("drinks")
            if not isinstance(rijen, list):
                continue
            for rij in rijen:
                drank_id = rij.get("idDrink")
                if drank_id and drank_id not in bekend:
                    ontbreekt.add(drank_id)
            time.sleep(0.15)

    return ontbreekt


def uitkleden(rij):
    resultaat = {veld: rij.get(veld) for veld in VELDEN if rij.get(veld)}

    for i in range(1, MAX_INGREDIENTEN + 1):
        naam = (rij.get(f"strIngredient{i}") or "").strip()
        if not naam:
            continue
        resultaat[f"strIngredient{i}"] = naam
        hoeveelheid = (rij.get(f"strMeasure{i}") or "").strip()
        if hoeveelheid:
            resultaat[f"strMeasure{i}"] = hoeveelheid

    return resultaat


def main():
    drankjes = per_letter()

    ontbreekt = ontbrekende_ids(set(drankjes))
    print(f"nog op te halen id's: {len(ontbreekt)}")
    for drank_id in sorted(ontbreekt):
        data = haal(f"{BASE}/lookup.php?i={drank_id}")
        rijen = (data or {}).get("drinks") or []
        if rijen:
            drankjes[drank_id] = rijen[0]
        time.sleep(0.2)

    if len(drankjes) < 500:
        print(f"FOUT: maar {len(drankjes)} drankjes gevonden, dat lijkt niet compleet.", file=sys.stderr)
        return 1

    uitvoer = sorted((uitkleden(rij) for rij in drankjes.values()), key=lambda d: d["strDrink"].lower())
    DOEL.write_text(json.dumps(uitvoer, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(uitvoer)} drankjes geschreven naar {DOEL}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
