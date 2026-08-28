#!/usr/bin/env python3
"""Haalt extra gerechten uit de Wikibooks Cookbook en voegt ze toe aan recipes.json.

TheMealDB is uitgeput: die database bevat 793 gerechten en die staan er al in. De
Wikibooks Cookbook is de enige grote bron die zonder sleutel te gebruiken is en
een vaste structuur heeft (== Ingredients == met opsomming, == Procedure == met
genummerde stappen).

De tekst van Wikibooks staat onder CC BY-SA 4.0 en de afbeeldingen onder hun eigen
licentie op Wikimedia Commons. Daarom krijgt elk geïmporteerd gerecht:

    strSource                    -> de Wikibooks-pagina
    strImageSource               -> de bestandspagina van de afbeelding
    strCreativeCommonsConfirmed  -> "Yes"

Gerechten uit deze bron krijgen een id vanaf 90001, zodat ze nooit botsen met
nieuwe id's van TheMealDB.

    python3 tools/fetch_wikibooks.py --limit 300

Daarna tools/normalize_data.py draaien; die maakt de maten en namen gelijk.
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEALS = ROOT / "src" / "API" / "recipes.json"
API = "https://en.wikibooks.org/w/api.php"
ID_START = 90001

sys.path.insert(0, str(Path(__file__).resolve().parent))
from normalize_data import (  # noqa: E402
    UNIT_ALIASES,
    clean_text,
    expand_fractions,
    normalize_ingredient,
    normalize_instructions,
    normalize_measure,
    space_units,
    title_case_name,
)

# ------------------------------------------------------------------ api

def api(params, post=False):
    payload = {**params, "format": "json", "formatversion": "2"}
    for attempt in range(4):
        try:
            if post:
                request = urllib.request.Request(API, data=urllib.parse.urlencode(payload).encode(),
                                                headers={"User-Agent": "SmartList/1.0 (recipe import)"})
            else:
                request = urllib.request.Request(f"{API}?{urllib.parse.urlencode(payload)}",
                                                headers={"User-Agent": "SmartList/1.0 (recipe import)"})
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode())
        except Exception as err:  # netwerkfout of tijdelijke storing
            print(f"  nieuwe poging: {err}", file=sys.stderr)
            time.sleep(2 * (attempt + 1))
    return {}


def all_recipe_titles():
    titles, cont = [], {}
    while True:
        data = api({"action": "query", "list": "categorymembers", "cmtitle": "Category:Recipes",
                    "cmlimit": "500", "cmnamespace": "102", **cont})
        titles += [row["title"] for row in data.get("query", {}).get("categorymembers", [])]
        if "continue" not in data:
            return titles
        cont = data["continue"]
        time.sleep(0.2)


def fetch_pages(titles):
    pages = {}
    for start in range(0, len(titles), 50):
        chunk = titles[start:start + 50]
        data = api({"action": "query", "prop": "revisions|categories", "rvprop": "content",
                    "rvslots": "main", "cllimit": "max", "titles": "|".join(chunk)}, post=True)
        for page in data.get("query", {}).get("pages", []):
            try:
                content = page["revisions"][0]["slots"]["main"]["content"]
            except (KeyError, IndexError):
                continue
            pages[page["title"]] = {
                "wikitext": content,
                "categories": [c["title"].replace("Category:", "") for c in page.get("categories", [])],
            }
        if start % 500 == 0:
            print(f"  {start}/{len(titles)} pagina's")
        time.sleep(0.15)
    return pages


def fetch_image_urls(filenames):
    """Geeft {bestandsnaam: (afbeeldings-url, bestandspagina-url)}.

    De api geeft bij te veel verzoeken achter elkaar een 429 terug, dus rustig
    aan en aan het eind nog een ronde voor wat niet lukte.
    """
    result = {}
    todo = sorted(set(filenames))

    for attempt in range(3):
        if not todo:
            break
        if attempt:
            print(f"  tweede ronde voor {len(todo)} afbeeldingen")
            time.sleep(5)
        for start in range(0, len(todo), 40):
            chunk = todo[start:start + 40]
            data = api({"action": "query", "prop": "imageinfo", "iiprop": "url",
                        "iiurlwidth": "600", "titles": "|".join(f"File:{n}" for n in chunk)}, post=True)
            for page in data.get("query", {}).get("pages", []):
                info = (page.get("imageinfo") or [{}])[0]
                url = info.get("thumburl") or info.get("url")
                if url:
                    result[page["title"].replace("File:", "")] = (
                        url.split("?")[0],
                        (info.get("descriptionurl") or "").split("?")[0],
                    )
            time.sleep(0.6)
        todo = [name for name in todo if name not in result]

    return result


# ------------------------------------------------------------------ wikitext

def strip_wiki(text):
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S | re.I)
    text = re.sub(r"<ref[^>]*/>", "", text, flags=re.I)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[([^\]|]*)\|([^\]]*)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]*)\]\]", lambda m: m.group(1).split(":")[-1], text)
    text = re.sub(r"\[https?://\S+\s+([^\]]*)\]", r"\1", text)
    text = re.sub(r"'''?([^']*)'''?", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"')
    return re.sub(r"\s+", " ", text).strip()


def section(wikitext, names):
    for name in names:
        match = re.search(r"(?mi)^==+\s*" + re.escape(name) + r"\s*==+\s*$", wikitext)
        if not match:
            continue
        rest = wikitext[match.end():]
        end = re.search(r"(?m)^==\s*[^=]", rest)
        return rest[:end.start()] if end else rest
    return None


def bullets(block, marker):
    out = []
    for line in (block or "").split("\n"):
        line = line.strip()
        if not line.startswith(marker) or line.startswith(marker * 2):
            continue
        text = strip_wiki(line[len(marker):])
        if text and not re.match(r"(?i)^(file|image):", text):
            out.append(text)
    return out


def image_name(wikitext):
    match = re.search(r"(?i)\|\s*image\s*=\s*\[\[\s*(?:File|Image):\s*([^|\]]+)", wikitext)
    if match:
        return match.group(1).strip()
    match = re.search(r"(?im)^\s*\[\[(?:File|Image):\s*([^|\]]+)", wikitext)
    return match.group(1).strip() if match else None


# ------------------------------------------------------------------ indeling

# Van een Wikibooks-categorie naar een categorie van TheMealDB.
CATEGORY_RULES = [
    ("Dessert", ["dessert", "cake", "cookie", "biscuit", "pudding", "ice cream", "candy", "confection",
                 "pie", "pastry", "sweet", "chocolate", "tart", "doughnut", "brownie"]),
    ("Breakfast", ["breakfast", "pancake", "porridge", "cereal"]),
    ("Seafood", ["seafood", "fish", "shrimp", "prawn", "shellfish", "crab", "lobster", "squid", "salmon", "tuna"]),
    ("Chicken", ["chicken", "poultry", "turkey", "duck"]),
    ("Beef", ["beef", "steak", "veal"]),
    ("Pork", ["pork", "bacon", "ham", "sausage"]),
    ("Lamb", ["lamb", "mutton"]),
    ("Goat", ["goat"]),
    ("Pasta", ["pasta", "noodle", "spaghetti", "macaroni", "lasagna"]),
    ("Vegan", ["vegan"]),
    ("Vegetarian", ["vegetarian", "vegetable", "salad", "tofu"]),
    ("Starter", ["appetizer", "starter", "dip", "snack", "fritter"]),
    ("Side", ["side dish", "side", "bread", "rice", "sauce", "condiment", "relish", "chutney", "potato"]),
]

# Van "<X> recipes" naar (strArea, strCountry) zoals TheMealDB die schrijft.
AREAS = {
    "american": ("American", "United States"), "argentine": ("Argentinian", "Argentina"),
    "australian": ("Australian", "Australia"), "austrian": ("Austrian", "Austria"),
    "bangladeshi": ("Bangladeshi", "Bangladesh"), "belgian": ("Belgian", "Belgium"),
    "brazilian": ("Brazilian", "Brazil"), "british": ("British", "United Kingdom"),
    "bulgarian": ("Bulgarian", "Bulgaria"), "cambodian": ("Cambodian", "Cambodia"),
    "canadian": ("Canadian", "Canada"), "caribbean": ("Caribbean", "Caribbean"),
    "chilean": ("Chilean", "Chile"), "chinese": ("Chinese", "China"),
    "colombian": ("Colombian", "Colombia"), "croatian": ("Croatian", "Croatia"),
    "cuban": ("Cuban", "Cuba"), "czech": ("Czech", "Czechia"),
    "danish": ("Danish", "Denmark"), "dutch": ("Dutch", "Netherlands"),
    "egyptian": ("Egyptian", "Egypt"), "english": ("British", "United Kingdom"),
    "ethiopian": ("Ethiopian", "Ethiopia"), "filipino": ("Filipino", "Philippines"),
    "finnish": ("Finnish", "Finland"), "french": ("French", "France"),
    "german": ("German", "Germany"), "ghanaian": ("Ghanaian", "Ghana"),
    "greek": ("Greek", "Greece"), "hungarian": ("Hungarian", "Hungary"),
    "indian": ("Indian", "India"), "indonesian": ("Indonesian", "Indonesia"),
    "iranian": ("Iranian", "Iran"), "iraqi": ("Iraqi", "Iraq"),
    "irish": ("Irish", "Ireland"), "israeli": ("Israeli", "Israel"),
    "italian": ("Italian", "Italy"), "jamaican": ("Jamaican", "Jamaica"),
    "japanese": ("Japanese", "Japan"), "kenyan": ("Kenyan", "Kenya"),
    "korean": ("Korean", "South Korea"), "lebanese": ("Lebanese", "Lebanon"),
    "malaysian": ("Malaysian", "Malaysia"), "mexican": ("Mexican", "Mexico"),
    "moroccan": ("Moroccan", "Morocco"), "nepalese": ("Nepalese", "Nepal"),
    "nigerian": ("Nigerian", "Nigeria"), "norwegian": ("Norwegian", "Norway"),
    "pakistani": ("Pakistani", "Pakistan"), "peruvian": ("Peruvian", "Peru"),
    "polish": ("Polish", "Poland"), "portuguese": ("Portuguese", "Portugal"),
    "romanian": ("Romanian", "Romania"), "russian": ("Russian", "Russia"),
    "scottish": ("Scottish", "United Kingdom"), "serbian": ("Serbian", "Serbia"),
    "singaporean": ("Singaporean", "Singapore"), "south african": ("South African", "South Africa"),
    "spanish": ("Spanish", "Spain"), "sri lankan": ("Sri Lankan", "Sri Lanka"),
    "swedish": ("Swedish", "Sweden"), "swiss": ("Swiss", "Switzerland"),
    "syrian": ("Syrian", "Syria"), "thai": ("Thai", "Thailand"),
    "tunisian": ("Tunisian", "Tunisia"), "turkish": ("Turkish", "Turkey"),
    "ukrainian": ("Ukrainian", "Ukraine"), "vietnamese": ("Vietnamese", "Vietnam"),
    "welsh": ("Welsh", "United Kingdom"),
}

# Keuken en soort gerecht die aansluiten bij de smaak in de bestaande selectie.
TASTE_AREAS = {"Vietnamese": 6, "Thai": 6, "Chinese": 5, "Japanese": 5, "Korean": 5, "Malaysian": 4,
               "Indonesian": 4, "Singaporean": 4, "Filipino": 3, "Spanish": 5, "Turkish": 5,
               "Lebanese": 4, "Moroccan": 4, "Israeli": 3, "Syrian": 3, "Indian": 3, "Mexican": 3,
               "Italian": 2, "Greek": 2, "Brazilian": 2}
TASTE_CATEGORIES = {"Vegetarian": 4, "Seafood": 4, "Chicken": 3, "Side": 3, "Starter": 3,
                    "Dessert": 3, "Beef": 2, "Pasta": 2, "Vegan": 2, "Lamb": 2, "Pork": 1,
                    "Breakfast": 1, "Miscellaneous": 0, "Goat": 0}
TASTE_WORDS = {"noodle": 3, "salad": 3, "chilli": 2, "chili": 2, "lime": 2, "peanut": 2, "sesame": 2,
               "grilled": 2, "skewer": 2, "kebab": 2, "curry": 2, "tapas": 2, "chocolate": 3,
               "caramel": 3, "cheesecake": 3, "stir": 2, "rice": 1, "dumpling": 2, "tofu": 2,
               "coconut": 2, "ginger": 1, "garlic": 1, "pancake": 1, "fritter": 1}


# Woorden in de ingrediëntenlijst die een gerecht niet vegetarisch maken.
MEAT_WORDS = {
    "Beef": ["beef", "steak", "veal", "oxtail", "brisket", "snout"],
    "Chicken": ["chicken", "turkey", "duck", "poultry"],
    "Pork": ["pork", "bacon", "ham", "sausage", "chorizo", "pancetta", "lard"],
    "Lamb": ["lamb", "mutton"],
    "Seafood": ["fish", "prawn", "shrimp", "salmon", "tuna", "cod", "crab", "lobster", "squid",
                "anchovy", "clam", "mussel", "oyster", "octopus", "sardine"],
    "Goat": ["goat"],
}


def classify(entry):
    """Bepaalt categorie en keuken.

    Alleen categorieën die over het soort gerecht gaan tellen mee. "Recipes using
    fish sauce" zei eerder dat een Thaise curry een visgerecht was.
    """
    dish_categories = [
        category for category in entry["categories"]
        if not category.lower().startswith("recipes using")
        and not category.lower().startswith("recipes with")
        and not category.lower().startswith("recipes without")
    ]
    haystack = " | ".join(dish_categories + [entry["summary_category"], entry["name"]]).lower()

    category = "Miscellaneous"
    for name, words in CATEGORY_RULES:
        if any(word in haystack for word in words):
            category = name
            break

    # Het hoofdingrediënt wint van een categorie als "salad" of "vegetable".
    ingredient_text = " ".join(entry["ingredients"]).lower()
    title = entry["name"].lower()

    def mentions(text, words):
        # Op hele woorden, anders vindt "ham" ook "Champorado".
        return any(re.search(rf"\b{re.escape(word)}s?\b", text) for word in words)

    if category != "Breakfast":
        for meat, words in MEAT_WORDS.items():
            in_title = mentions(title, words)
            if in_title or (category in ("Vegetarian", "Vegan") and mentions(ingredient_text, words)):
                category = meat
                break

    area = country = None
    for key, (area_name, country_name) in AREAS.items():
        if f"{key} recipes" in haystack or f"cuisine of {key}" in haystack:
            area, country = area_name, country_name
            break

    return category, area, country


def taste_score(entry, category, area):
    score = TASTE_CATEGORIES.get(category, 0) + TASTE_AREAS.get(area, 0)
    text = (entry["name"] + " " + " ".join(entry["ingredients"])).lower()
    for word, weight in TASTE_WORDS.items():
        if word in text:
            score += weight
    if "easy recipes" in [c.lower() for c in entry["categories"]]:
        score += 2
    if "featured recipes" in [c.lower() for c in entry["categories"]]:
        score += 2
    # niet te lange ingrediëntenlijsten
    if len(entry["ingredients"]) > 16:
        score -= 3
    return score


# ------------------------------------------------------------------ ingrediëntregels

PREP_WORDS = {"chopped", "sliced", "diced", "minced", "crushed", "grated", "peeled", "beaten",
              "melted", "softened", "shredded", "cubed", "halved", "quartered", "julienned",
              "finely", "roughly", "thinly", "coarsely", "freshly", "lightly", "well",
              "drained", "rinsed", "washed", "trimmed", "seeded", "deseeded", "pitted",
              "toasted", "roasted", "cooked", "boiled", "warmed", "chilled", "divided",
              "optional", "plus", "more", "needed", "taste", "garnish", "serving", "cut", "into",
              "and", "or", "for", "to", "at", "room", "temperature", "very", "if", "desired"}

LEADING_NOISE = re.compile(
    r"(?i)^(?:at least|a little over|a little|just over|just under|about|approx\.?|approximately|"
    r"roughly|around|some|a few|few|>|~)\s*")

# Regels die twee dingen in één opsomming zetten; we houden het eerste deel.
CONNECTORS = re.compile(r"(?i)\s+(?:mixed with|combined with|dissolved in|and\s+\d|plus\s+\d)\b|\s*\+\s*\d")

# "1 ea. onion" betekent "1 onion".
EACH = re.compile(r"(?i)\bea\.?\s+")

# Bijvoeglijke naamwoorden die zelf geen ingrediënt zijn. Staat zo'n woord voor
# een "of"/"and", dan gaat het om alternatieven op het bijvoeglijk naamwoord
# ("red or green chiles") en niet om twee ingrediënten.
ADJECTIVE_ONLY = {"red", "green", "yellow", "white", "black", "brown", "dark", "light", "fresh",
                  "dried", "hot", "sweet", "mild", "large", "small", "thick", "thin", "ripe",
                  "raw", "cooked", "firm", "soft", "whole", "ground", "chopped", "sliced"}

# Namen die te vaag zijn om op een boodschappenlijst te zetten.
TOO_GENERIC = {"nuts", "nut", "beans", "bean", "meat", "fish", "seafood", "vegetables", "vegetable",
               "spices", "spice", "seasoning", "seasonings", "filling", "topping", "toppings",
               "garnish", "sauce", "other", "food colorings", "food coloring", "ingredients",
               "flour or", "salt or", "oil or", "water or", "fruit", "fruits", "herbs", "cheese",
               "milk or", "juice", "batter", "dough", "syrup", "stock", "broth", "liquid",
               "leaves", "leaf", "molds", "mold", "wrappers", "skins", "mix", "extract", "powder"}


def alternative_names(name):
    """Geeft de mogelijke lezingen van een regel met "of".

    "cilantro or parsley"                -> ["cilantro", "parsley"]
    "red or green bell peppers"          -> ["green bell peppers", ...]
    "live littleneck or mahogany clams"  -> ["live littleneck clams", "mahogany clams", ...]

    Welke lezing het wordt, beslist align_name aan de hand van de namen die al in
    de database staan.
    """
    for joiner in (" and/or ", " or ", " and "):
        index = name.lower().find(joiner)
        if index == -1:
            continue
        left, right = name[:index].strip(), name[index + len(joiner):].strip()
        if not left or not right:
            continue

        left_words, right_words = left.split(), right.split()
        if all(word.lower() in ADJECTIVE_ONLY for word in left_words):
            return alternative_names(right)

        options = [left]
        # het zelfstandig naamwoord staat vaak alleen achteraan
        if len(right_words) > 1:
            options.append(f"{left} {right_words[-1]}")
        options.append(right)
        if len(right_words) > 1:
            options.append(right_words[-1])
        seen, unique = set(), []
        for option in options:
            if option.lower() not in seen:
                seen.add(option.lower())
                unique.append(option)
        return unique
    return [name]

MEASURE_WORDS = set(UNIT_ALIASES) | {"pinch", "dash", "handful", "splash", "knob", "bunch"}


def finish(measure, name, prep):
    """Rondt een gesplitste regel af: mogelijke lezingen van de naam erbij."""
    name = name.strip(" ,.")
    if not name:
        return None
    return measure, "|".join(alternative_names(name)), prep.strip()


def split_ingredient_line(line):
    """Splitst "1 cup (240 ml) chopped onion" in ("1 cup", "onion", "chopped")."""
    text = clean_text(line)
    text = LEADING_NOISE.sub("", text)
    text = EACH.sub("", text)
    if not text:
        return None

    # "vegetable oil for frying": de bewerking eraf, de hoeveelheid blijft
    frying = ""
    match = re.search(r"(?i),?\s*for (?:deep[- ]?)?frying\s*$", text)
    if match:
        frying = "for frying"
        text = text[: match.start()].strip(" ,")

    # Eerst de haakjes met een dubbele maat eruit: "1 cup (300 ml / 1 cup + 2 tbsp)
    # sweet rice flour". Anders knipt de regel hieronder middenin die haakjes.
    text = expand_fractions(text)
    text = re.sub(r"\((?=[^)]*\b(?:g|kg|ml|l|oz|lb|grams?|ounces?|pounds?|millilitres?|milliliters?|"
                  r"cups?|sticks?|tablespoons?|teaspoons?|tbsp|tsp)\b)[^)]*\)", "", text)
    text = re.sub(r"\s+", " ", text).strip()

    # "½ cup vinegar mixed with 1 cup water and 1 tbsp salt" -> alleen het eerste deel
    cut = CONNECTORS.search(text)
    if cut:
        text = text[: cut.start()].strip(" ,")

    # "to taste" en soortgelijke staarten
    tail_measure = ""
    text = re.sub(r"(?i)\s+or\s+(to taste|as needed)\s*$", r", \1", text)
    tail = re.search(r"(?i),?\s*(to taste|as needed|as required|to serve|for garnish|to garnish|optional)\s*$", text)
    if tail:
        tail_measure = {"to taste": "To taste", "as needed": "As required", "as required": "As required",
                        "to serve": "To serve", "for garnish": "To garnish", "to garnish": "To garnish",
                        "optional": "Optional"}[tail.group(1).lower()]
        text = text[: tail.start()].strip(" ,")

    # "1 generous pinch of saffron", "a large loaf of crusty bread"
    of_measure = re.match(
        r"(?i)^(?:a|an|one|\d+)?\s*(?:generous|good|small|large|big|heaped|level)?\s*"
        r"(pinch|handful|dash|splash|knob|drizzle|sprinkle|loaf|slice|slices|bunch|can|jar|bottle|"
        r"packet|bag|sprig|sprigs|clove|cloves|stalk|head|bulb|piece|pieces|cake|block)\s+of\s+(.+)$", text)
    if of_measure:
        word = of_measure.group(1).lower()
        loose = {"pinch": "Pinch", "handful": "Handful", "dash": "Dash", "splash": "Splash",
                 "knob": "Knob", "drizzle": "Drizzle", "sprinkle": "For sprinkling"}
        count = re.match(r"^(\d+)", text)
        measure = loose.get(word, f"{count.group(1) if count else '1'} {word}")
        return finish(measure, of_measure.group(2), "")

    # "1 small piece of ginger" -> maat "1 piece", verder gewoon doorlopen
    text = re.sub(r"(?i)^(?:\d+(?:\.\d+)?|\d+/\d+)?\s*(?:thumb-sized|marble-sized|small|large|medium)?\s*piece of\s+",
                  "1 piece ", text)

    juice = re.match(r"(?i)^juice of\s+(?:(\d+(?:\s+\d+/\d+)?|\d+/\d+)\s+)?(?:a\s+|an\s+)?(.+)$", text)
    if juice:
        fruit = re.sub(r"(?i)\s*\([^)]*\)", "", juice.group(2)).strip().rstrip("s")
        fruit = CONNECTORS.split(fruit)[0].strip()
        return finish(f"Juice of {juice.group(1) or '1'}", f"{fruit} juice", "")

    number = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
    quantity = re.match(rf"^({number}\s*-\s*{number}|{number})\s*\+?\s*", text)
    measure_text = ""
    rest = text
    if quantity:
        measure_text = quantity.group(1).strip()
        rest = text[quantity.end():].strip()
        words = rest.split(" ")
        if words and words[0].lower().strip(".,") in MEASURE_WORDS:
            measure_text += " " + words[0].strip(".,")
            rest = " ".join(words[1:]).strip()
            rest = re.sub(r"(?i)^of\s+", "", rest).strip()

    # opmerkingen tussen haakjes weg, die horen niet in een naam
    rest = re.sub(r"\([^)]*\)", "", rest).strip(" ,")

    # alles na de eerste komma is bewerking
    prep = ""
    if "," in rest:
        rest, _, prep = rest.partition(",")
        prep = prep.strip()

    rest = rest.split("/")[0].strip() if re.search(r"[a-z]/[a-z]", rest) else rest

    # "2 inch cubes leche flan" -> de maat erbij, niet in de naam
    size_in_name = re.match(r"(?i)^(\d+(?:\.\d+)?)\s*-?\s*(inch|cm|mm)\s+(cubes?|pieces?|slices?|strips?|chunks?)\s+(.+)$", rest)
    if size_in_name:
        prep_extra = f"cut into {size_in_name.group(1)} {size_in_name.group(2)} {size_in_name.group(3)}"
        rest = size_in_name.group(4).strip()
        prep = f"{prep} {prep_extra}".strip() if prep else prep_extra

    # "freshly-ground black pepper": streepje maakt er één woord van
    rest = re.sub(r"(?i)\b(freshly|fresh|finely|roughly|thinly|coarsely|well|lightly|hand)-(?=[a-z])", r"\1 ", rest)

    # bewerkingswoorden vooraan verhuizen ook naar de bewerking
    words = rest.split(" ")
    moved = []
    while len(words) > 1 and words[0].lower().strip(".,") in PREP_WORDS:
        moved.append(words.pop(0).lower())
    if moved:
        prep = (" ".join(moved) + (" " + prep if prep else "")).strip()

    name = " ".join(words).strip(" ,.")
    name = re.sub(r"(?i)\s+(?:or|and)$", "", name).strip()
    if not name:
        return None

    if frying:
        prep = (prep + " " + frying).strip() if prep else frying
    if not measure_text and tail_measure:
        measure_text = tail_measure
    elif tail_measure and tail_measure not in ("To taste",):
        prep = (prep + " " + tail_measure.lower()).strip()

    return finish(measure_text, name, prep)


# ------------------------------------------------------------------ namen laten aansluiten

STRIP_FOR_MATCH = {"fresh", "freshly", "dried", "ground", "whole", "large", "small", "medium",
                   "raw", "cooked", "all-purpose", "allpurpose", "plain", "good", "quality",
                   "extra", "unsalted", "salted", "granulated", "white", "brown", "black",
                   "hot", "cold", "warm", "ripe", "boneless", "skinless", "canned", "tinned",
                   "frozen", "chopped", "sliced", "minced", "grated"}


def match_key(name):
    words = re.sub(r"[^a-z0-9 ]", " ", name.lower()).split()
    out = []
    for word in words:
        if word.endswith("ies") and len(word) > 4:
            word = word[:-3] + "y"
        elif word.endswith("oes") and len(word) > 4:
            word = word[:-2]
        elif word.endswith("es") and len(word) > 4 and word[-3] in "shxz":
            word = word[:-2]
        elif word.endswith("s") and not word.endswith("ss") and len(word) > 3:
            word = word[:-1]
        out.append(word)
    return " ".join(sorted(out))


def build_known_names(meals):
    known = {}
    for meal in meals:
        for i in range(1, 21):
            value = (meal.get(f"strIngredient{i}") or "").strip()
            if value:
                known.setdefault(match_key(value), value)
    return known


def align_name(name, known):
    """Gebruikt een bestaande ingrediëntnaam als het om hetzelfde ingrediënt gaat.

    Bij meerdere lezingen (gescheiden door |) wint de lezing die al in de
    database voorkomt.
    """
    options = [part for part in name.split("|") if part.strip()]
    for option in options:
        if match_key(title_case_name(clean_text(option))) in known:
            name = option
            break
    else:
        name = options[0] if options else name

    canonical = title_case_name(clean_text(name))
    key = match_key(canonical)
    if key in known:
        return known[key]

    words = canonical.split()
    # steeds een bijvoeglijk woord vooraan weghalen en opnieuw proberen
    for start in range(1, len(words)):
        if words[start - 1].lower() not in STRIP_FOR_MATCH:
            break
        shorter = " ".join(words[start:])
        shorter_key = match_key(shorter)
        if shorter_key in known:
            return known[shorter_key]

    known[key] = canonical
    return canonical


# ------------------------------------------------------------------ opbouw

def build_record(entry, meal_id, image_url, image_page, known_names):
    category, area, country = classify(entry)

    steps = []
    for step in entry["steps"]:
        step = strip_wiki(step)
        if not step or re.match(r"(?i)^(file|image):", step):
            continue
        # Een losse "Serve." hoort bij de stap ervoor, niet als eigen stap.
        if steps and len(step) < 20:
            steps[-1] = f"{steps[-1]} {step}"
        else:
            steps.append(step)
    instructions = normalize_instructions("\n".join(steps))

    record = {
        "idMeal": str(meal_id),
        "strMeal": entry["name"],
        "strMealAlternate": None,
        "strCategory": category,
        "strArea": area,
        "strCountry": country,
        "strInstructions": instructions,
        "strMealThumb": image_url,
        "strTags": None,
        "strYoutube": "",
    }

    slots = []
    for line in entry["ingredients"]:
        parsed = split_ingredient_line(line)
        if not parsed:
            continue
        measure_text, raw_name, prep = parsed
        name = align_name(raw_name, known_names)
        name, extra_prep = normalize_ingredient(name)
        measure, replacement = normalize_measure(measure_text, name)
        if replacement:
            name = replacement
        for note in (extra_prep, prep):
            if note:
                measure = f"{measure}, {note.lower()}" if measure else note.capitalize()
        if not name:
            continue
        if (name, measure) in slots:
            continue
        slots.append((name, measure))
        if len(slots) == 20:
            break

    for i in range(1, 21):
        record[f"strIngredient{i}"] = slots[i - 1][0] if i <= len(slots) else None
    for i in range(1, 21):
        record[f"strMeasure{i}"] = slots[i - 1][1] if i <= len(slots) else None

    record["strSource"] = "https://en.wikibooks.org/wiki/" + urllib.parse.quote(f"Cookbook:{entry['name']}".replace(" ", "_"))
    record["strImageSource"] = image_page or None
    record["strCreativeCommonsConfirmed"] = "Yes"
    record["dateModified"] = None
    return record


def quality_problems(record):
    """Redenen om een gerecht niet toe te voegen."""
    problems = []
    ingredients = [record[f"strIngredient{i}"] for i in range(1, 21) if record[f"strIngredient{i}"]]
    steps = [s for s in (record["strInstructions"] or "").split("\n") if s.strip()]

    if len(ingredients) < 3:
        problems.append("minder dan 3 ingrediënten")
    if len(steps) < 3:
        problems.append("minder dan 3 stappen")
    if any(len(step) < 15 for step in steps):
        problems.append("een te korte stap")
    if len(record["strMeal"]) > 70:
        problems.append("titel te lang")
    if not record["strMealThumb"]:
        problems.append("geen afbeelding")
    if any(len(name) > 45 for name in ingredients):
        problems.append("ingrediëntnaam te lang")
    if any(re.search(r"(?i)\b(see|refer to|as above|recipe below)\b", step) for step in steps):
        problems.append("verwijzing naar iets buiten het recept")
    if any(name.lower() in TOO_GENERIC for name in ingredients):
        problems.append("te vaag ingrediënt")
    if any(re.search(r"(?i)\bper (person|liter|litre|serving)\b", name) for name in ingredients):
        problems.append("hoeveelheid per persoon in de naam")
    if sum(1 for name in ingredients if re.search(r"(?i)(filling|of choice)$", name)) >= 2:
        problems.append("lijst met vullingen in plaats van ingrediënten")
    measures = [record[f"strMeasure{i}"] for i in range(1, 21) if record[f"strIngredient{i}"]]
    if len(ingredients) >= 5 and sum(1 for m in measures if not m) > len(ingredients) / 2:
        problems.append("meer dan de helft van de ingrediënten zonder hoeveelheid")
    return problems


def reclassify(meals, cache, dry_run):
    """Werkt strCategory, strArea en strCountry van de Wikibooks-gerechten bij.

    Handig na een aanpassing in classify(): de id\'s en de afbeeldingen blijven
    zoals ze zijn, alleen de indeling verandert.
    """
    if not cache or not cache.exists():
        print("hiervoor is de pagina-cache nodig (--cache met wb_pages.json)", file=sys.stderr)
        return 1
    pages = json.loads(cache.read_text(encoding="utf-8"))
    by_name = {}
    for title, page in pages.items():
        summary = re.search(r"(?i)\|\s*category\s*=\s*([^|}\n]+)", page["wikitext"])
        ing_block = section(page["wikitext"], ["ingredients"])
        by_name[title.replace("Cookbook:", "").strip()] = {
            "name": title.replace("Cookbook:", "").strip(),
            "categories": page["categories"],
            "summary_category": summary.group(1).strip() if summary else "",
            "ingredients": bullets(ing_block, "*"),
        }

    changed = 0
    for meal in meals:
        if int(meal["idMeal"]) < 90000:
            continue
        entry = by_name.get(meal["strMeal"])
        if not entry:
            print(f"  geen bronpagina voor {meal['strMeal']!r}", file=sys.stderr)
            continue
        category, area, country = classify(entry)
        if (category, area, country) != (meal["strCategory"], meal["strArea"], meal["strCountry"]):
            print(f"  {meal['strMeal'][:46]:<48} {meal['strCategory']} -> {category}")
            meal["strCategory"], meal["strArea"], meal["strCountry"] = category, area, country
            changed += 1

    print(f"aangepast: {changed}")
    if not dry_run:
        MEALS.write_text(json.dumps(meals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=300, help="hoeveel gerechten toevoegen")
    parser.add_argument("--cache", default="", help="map met eerder opgehaalde pagina's (wb_pages.json)")
    parser.add_argument("--dry-run", action="store_true", help="niets wegschrijven")
    parser.add_argument("--reclassify", action="store_true",
                        help="alleen categorie en keuken van de al geïmporteerde gerechten bijwerken")
    args = parser.parse_args()

    meals = json.loads(MEALS.read_text(encoding="utf-8"))
    existing_titles = {m["strMeal"].strip().lower() for m in meals}
    known_names = build_known_names(meals)
    print(f"bestaande gerechten: {len(meals)}, bekende ingrediëntnamen: {len(known_names)}")

    cache = Path(args.cache) / "wb_pages.json" if args.cache else None
    if cache and cache.exists():
        pages = json.loads(cache.read_text(encoding="utf-8"))
        print(f"pagina's uit cache: {len(pages)}")
    else:
        titles = all_recipe_titles()
        print(f"recepten in Category:Recipes: {len(titles)}")
        pages = fetch_pages(titles)
        if cache:
            cache.write_text(json.dumps(pages, ensure_ascii=False), encoding="utf-8")

    if args.reclassify:
        return reclassify(meals, Path(args.cache) / "wb_pages.json" if args.cache else None, args.dry_run)

    entries = []
    skipped = Counter()
    for title, page in pages.items():
        wikitext = page["wikitext"]
        if re.search(r"(?i)#redirect", wikitext[:200]):
            skipped["doorverwijzing"] += 1
            continue
        ing_block = section(wikitext, ["ingredients"])
        proc_block = section(wikitext, ["procedure", "procedures", "preparation", "method", "directions"])
        if not ing_block or not proc_block:
            skipped["geen ingrediënten of bereiding"] += 1
            continue
        ingredients = bullets(ing_block, "*")
        steps = bullets(proc_block, "#")
        if not steps:
            steps = [s for s in (strip_wiki(l) for l in proc_block.split("\n")) if len(s) > 40]
        image = image_name(wikitext)
        if len(ingredients) < 3 or len(steps) < 3 or not image:
            skipped["te weinig inhoud of geen afbeelding"] += 1
            continue
        name = title.replace("Cookbook:", "").strip()
        if name.lower() in existing_titles:
            skipped["titel bestaat al"] += 1
            continue
        summary_category = re.search(r"(?i)\|\s*category\s*=\s*([^|}\n]+)", wikitext)
        entries.append({
            "name": name,
            "image": image,
            "ingredients": ingredients,
            "steps": steps,
            "categories": page["categories"],
            "summary_category": summary_category.group(1).strip() if summary_category else "",
        })

    for reason, count in skipped.most_common():
        print(f"  overgeslagen: {count} ({reason})")
    print(f"kandidaten: {len(entries)}")

    scored = []
    for entry in entries:
        category, area, _ = classify(entry)
        scored.append((taste_score(entry, category, area), entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["name"]))

    # ruim boven de limiet ophalen, want de kwaliteitscontrole gooit er nog uit
    shortlist = [entry for _, entry in scored[: int(args.limit * 1.8) + 40]]
    images = fetch_image_urls([entry["image"] for entry in shortlist])
    print(f"afbeeldingen opgelost: {len(images)}/{len(shortlist)}")

    next_id = ID_START
    added, rejected = [], Counter()
    for entry in shortlist:
        if len(added) >= args.limit:
            break
        image = images.get(entry["image"])
        if not image:
            rejected["afbeelding niet gevonden"] += 1
            continue
        record = build_record(entry, next_id, image[0], image[1], known_names)
        problems = quality_problems(record)
        if problems:
            rejected[problems[0]] += 1
            continue
        added.append(record)
        next_id += 1

    for reason, count in rejected.most_common():
        print(f"  afgekeurd: {count} ({reason})")
    print(f"toegevoegd: {len(added)}")

    if args.dry_run:
        print(json.dumps(added[:2], ensure_ascii=False, indent=2)[:3000])
        return 0

    meals += added
    MEALS.write_text(json.dumps(meals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"weggeschreven: {len(meals)} gerechten in {MEALS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
