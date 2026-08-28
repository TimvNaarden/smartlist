#!/usr/bin/env python3
"""Zet de categorie en de keuken van alle gerechten in recipes.json goed.

De categorieën kwamen uit de bronnen en klopten niet altijd: een Thaise curry met
vissaus stond onder Seafood, een salade met rundvlees onder Vegetarian, en bij 189
gerechten was strArea leeg terwijl strCountry wel gevuld was.

Dit script leidt de categorie af uit de titel en de ingrediëntenlijst:

  1. het hoofdbestanddeel: Goat, Lamb, Beef, Pork, Chicken of Seafood
  2. anders een nagerecht of ontbijt, als de titel dat zegt
  3. anders Pasta, wanneer pasta of noedels het hoofdbestanddeel zijn
  4. anders Vegan of Vegetarian, afhankelijk van de dierlijke producten
  5. anders Side, Starter of Miscellaneous

Vissaus, oestersaus, garnalenpasta en bouillon tellen niet als hoofdbestanddeel;
dat zijn smaakmakers. Ze maken een gerecht wel niet-vegetarisch.

    python3 tools/classify_meals.py --dry-run   # alleen laten zien wat er verandert
    python3 tools/classify_meals.py             # doorvoeren
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

MEALS = Path(__file__).resolve().parent.parent / "src" / "API" / "recipes.json"

CATEGORIES = {"Beef", "Breakfast", "Chicken", "Dessert", "Goat", "Lamb", "Miscellaneous",
              "Pasta", "Pork", "Seafood", "Side", "Starter", "Vegan", "Vegetarian"}

# ---------------------------------------------------------------- bestanddelen

# Ingrediënten die het hoofdbestanddeel kunnen zijn, in de volgorde waarin ze
# voorrang krijgen als een gerecht er meerdere bevat.
PROTEIN = [
    ("Goat", ["goat", "mutton chunks"]),
    ("Lamb", ["lamb", "mutton", "doner meat", "doner", "kebab meat"]),
    ("Beef", ["beef", "steak", "veal", "oxtail", "brisket", "sirloin", "rump", "chuck",
              "minced beef", "corned beef", "snout", "beef heart", "tripe", "cow feet", "cow foot",
              "cow rib", "hind shank", "shin of beef", "ox cheek"]),
    ("Pork", ["pork", "bacon", "gammon", "ham", "sausage", "sausages", "chorizo", "pancetta",
              "prosciutto", "salami", "pepperoni", "spare ribs", "pig", "lardons", "black pudding",
              "jamon", "jamón", "serrano ham", "guanciale", "speck", "chipolata"]),
    ("Chicken", ["chicken", "turkey", "duck", "poussin", "quail", "guinea fowl", "chicken thighs",
                 "chicken breast", "chicken wings", "chicken legs", "pigeon", "goose", "pheasant",
                 "partridge"]),
    ("Seafood", ["fish", "salmon", "tuna", "cod", "haddock", "pollock", "trout", "mackerel",
                 "sardine", "sardines", "sea bass", "seabass", "barramundi", "monkfish", "halibut",
                 "snapper", "tilapia", "herring", "eel", "prawns", "prawn", "shrimp", "crab",
                 "lobster", "squid", "calamari", "octopus", "mussels", "clams", "clam", "oysters",
                 "scallops", "crayfish", "crawfish", "anchovy", "anchovies", "kipper", "whitebait",
                 "fish fillet", "smoked salmon", "smoked haddock", "conch", "conchs", "abalone",
                 "cuttlefish", "roe", "caviar", "surimi", "fishballs", "fish balls", "seafood",
                 "seafood mix", "shellfish", "codfish", "milkfish", "catfish", "swordfish",
                 "whitefish", "hake", "bream", "pilchard", "stockfish", "crab meat", "crabmeat",
                 "bangus", "tilefish", "pomfret", "kingfish", "bonito", "skate"],),
]

# Namen die op vlees of vis lijken maar het niet zijn.
NOT_MEAT = {
    "goat cheese", "goats cheese", "goat's cheese", "goats' cheese", "goat milk", "goat butter",
    "goat yoghurt", "beef tomato", "beef tomatoes", "prawn crackers", "chicken seasoning",
    "vegan chicken", "vegan beef", "mock duck", "duck fat", "fish shaped pasta",
}

# Plaatsvervangers voor vlees: die zeggen niet welk vlees, dus dan laten we de
# bestaande categorie staan.
GENERIC_MEAT = {"meat", "shredded meat", "minced meat", "your choice of meat", "meatballs",
                "meat balls", "cold cuts", "mixed meat", "offal"}

# Smaakmakers: die maken een gerecht niet tot vlees- of visgerecht.
FLAVOURING = {
    "fish sauce", "oyster sauce", "shrimp paste", "anchovy paste", "worcestershire sauce",
    "chicken stock", "chicken broth", "chicken stock cube", "chicken stock cubes", "beef stock",
    "beef broth", "beef stock cube", "beef stock cubes", "beef stock concentrate", "fish stock",
    "seafood stock", "shrimp stock", "lamb stock", "hot beef stock", "stock cube", "stock cubes",
    "bonito flakes", "dashi", "gelatin", "gelatine", "lard", "beef dripping", "duck fat",
    "chicken bouillon", "bouillon", "ground crayfish", "xo sauce", "aekjeot", "belacan",
    "chicken bouillon powder", "chicken seasoning cube", "beef seasoning cube",
}

# Dierlijke producten die een gerecht niet-vegan maken (naast vlees en vis).
DAIRY_AND_EGG = [
    "milk", "butter", "buttermilk", "cheese", "cream", "yoghurt", "yogurt", "ghee", "custard",
    "mozzarella", "parmesan", "cheddar", "feta", "ricotta", "mascarpone", "halloumi", "paneer",
    "gruyere", "gouda", "brie", "stilton", "pecorino", "emmental", "quark", "creme fraiche",
    "crème fraîche", "condensed milk", "evaporated milk", "ice cream", "egg", "eggs", "egg yolks",
    "egg white", "egg whites", "mayonnaise", "honey", "lactose", "whey", "curd", "kefir",
]

# Plantaardige vervangers: "almond milk", "vegan butter", "flax eggs" en
# "peanut butter" zijn geen zuivel of ei.
VEGAN_SUBSTITUTE = re.compile(
    r"(?i)\b(almond|soya|soy|oat|rice|coconut|cashew|hemp|hazelnut|walnut|macadamia|plant|"
    r"vegan|flax|chia|peanut|nut|cocoa|shea|apple|dairy-free|dairy free|non-dairy)\b"
    r".*\b(milk|butter|cream|creams|cheese|egg|eggs|yoghurt|yogurt)\b"
)

# ---------------------------------------------------------------- soort gerecht

DESSERT_WORDS = [
    "cake", "tart", "cookie", "biscuit", "brownie", "blondie", "pudding", "ice cream", "icecream",
    "sorbet", "mousse", "cheesecake", "fudge", "truffle", "custard", "crumble", "cobbler",
    "doughnut", "donut", "cupcake", "muffin", "meringue", "baklava", "halva", "flan", "parfait",
    "trifle", "candy", "toffee", "caramel", "sundae", "eclair", "éclair", "macaron", "macaroon",
    "tiramisu", "panna cotta", "churro", "shortbread", "gingerbread", "strudel", "compote",
    "mochi", "pavlova", "roulade", "marzipan", "praline", "brittle", "cannoli", "profiterole",
    "dessert", "sweet", "jam", "syrup cake", "halwa", "kheer", "laddu", "barfi", "gulab jamun",
    "jalebi", "rasgulla", "tres leches", "banoffee", "pie crust", "frosting", "icing", "ganache",
    "brulee", "brûlée", "clafoutis", "fritters in syrup", "sticky toffee", "millefeuille",
]

BREAKFAST_WORDS = ["breakfast", "porridge", "oatmeal", "granola", "muesli", "french toast",
                   "congee", "shakshuka", "hash browns", "overnight oats", "bircher"]

PASTA_WORDS = ["pasta", "spaghetti", "macaroni", "fettuccine", "fettucine", "lasagne", "lasagna",
               "tagliatelle", "linguine", "rigatoni", "fusilli", "farfalle", "cannelloni",
               "ravioli", "tortellini", "orzo", "penne", "noodle", "noodles", "udon", "ramen",
               "soba", "vermicelli", "gnocchi", "pappardelle", "conchiglie", "orecchiette"]

STARTER_WORDS = ["appetizer", "appetiser", "starter", "canape", "canapé", "dip", "hummus",
                 "bruschetta", "spring roll", "samosa", "croquette", "fritter", "tapas",
                 "antipasto", "meze", "mezze", "amuse"]

SIDE_WORDS = ["sauce", "dressing", "chutney", "relish", "pickle", "pickles", "condiment", "salsa",
              "bread", "rolls", "bun", "buns", "flatbread", "tortilla", "naan", "roti", "chapati",
              "biscuits", "cornbread", "salad", "slaw", "side", "mash", "fries", "chips",
              "roast potatoes", "stuffing", "gravy", "marinade", "paste", "seasoning", "spice mix",
              "oil", "butter", "jam", "preserve", "garnish", "rice", "polenta", "couscous",
              "kimchi", "pesto", "aioli", "hummus", "guacamole", "purée", "puree", "cocktail sauce"]

SOUP_WORDS = ["soup", "broth", "chowder", "bisque", "consomme", "consommé", "gazpacho", "ramen",
              "stew", "potage"]

# ---------------------------------------------------------------- keukens

# Van een land naar de naam die TheMealDB voor de keuken gebruikt.
COUNTRY_TO_AREA = {
    "Algeria": "Algerian", "Argentina": "Argentinian", "Armenia": "Armenian", "Aruba": "Aruban",
    "Australia": "Australian", "Austria": "Austrian", "Azerbaijan": "Azerbaijani",
    "Bangladesh": "Bangladeshi", "Barbados": "Barbadian", "Belgium": "Belgian", "Belize": "Belizean",
    "Bolivia": "Bolivian", "Bosnia and Herzegovina": "Bosnian", "Brazil": "Brazilian",
    "Bulgaria": "Bulgarian", "Cambodia": "Cambodian", "Cameroon": "Cameroonian", "Canada": "Canadian",
    "Chile": "Chilean", "China": "Chinese", "Colombia": "Colombian", "Costa Rica": "Costa Rican",
    "Croatia": "Croatian", "Cuba": "Cuban", "Czechia": "Czech", "Czech Republic": "Czech",
    "Denmark": "Danish", "Dominican Republic": "Dominican", "Ecuador": "Ecuadorian", "Egypt": "Egyptian",
    "El Salvador": "Salvadoran", "Estonia": "Estonian", "Ethiopia": "Ethiopian", "Finland": "Finnish",
    "France": "French", "Georgia": "Georgian", "Germany": "German", "Ghana": "Ghanaian",
    "Greece": "Greek", "Guatemala": "Guatemalan", "Haiti": "Haitian", "Hungary": "Hungarian",
    "Iceland": "Icelandic", "India": "Indian", "Indonesia": "Indonesian", "Iran": "Iranian",
    "Iraq": "Iraqi", "Ireland": "Irish", "Israel": "Israeli", "Italy": "Italian", "Jamaica": "Jamaican",
    "Japan": "Japanese", "Jordan": "Jordanian", "Kenya": "Kenyan", "Latvia": "Latvian",
    "Lebanon": "Lebanese", "Lithuania": "Lithuanian", "Malaysia": "Malaysian", "Mexico": "Mexican",
    "Morocco": "Moroccan", "Nepal": "Nepalese", "Netherlands": "Dutch", "New Zealand": "New Zealander",
    "Nicaragua": "Nicaraguan", "Nigeria": "Nigerian", "Norway": "Norwegian", "Pakistan": "Pakistani",
    "Palestine": "Palestinian", "Panama": "Panamanian", "Paraguay": "Paraguayan", "Peru": "Peruvian",
    "Philippines": "Filipino", "Poland": "Polish", "Portugal": "Portuguese", "Puerto Rico": "Puerto Rican",
    "Romania": "Romanian", "Russia": "Russian", "Saudi Arabia": "Saudi", "Senegal": "Senegalese",
    "Serbia": "Serbian", "Singapore": "Singaporean", "Slovakia": "Slovak", "Slovenia": "Slovenian",
    "South Africa": "South African", "South Korea": "Korean", "Korea": "Korean", "Spain": "Spanish",
    "Sri Lanka": "Sri Lankan", "Sweden": "Swedish", "Switzerland": "Swiss", "Syria": "Syrian",
    "Taiwan": "Taiwanese", "Tanzania": "Tanzanian", "Thailand": "Thai", "Trinidad and Tobago": "Trinidadian",
    "Tunisia": "Tunisian", "Turkey": "Turkish", "Uganda": "Ugandan", "Ukraine": "Ukrainian",
    "United Arab Emirates": "Emirati", "United Kingdom": "British", "United States": "American",
    "Uruguay": "Uruguayan", "Venezuela": "Venezuelan", "Vietnam": "Vietnamese", "Antigua and Barbuda": "Antiguan",
    "Bahamas": "Bahamian", "Bermuda": "Bermudian", "Cape Verde": "Cape Verdean", "Cyprus": "Cypriot",
    "Fiji": "Fijian", "Guyana": "Guyanese", "Honduras": "Honduran", "Ivory Coast": "Ivorian",
    "Laos": "Laotian", "Libya": "Libyan", "Madagascar": "Malagasy", "Mali": "Malian",
    "Malta": "Maltese", "Mauritius": "Mauritian", "Moldova": "Moldovan", "Mongolia": "Mongolian",
    "Mozambique": "Mozambican", "Myanmar": "Burmese", "Namibia": "Namibian", "Zambia": "Zambian",
    "Zimbabwe": "Zimbabwean", "Bhutan": "Bhutanese", "Brunei": "Bruneian", "Burkina Faso": "Burkinabe",
    "Congo": "Congolese", "Gambia": "Gambian", "Guinea": "Guinean", "Liberia": "Liberian",
    "Rwanda": "Rwandan", "Sierra Leone": "Sierra Leonean", "Somalia": "Somali", "Sudan": "Sudanese",
    "Togo": "Togolese", "Yemen": "Yemeni", "Albania": "Albanian", "Belarus": "Belarusian",
    "Greenland": "Greenlandic", "Kazakhstan": "Kazakh", "Luxembourg": "Luxembourgish",
    "North Macedonia": "Macedonian", "Uzbekistan": "Uzbek", "Caribbean": "Caribbean",
    "Dominica": "Dominican", "Cayman Islands": "Caymanian", "Afghanistan": "Afghan",
    "Botswana": "Motswana", "Andorra": "Andorran", "Angola": "Angolan",
}

AREA_TO_COUNTRY = {}
for country, area in COUNTRY_TO_AREA.items():
    AREA_TO_COUNTRY.setdefault(area, country)

# ---------------------------------------------------------------- hulpjes


def ingredients_of(meal):
    """Geeft [(naam_klein, maat_klein, plek)] van de gevulde plekken."""
    rows = []
    for i in range(1, 21):
        name = (meal.get(f"strIngredient{i}") or "").strip()
        if not name:
            continue
        rows.append((name.lower(), (meal.get(f"strMeasure{i}") or "").strip().lower(), i))
    return rows


def mentions(text, words):
    return any(re.search(rf"\b{re.escape(word)}s?\b", text) for word in words)


def categories_present(meal):
    """Welke vlees- of viscategorieën komen ergens in de ingrediënten voor?

    Ook een klein beetje telt hier mee: 10 g garnalen maakt een gerecht geen
    visgerecht, maar het is wel een reden om de categorie Seafood te laten staan.
    """
    present = set()
    for name, _, _ in ingredients_of(meal):
        if name in NOT_MEAT or name in FLAVOURING:
            continue
        for category, words in PROTEIN:
            if mentions(name, words):
                present.add(category)
    return present


def has_generic_meat(meal):
    """Staat er "meat" of "your choice of meat" in, zonder te zeggen welk?"""
    return any(name in GENERIC_MEAT for name, _, _ in ingredients_of(meal))


def ingredient_list_is_full(meal):
    """Alle 20 plekken gevuld betekent dat de lijst mogelijk is afgekapt."""
    return all((meal.get(f"strIngredient{i}") or "").strip() for i in range(1, 21))


def is_substantial(measure, position):
    """Is dit een hoofdbestanddeel of maar een klein beetje?

    Een gewicht, een aantal stuks of een plek bovenaan de lijst wijst op het
    eerste; theelopen en snufjes op het tweede.
    """
    if re.search(r"\b(tsp|tbsp|pinch|dash|splash|drizzle|to taste|to garnish|to serve)\b", measure):
        return False
    if re.search(r"\b(\d+(?:\.\d+)?)\s*(g|kg|lb|oz|ml|l)\b", measure):
        grams = re.match(r"^(\d+(?:\.\d+)?)\s*(g|ml)\b", measure)
        if grams and float(grams.group(1)) < 60:
            return False
        return True
    if re.match(r"^\d", measure):
        return True
    # zonder maat: alleen bovenaan de lijst als hoofdbestanddeel zien
    return position <= 4


def find_protein(meal):
    """Geeft (beste_categorie, alle_gevonden_categorieën).

    "beste" is wat de titel noemt, en anders het bestanddeel dat het hoogst in de
    ingrediëntenlijst staat.
    """
    title = meal["strMeal"].lower()
    rows = ingredients_of(meal)

    found = {}
    for category, words in PROTEIN:
        for name, measure, position in rows:
            if name in FLAVOURING or name in NOT_MEAT or not mentions(name, words):
                continue
            if not is_substantial(measure, position):
                continue
            found.setdefault(category, position)

    # Wat in de titel staat, is waar het gerecht om gaat.
    for category, words in PROTEIN:
        if mentions(title, words):
            return category, set(found) | {category}

    if not found:
        return None, set()
    best = min(found.items(), key=lambda pair: pair[1])
    return best[0], set(found)


def has_animal_flavouring(meal):
    """Staat er bouillon, vissaus of gedroogde garnaal in? Dan is het niet vegan."""
    return any(name in FLAVOURING and name not in {"gelatin", "gelatine"}
               for name, _, _ in ingredients_of(meal))


def has_animal_product(meal):
    """Geeft (vlees_of_vis, zuivel_of_ei)."""
    rows = ingredients_of(meal)
    meat = False
    dairy = False
    for name, _, _ in rows:
        if name in FLAVOURING:
            # Bouillonblokjes en vissaus maken een gerecht strikt genomen niet
            # vegetarisch, maar ze zijn geen bestanddeel. Ze zijn hier geen reden
            # om het label Vegetarian weg te halen; iedereen ruilt ze in voor de
            # plantaardige variant.
            continue
        if name in NOT_MEAT:
            if ("cheese" in name or "milk" in name) and not VEGAN_SUBSTITUTE.search(name):
                dairy = True
            continue
        if name in GENERIC_MEAT:
            meat = True
            continue
        for _, words in PROTEIN:
            if mentions(name, words):
                meat = True
                break
        if mentions(name, DAIRY_AND_EGG) and not VEGAN_SUBSTITUTE.search(name):
            dairy = True
    return meat, dairy


def classify(meal):
    """Geeft (categorie, zekerheid)."""
    title = meal["strMeal"].lower()
    ingredient_text = " ".join(name for name, _, _ in ingredients_of(meal))

    protein, _ = find_protein(meal)
    certainty = "hoog"
    sweet = mentions(title, DESSERT_WORDS)
    savoury_pie = re.search(r"\b(pie|tart|pasty|pastie|roll|parcel)\b", title) and not sweet

    # Een nagerecht met vlees bestaat niet; een hartige pie met vlees wel.
    if sweet and not savoury_pie:
        sweet_ingredients = mentions(ingredient_text, ["sugar", "chocolate", "honey", "syrup",
                                                       "caster sugar", "icing sugar", "condensed milk",
                                                       "jam", "vanilla", "cream", "brown sugar"])
        if not protein or sweet_ingredients:
            return "Dessert", "hoog"

    if protein:
        return protein, certainty

    if mentions(title, BREAKFAST_WORDS):
        return "Breakfast", "hoog"
    if re.search(r"\b(pancake|waffle|crepe|crêpe|omelette|omelet|scrambled eggs|frittata)\b", title):
        sweet_ingredients = mentions(ingredient_text, ["sugar", "chocolate", "honey", "syrup", "banana"])
        return ("Dessert", "midden") if sweet_ingredients else ("Breakfast", "midden")

    if mentions(title, PASTA_WORDS) or mentions(ingredient_text, PASTA_WORDS[:20]):
        if mentions(title, PASTA_WORDS):
            return "Pasta", "hoog"

    meat, dairy = has_animal_product(meal)
    if not meat and not dairy:
        return "Vegan", "hoog"
    if not meat:
        # zonder vlees of vis, maar met zuivel of ei
        if mentions(title, SIDE_WORDS) or mentions(title, STARTER_WORDS):
            return ("Starter" if mentions(title, STARTER_WORDS) else "Side"), "midden"
        return "Vegetarian", "midden"

    if mentions(title, STARTER_WORDS):
        return "Starter", "midden"
    if mentions(title, SOUP_WORDS):
        return "Miscellaneous", "midden"
    if mentions(title, SIDE_WORDS):
        return "Side", "midden"
    return "Miscellaneous", "laag"


PROTEIN_CATEGORIES = {category for category, _ in PROTEIN}
DIET_CATEGORIES = {"Vegan", "Vegetarian"}


def repair(meal):
    """Geeft (nieuwe_categorie, reden), of (None, None) als er niets fout is.

    De categorieën van TheMealDB mengen gangen (Dessert, Side, Starter), hoofd-
    bestanddelen (Beef, Chicken) en dieet (Vegan, Vegetarian). Of een cake onder
    Dessert of onder Vegetarian hoort is een keuze, geen fout. Daarom veranderen we
    alleen wat de ingrediënten tegenspreken.
    """
    current = meal["strCategory"]
    title = meal["strMeal"].lower()

    # Bij een onvolledige of afgekapte ingrediëntenlijst weet de bron het beter.
    if has_generic_meat(meal) or ingredient_list_is_full(meal):
        return None, None

    present = categories_present(meal)
    protein, _ = find_protein(meal)
    meat, dairy = has_animal_product(meal)

    # 1) een vegetarisch of vegan gerecht met vlees of vis erin
    if current in DIET_CATEGORIES and meat:
        keuze = protein or (sorted(present)[0] if present else None)
        if keuze:
            return keuze, "vlees of vis in een vegetarisch gerecht"

    # 2) vegan met zuivel of ei
    if current == "Vegan" and dairy:
        return "Vegetarian", "zuivel of ei in een vegan gerecht"

    # 3) de categorie noemt een bestanddeel dat er helemaal niet in zit
    if current in PROTEIN_CATEGORIES and current not in present:
        if protein:
            return protein, "ander hoofdbestanddeel dan de categorie zegt"
        if present:
            return sorted(present)[0], "ander hoofdbestanddeel dan de categorie zegt"
        if mentions(title, STARTER_WORDS):
            return "Starter", "geen vlees of vis, en de titel wijst op een voorgerecht"
        if mentions(title, SIDE_WORDS):
            return "Side", "geen vlees of vis, en de titel wijst op een bijgerecht"
        if mentions(title, SOUP_WORDS):
            return "Miscellaneous", "geen vlees of vis, en het is een soep of stoofpot"
        if has_animal_flavouring(meal):
            # Geen hoofdbestanddeel, maar met vissaus of bouillon is het geen
            # vegetarisch gerecht om zo te noemen.
            return "Miscellaneous", "alleen een dierlijke smaakmaker, geen hoofdbestanddeel"
        return ("Vegetarian" if dairy else "Vegan"), "geen vlees of vis in het gerecht"

    return None, None


def fix_area(meal):
    """Vult strArea aan uit strCountry en omgekeerd."""
    area = (meal.get("strArea") or "").strip() or None
    country = (meal.get("strCountry") or "").strip() or None

    if not area and country:
        area = COUNTRY_TO_AREA.get(country)
    if not country and area:
        country = AREA_TO_COUNTRY.get(area)
    # strArea is de vorm die de filters gebruiken; die moet bij het land passen
    if area and country and COUNTRY_TO_AREA.get(country) and COUNTRY_TO_AREA[country] != area:
        area = COUNTRY_TO_AREA[country]
    return area, country


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="niets wegschrijven")
    parser.add_argument("--show", default="", help="alleen deze overgang laten zien, bv. 'Vegetarian->Beef'")
    parser.add_argument("--full", action="store_true",
                        help="alle categorieën opnieuw bepalen in plaats van alleen de foute repareren")
    args = parser.parse_args()

    meals = json.loads(MEALS.read_text(encoding="utf-8"))
    transitions = Counter()
    examples = {}
    area_fixed = 0

    reasons = Counter()
    for meal in meals:
        if args.full:
            category, _ = classify(meal)
            reason = "opnieuw bepaald"
        else:
            category, reason = repair(meal)

        if category and category not in CATEGORIES:
            print(f"  onbekende categorie {category!r} voor {meal['strMeal']}", file=sys.stderr)
            category = None

        if category and category != meal["strCategory"]:
            key = f"{meal['strCategory']} -> {category}"
            transitions[key] += 1
            reasons[reason] += 1
            examples.setdefault(key, []).append(meal["strMeal"])
            meal["strCategory"] = category

        area, country = fix_area(meal)
        if (area, country) != (meal.get("strArea"), meal.get("strCountry")):
            area_fixed += 1
            meal["strArea"], meal["strCountry"] = area, country

    total = sum(transitions.values())
    print(f"{len(meals)} gerechten, categorie aangepast bij {total}, keuken aangevuld bij {area_fixed}\n")
    for reason, count in reasons.most_common():
        print(f"  {count:>4}x {reason}")
    print()
    for key, count in transitions.most_common():
        print(f"  {count:>4}x {key}")
        if args.show and args.show.lower() in key.lower():
            for name in examples[key]:
                print(f"           {name}")

    if not args.dry_run:
        MEALS.write_text(json.dumps(meals, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nweggeschreven naar {MEALS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
