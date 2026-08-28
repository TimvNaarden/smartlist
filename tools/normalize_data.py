#!/usr/bin/env python3
"""Maakt de maten, ingrediëntnamen en bereidingswijzen in de databases gelijk.

De bronnen (TheMealDB, TheCocktailDB, Wikibooks) schrijven dezelfde dingen op
tientallen manieren: "1 tbsp", "1 tablespoon", "1 tbs" en "1 tblsp", of "100g"
naast "100 g" en "100 Grams". Op de boodschappenlijst worden ingrediënten samen-
gevoegd op naam, dus elke variant levert een extra regel op. Dit script schrijft
alles in één vorm:

    <hoeveelheid> <eenheid>[, bewerking]     bijvoorbeeld  "1 1/2 tbsp, minced"
    <omschrijving>                           bijvoorbeeld  "To taste", "Pinch"

en ingrediëntnamen in Title Case, met één naam per ingrediënt.

    python3 tools/normalize_data.py            # past de json-bestanden aan
    python3 tools/normalize_data.py --check    # rapporteert alleen, wijzigt niets
    python3 tools/normalize_data.py --report   # laat alle unieke maten zien

Het script is bedoeld om herhaald te draaien: het resultaat van een tweede run is
gelijk aan dat van de eerste (idempotent).
"""

import argparse
import html
import json
import re
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src" / "API"
MEALS = SRC / "recipes.json"
DRINKS = SRC / "cocktails.json"

# ---------------------------------------------------------------- hoeveelheden

UNICODE_FRACTIONS = {
    "¼": "1/4",
    "½": "1/2",
    "¾": "3/4",
    "⅓": "1/3",
    "⅔": "2/3",
    "⅛": "1/8",
    "⅜": "3/8",
    "⅝": "5/8",
    "⅞": "7/8",
    "⅕": "1/5",
    "⅖": "2/5",
}

# Decimalen die we als breuk schrijven, zodat "0.5" en "½" hetzelfde worden.
DECIMAL_AS_FRACTION = {
    Fraction(1, 8): "1/8",
    Fraction(1, 4): "1/4",
    Fraction(1, 3): "1/3",
    Fraction(3, 8): "3/8",
    Fraction(1, 2): "1/2",
    Fraction(5, 8): "5/8",
    Fraction(2, 3): "2/3",
    Fraction(3, 4): "3/4",
    Fraction(7, 8): "7/8",
}

# ---------------------------------------------------------------- eenheden

# alias -> canonieke eenheid. Eenheden die niet meervoud krijgen staan in SINGULAR_ONLY.
UNIT_ALIASES = {
    # gewicht
    "g": "g", "gr": "g", "gm": "g", "gram": "g", "grams": "g", "gramme": "g", "grammes": "g",
    "kg": "kg", "kilo": "kg", "kilos": "kg", "kilogram": "kg", "kilograms": "kg",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    # volume
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml",
    "l": "l", "litre": "l", "litres": "l", "liter": "l", "liters": "l",
    "cl": "cl", "dl": "dl",
    "tsp": "tsp", "tsps": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
    "tbsp": "tbsp", "tbsps": "tbsp", "tbs": "tbsp", "tbls": "tbsp", "tblsp": "tbsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp",
    "cup": "cup", "cups": "cup",
    "pint": "pint", "pints": "pint",
    "quart": "quart", "quarts": "quart", "qt": "quart",
    "shot": "shot", "shots": "shot",
    "jigger": "jigger", "jiggers": "jigger",
    "part": "part", "parts": "part",
    "dash": "dash", "dashes": "dash",
    "drop": "drop", "drops": "drop",
    "splash": "splash", "splashes": "splash",
    "measure": "measure", "measures": "measure",
    # stuks en verpakkingen
    "clove": "clove", "cloves": "clove",
    "sprig": "sprig", "sprigs": "sprig",
    "slice": "slice", "slices": "slice",
    "stick": "stick", "sticks": "stick",
    "stalk": "stalk", "stalks": "stalk",
    "leaf": "leaf", "leaves": "leaf",
    "floret": "floret", "florets": "floret",
    "piece": "piece", "pieces": "piece",
    "head": "head", "heads": "head",
    "bulb": "bulb", "bulbs": "bulb",
    "pod": "pod", "pods": "pod",
    "fillet": "fillet", "fillets": "fillet",
    "yolk": "yolk", "yolks": "yolk", "yolkes": "yolk",
    "wedge": "wedge", "wedges": "wedge",
    "rasher": "rasher", "rashers": "rasher",
    "shank": "shank", "shanks": "shank",
    "strip": "strip", "strips": "strip",
    "can": "can", "cans": "can", "tin": "can", "tins": "can",
    "jar": "jar", "jars": "jar",
    "tub": "tub", "tubs": "tub",
    "pack": "pack", "packs": "pack", "packet": "pack", "packets": "pack", "package": "pack",
    "bag": "bag", "bags": "bag",
    "bottle": "bottle", "bottles": "bottle",
    "pot": "pot", "pots": "pot",
    "scoop": "scoop", "scoops": "scoop",
    "bunch": "bunch", "bunches": "bunch",
    "handful": "handful", "handfuls": "handful", "handfull": "handful", "handfulls": "handful",
    "pinch": "pinch", "pinches": "pinch",
    "knob": "knob", "knobs": "knob",
    "tail": "tail", "tails": "tail",
    "cm": "cm", "mm": "mm",
    "twist": "twist", "twists": "twist",
    "gal": "gallon", "gallon": "gallon", "gallons": "gallon",
    "fifth": "bottle (750 ml)", "fifths": "bottle (750 ml)",
    "cube": "cube", "cubes": "cube",
    "portion": "portion", "portions": "portion",
    "cake": "cake", "cakes": "cake", "block": "block", "blocks": "block",
    "glass": "glass", "glasses": "glass",
}

# Bij deze eenheden schrijven we 2.5 en niet 2 1/2; niemand schrijft "2 1/2 cm".
DECIMAL_UNITS = {"g", "kg", "ml", "l", "cl", "dl", "cm", "mm"}

# Deze eenheden blijven altijd in het enkelvoud staan.
SINGULAR_ONLY = {"g", "kg", "ml", "l", "cl", "dl", "oz", "lb", "tsp", "tbsp", "cm", "mm"}

# Maatwoorden die meervoud krijgen als de hoeveelheid groter is dan één.
IRREGULAR_PLURAL = {"leaf": "leaves", "pinch": "pinches", "dash": "dashes", "splash": "splashes",
                    "inch": "inches", "bunch": "bunches", "wedge": "wedges"}

# Woorden die geen eenheid zijn maar een grootte aanduiden; die houden hun plek
# direct achter de hoeveelheid ("1 large", "2 medium").
SIZE_WORDS = {"large", "medium", "small", "whole", "thin", "thick", "extra", "jumbo", "baby", "big"}

# Woorden die tussen de hoeveelheid en de eenheid mogen staan ("5 chopped cloves").
# Staat er iets anders tussen, dan is het geen eenheid maar gewoon tekst.
PRE_UNIT_WORDS = SIZE_WORDS | {
    "fresh", "dried", "chopped", "sliced", "minced", "crushed", "grated", "peeled",
    "ground", "cooked", "boiled", "roasted", "mixed", "ripe", "smoked", "frozen",
    "finely", "roughly", "thinly", "coarsely",
}

# ---------------------------------------------------------------- omschrijvingen

# Maten zonder hoeveelheid. Sleutel is de kleine-letterversie zonder punctuatie.
DESCRIPTIVE = {
    "to taste": "To taste",
    "taste": "To taste",
    "grated to taste": "To taste, grated",
    "to serve": "To serve",
    "serve": "To serve",
    "to garnish": "To garnish",
    "garnish": "To garnish",
    "garnish with": "To garnish",
    "garnish chopped": "To garnish, chopped",
    "to glaze": "To glaze",
    "to decorate": "To decorate",
    "for frying": "For frying",
    "fry": "For frying",
    "for cooking": "For frying",
    "drizzle for cooking": "For frying",
    "for deep frying": "For frying",
    "for greasing": "For greasing",
    "for brushing": "For brushing",
    "for dusting": "For dusting",
    "dusting": "For dusting",
    "for topping": "For topping",
    "topping": "For topping",
    "top": "For topping",
    "sprinkling": "For sprinkling",
    "sprinking": "For sprinkling",
    "spinkling": "For sprinkling",
    "as required": "As required",
    "as needed": "As required",
    "optional": "Optional",
    # bewerkingen zonder hoeveelheid
    "chopped": "Chopped",
    "sliced": "Sliced",
    "grated": "Grated",
    "grating": "Grated",
    "shaved": "Shaved",
    "beaten": "Beaten",
    "boiled": "Boiled",
    "steamed": "Steamed",
    "crushed": "Crushed",
    "minced": "Minced",
    "melted": "Melted",
    "ground": "Ground",
    "halved": "Halved",
    "peeled and sliced": "Peeled and sliced",
    "sliced and seeded": "Sliced and seeded",
    # sap en zeste
    "juice of half": "Juice of 1/2",
    "zest and juice of 1": "Zest and juice of 1",
    "zest and juice of 2": "Zest and juice of 2",
    "zest and juice of one": "Zest and juice of 1",
    "the juice and zest of one": "Zest and juice of 1",
    "juice zest of one": "Zest and juice of 1",
    "grated zest of 1": "Zest of 1",
    "grated zest of 2": "Zest of 2",
    # losse maatwoorden
    "pinch": "Pinch",
    "dash": "Dash",
    "splash": "Splash",
    "drizzle": "Drizzle",
    "handful": "Handful",
    "handfull": "Handful",
    "large handful": "Large handful",
    "small bunch": "Small bunch",
    "bunch": "Bunch",
    "knob": "Knob",
    "leaves": "Leaves",
    "sprigs of fresh": "Sprigs",
    "small pack": "Small pack",
    "can": "1 can",
    "bottle": "1 bottle",
    "pod of": "1 pod",
    "half": "1/2",
    "3rd": "1/3",
    "twist of": "Twist",
    "fill with": "Fill with",
    "top up with": "Top up with",
    "top with": "Top up with",
    "chilled": "Chilled",
    "cubes": "Cubes",
    "frozen": "Frozen",
    "bacardi": "",
}

# Maten die zo eigenaardig zijn dat een regel geen zin heeft. Waarde is de
# gewenste maat, of een tuple (maat, extra ingrediëntnaam) waar de naam ook
# aangepast moet worden.
MEASURE_OVERRIDES = {
    "1 - 14-ounce can": "1 can",
    "1 (12 oz.)": "1 pack (340 g)",
    "1 (400g) tin": "1 can (400 g)",
    "1 (200g) pack": "1 pack (200 g)",
    "14 oz jar": "1 jar (400 g)",
    "400g can": "1 can (400 g)",
    "400ml can": "1 can (400 ml)",
    "2 x 400g tins": "2 cans (400 g)",
    "2 x 400g": "2 x 400 g",
    "3 400g cans": "3 cans (400 g)",
    "2 400g cans": "2 cans (400 g)",
    "1 x 300ml": "300 ml",
    "100ml milk": "100 ml",
    "175ml boiling": "175 ml, boiling",
    "1 litre hot": "1 l, hot",
    "1/2 cup boiling": "1/2 cup, boiling",
    "230ml frying": "230 ml, for frying",
    "2 quarts neutral frying": "2 quarts, for frying",
    "1.5 tablespoons minced garlic": "1 1/2 tbsp, minced",
    "2 juice of 1, the other halved": "2, juice of 1 and the other halved",
    "2 juice": "Juice of 2",
    "1 inch": "2.5 cm piece",
    "3 x 7.5cm": "3 pieces (7.5 cm)",
    "thumb sized peeled and very finely grated": "1 thumb-sized piece, peeled and finely grated",
    "1/2 tsp dissolved in 1/2 cup warm milk": "1/2 tsp, dissolved in 125 ml warm milk",
    "white": "To serve",
    "1 trimmed and roughly chopped; reserve any fronds to garnish": "1, trimmed and roughly chopped",
    "1 red deseeded and finely sliced, to serve": "1, deseeded and finely sliced",
    "1 tbsp palm or soft light": "1 tbsp",
    "1 and 1/8 cup": "1 1/8 cup",
    "2-1/2 cups": "2 1/2 cups",
    "1-1/2 cups": "1 1/2 cups",
    "1-2/3 cups": "1 2/3 cups",
    "1-1/3 cups": "1 1/3 cups",
    "450 grams boneless skin": "450 g, boneless and skinless",
    "16 skinnless": "16, skinless",
    "1 seperated": "1, separated",
    "1 cut thin wedges": "1, cut into thin wedges",
    "6 cut thick slices": "6, cut into thick slices",
    "5 thin cut": "5, thinly cut",
    "2 marble sized": "2 marble-sized pieces",
    "1 x 400g tin": "1 can (400 g)",
    # eigenaardigheden uit TheCocktailDB
    "a little bit of": "To taste",
    "by taste": "To taste",
    "(if needed)": "As required",
    "add": "",
    "add splash": "Splash",
    ", orange": "",
    "fill": "Fill with",
    "fill to top": "Fill with",
    "fill to top with": "Fill with",
    "full glass": "1 glass",
    "float bacardi": "",
    "around rim put 1 pinch": "Pinch, around the rim",
    "(claret)": "",
    "(seltzer water)": "",
    "8-ounce sliced": "225 g, sliced",
    "1 chopped into 1/2-inch pieces": "1, chopped into 1/2-inch pieces",
    "1 medium chopped into 1/2-inch pieces": "1 medium, chopped into 1/2-inch pieces",
    "1 bulb chopped into 1/2-inch pieces": "1 bulb, chopped into 1/2-inch pieces",
}

# Maten waarin de eenheid en de ingrediëntnaam door elkaar liepen; hier hoort
# ook de naam aangepast te worden.
NAME_FROM_MEASURE = {
    ("1 yolk", "Egg"): ("1", "Egg Yolks"),
    ("3 yolkes", "Egg"): ("3", "Egg Yolks"),
    ("1 red", "Pepper"): ("1", "Red Pepper"),
    ("2 free-range", "Egg Yolks"): ("2", "Egg Yolks"),
    # "Cubes Ice" op een boodschappenlijst is onzin; Ice zegt genoeg.
    ("cubes", "Ice"): ("", "Ice"),
    ("crushed", "Ice"): ("", "Crushed Ice"),
    ("to serve", "Rice"): ("To serve", "White Rice"),
}

# Woorden die in de maat stonden maar het product aanduiden. Die verhuizen naar
# de naam: "1 tsp superfine" bij Sugar wordt "1 tsp" bij "Superfine Sugar".
PREP_AS_NAME_PREFIX = {
    "superfine": "Superfine",
    "white": "White",
    "frozen": "Frozen",
    "green ginger": "Green Ginger",
    "bacardi": "Bacardi",
    "light": "Light",
    "dark": "Dark",
    "black": "Black",
    "coarse": "Coarse",
    "fresh": "Fresh",
    "dry": "Dry",
    "sweet": "Sweet",
}

# Alleen bij deze ingrediënten is "crushed" een productnaam en geen bewerking.
CRUSHED_AS_NAME = {"Ice"}

# ---------------------------------------------------------------- ingrediënten

# Woorden die binnen een naam klein blijven.
LOWER_WORDS = {"of", "and", "or", "the", "in", "with", "for", "a", "to", "on", "de", "en"}

# Namen die precies zo blijven staan (merknamen, afkortingen, streepjes).
NAME_EXACT = {
    "msg": "MSG",
    "iqf prawns": "IQF Prawns",
    "extra virgin olive oil": "Extra Virgin Olive Oil",
    "self-raising flour": "Self-raising Flour",
    "free-range egg": "Free-range Egg",
    "free-range eggs": "Free-range Egg",
    "stir-fry vegetables": "Stir-fry Vegetables",
    "creme fraiche": "Crème Fraîche",
    "crème fraîche": "Crème Fraîche",
}

# Namen die eigenlijk hetzelfde ingrediënt zijn. Waarde is de canonieke naam, of
# een tuple (naam, bewerking) wanneer er een bewerking in de naam stond die naar
# de maat verhuist.
NAME_ALIASES = {
    # spelfouten
    "tinned tomatos": "Tinned Tomatoes",
    "corn arepa filled with mozarella cheese": "Corn Arepa Filled With Mozzarella Cheese",
    "sundried tomatoes": "Sun-dried Tomatoes",
    # enkelvoud/meervoud van hetzelfde ingrediënt (de vaakst gebruikte vorm wint)
    "eggs": "Egg",
    "tomatoes": "Tomato",
    "lemons": "Lemon",
    "onions": "Onion",
    "bay leaves": "Bay Leaf",
    "chicken breasts": "Chicken Breast",
    "clove": "Cloves",
    "buns": "Bun",
    "carrot": "Carrots",
    "dark soft brown sugar": "Dark Brown Soft Sugar",
    "rice stick noodles": "Rice Stick Noodles",
    "mozzarella balls": "Mozzarella Balls",
    "chestnut mushroom": "Chestnut Mushrooms",
    # bewerking hoort in de maat, niet in de naam
    "chopped onion": ("Onion", "chopped"),
    "chopped parsley": ("Parsley", "chopped"),
    "freshly chopped parsley": ("Parsley", "finely chopped"),
    "minced garlic": ("Garlic", "minced"),
    "free-range egg, beaten": ("Free-range Egg", "beaten"),
    "free-range eggs, beaten": ("Free-range Egg", "beaten"),
}


# Verschillende namen voor hetzelfde ingrediënt. Deels Amerikaans naast Brits
# (cilantro/coriander, scallions/spring onions), deels varianten die al in de
# oorspronkelijke data naast elkaar stonden. De Britse vorm wint, want die is in
# TheMealDB de meest gebruikte.
SYNONYMS = {
    # kruiden en groenten
    "cilantro": "Coriander",
    "cilantro leaves": "Coriander",
    "coriander leaves": "Coriander",
    "fresh coriander": "Coriander",
    "fresh cilantro": "Coriander",
    "scallions": "Spring Onions",
    "scallion": "Spring Onions",
    "green onions": "Spring Onions",
    "green onion": "Spring Onions",
    "spring onion": "Spring Onions",
    "eggplant": "Aubergine",
    "eggplants": "Aubergine",
    "aubergines": "Aubergine",
    "zucchini": "Courgettes",
    "zucchinis": "Courgettes",
    "courgette": "Courgettes",
    "garbanzo beans": "Chickpeas",
    "garbanzos": "Chickpeas",
    "chickpea": "Chickpeas",
    "yellow onion": "Onion",
    "yellow onions": "Onion",
    "white onion": "Onion",
    "brown onion": "Onion",
    "medium-sized yellow onion": "Onion",
    "fresh mint": "Mint",
    "fresh mint leaves": "Mint",
    "mint leaves": "Mint",
    "dill weed": "Dill",
    "fresh dill": "Dill",
    "tarragon leaves": "Tarragon",
    "flat-leaf parsley": "Parsley",
    "fresh parsley": "Parsley",
    "parsley leaves": "Parsley",
    "fresh basil": "Basil",
    "basil leaves": "Basil",
    "fresh thyme": "Thyme",
    "thyme leaves": "Thyme",
    "overripe plantain": "Plantain",
    "plantains": "Plantain",
    "firm tofu": "Tofu",
    "bean sprouts": "Beansprouts",
    "beansprout": "Beansprouts",
    # peper en chili
    "chili powder": "Chilli Powder",
    "chile powder": "Chilli Powder",
    "red chile powder": "Red Chilli Powder",
    "chili flakes": "Chilli Flakes",
    "red chili flakes": "Chilli Flakes",
    "red pepper flakes": "Chilli Flakes",
    "crushed red pepper": "Chilli Flakes",
    "chile pepper": "Chilli",
    "chile peppers": "Chilli",
    "chili pepper": "Chilli",
    "chilies": "Chilli",
    "chiles": "Chilli",
    "chillies": "Chilli",
    "dried chile pepper": "Dried Chillies",
    "dried chillies": "Dried Chillies",
    "dried chilies": "Dried Chillies",
    "red bell pepper": "Red Pepper",
    "red bell peppers": "Red Pepper",
    "green bell pepper": "Green Pepper",
    "green bell peppers": "Green Pepper",
    "sweet red peppers": "Red Pepper",
    "freshly-ground black pepper": "Black Pepper",
    "fresh-ground black pepper": "Black Pepper",
    "fresh ground black pepper": "Black Pepper",
    "cake tofu": "Tofu",
    "pieces of seaweed": "Seaweed",
    "freshly ground black pepper": "Black Pepper",
    "ground black pepper": "Black Pepper",
    "sweet paprika": "Paprika",
    # meel, zetmeel en zoet
    "all purpose flour": "Plain Flour",
    "all-purpose flour": "Plain Flour",
    "white flour": "Plain Flour",
    "wheat flour": "Plain Flour",
    "besan": "Gram Flour",
    "chickpea flour": "Gram Flour",
    "semolina flour": "Semolina",
    "fine semolina": "Semolina",
    "corn starch": "Cornstarch",
    "corn-starch": "Cornstarch",
    "powdered sugar": "Icing Sugar",
    "confectioners sugar": "Icing Sugar",
    "confectioner's sugar": "Icing Sugar",
    "superfine sugar": "Caster Sugar",
    "golden superfine sugar": "Caster Sugar",
    "packed brown sugar": "Brown Sugar",
    "packed light brown sugar": "Light Brown Sugar",
    "light brown soft sugar": "Light Brown Sugar",
    "white granulated sugar": "Granulated Sugar",
    "white sugar": "Sugar",
    "sugar to taste": "Sugar",
    "baking soda": "Bicarbonate of Soda",
    "unsweetened cocoa": "Cocoa Powder",
    "unsweetened cocoa powder": "Cocoa Powder",
    "cocoa": "Cocoa Powder",
    "vanilla essence": "Vanilla Extract",
    "dry active yeast": "Yeast",
    "active dry yeast": "Yeast",
    "dried yeast": "Yeast",
    "bread crumbs": "Breadcrumbs",
    "breadcrumb": "Breadcrumbs",
    # zuivel en eieren
    "heavy cream": "Double Cream",
    "heavy whipping cream": "Whipping Cream",
    "full-fat milk": "Milk",
    "whole milk": "Milk",
    "lukewarm water": "Water",
    "warm water": "Water",
    "cold water": "Water",
    "hot water": "Water",
    "egg beaten": ("Egg", "beaten"),
    "eggs beaten": ("Egg", "beaten"),
    "quail eggs": "Quail Egg",
    "egg yolk": "Egg Yolks",
    "mozzarella cheese": "Mozzarella",
    "parmesan cheese": "Parmesan",
    "cheddar": "Cheddar Cheese",
    # bouillon en sauzen
    "chicken broth": "Chicken Stock",
    "beef broth": "Beef Stock",
    "vegetable broth": "Vegetable Stock",
    "fish broth": "Fish Stock",
    "stock cubes": "Stock Cube",
    "seasoning cubes": "Stock Cube",
    "bouillon cube": "Stock Cube",
    "bouillon cubes": "Stock Cube",
    "tomato paste": "Tomato Puree",
    "tomato concentrate": "Tomato Puree",
    "ketchup": "Tomato Ketchup",
    "rice wine vinegar": "Rice Vinegar",
    "sesame oil": "Sesame Seed Oil",
    "toasted sesame oil": "Sesame Seed Oil",
    "sesame seeds": "Sesame Seed",
    "cooking oil": "Vegetable Oil",
    "canola oil": "Rapeseed Oil",
    "groundnut oil": "Peanut Oil",
    # vis en vlees
    "ground beef": "Minced Beef",
    "ground pork": "Minced Pork",
    "ground lamb": "Lamb Mince",
    "ground chicken": "Minced Chicken",
    "ground turkey": "Minced Turkey",
    "ground meat": "Minced Beef",
    "beef mince": "Minced Beef",
    "pork mince": "Minced Pork",
    "uncooked rice": "Rice",
    "ground sugar": "Caster Sugar",
    "coarse salt": "Salt",
    "shrimp": "Prawns",
    "shrimps": "Prawns",
    "jumbo shrimp": "Prawns",
    "prawn": "Prawns",
    "stew beef": "Beef",
    "stewing beef": "Beef",
    "chicken pieces": "Chicken",
    "squid mantles": "Squid",
    # noten en specerijen
    "shelled hazelnuts": "Hazelnuts",
    "hazelnut": "Hazelnuts",
    "cardamom pods": "Cardamom",
    "green cardamom pods": "Cardamom",
    "cardamom powder": "Ground Cardamom",
    "star anise pod": "Star Anise",
    "star anise pods": "Star Anise",
    "coriander powder": "Ground Coriander",
    "cumin powder": "Ground Cumin",
    "powdered ginger": "Ground Ginger",
    "ginger powder": "Ground Ginger",
    "turmeric powder": "Turmeric",
    "ground turmeric": "Turmeric",
    "non-iodised salt": "Salt",
    # namen die in recipes.json en cocktails.json anders geschreven stonden;
    # eten en drinken delen één boodschappenlijst, dus dat moet gelijk zijn
    "cranberry": "Cranberries",
    "cherry": "Cherries",
    "almond": "Almonds",
    "apples": "Apple",
    "cumin seed": "Cumin Seeds",
    "vanilla ice-cream": "Vanilla Ice Cream",
    "chocolate ice-cream": "Chocolate Ice Cream",
    "ice-cream": "Ice Cream",
    "table salt": "Salt",
    "sea salt flakes": "Sea Salt",
}

# ---------------------------------------------------------------- helpers


def clean_text(value):
    """Haalt vreemde witruimte en dubbele spaties weg."""
    if not value:
        return ""
    text = html.unescape(str(value))
    for weird in (" ", " ", "​", " ", " "):
        text = text.replace(weird, " ")
    text = text.replace("–", "-").replace("—", "-")
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return re.sub(r"[ \t]+", " ", text).strip()


def expand_fractions(text):
    """Zet ½ om naar 1/2, ook als het aan een cijfer vastzit (1½ -> 1 1/2)."""
    for symbol, ascii_form in UNICODE_FRACTIONS.items():
        text = re.sub(r"(\d)\s*" + symbol, r"\1 " + ascii_form, text)
        text = text.replace(symbol, ascii_form)
    return re.sub(r"\s+", " ", text).strip()


def space_units(text):
    """Maakt "100g" los naar "100 g", maar laat "1/2-inch" en "x400" met rust."""

    def repl(match):
        number, word = match.group(1), match.group(2)
        return f"{number} {word}" if word.lower() in UNIT_ALIASES else match.group(0)

    return re.sub(r"(\d)\s*([a-zA-Z]+)", repl, text)


def format_number(value):
    """Schrijft een getal als heel getal of als gangbare breuk.

    Een hoeveelheid als 1,2 kg blijft 1.2 kg: daar is geen gangbare breuk voor en
    "1 1/5 kg" zou niemand opschrijven.
    """
    if value is None:
        return ""
    frac = Fraction(value)
    if frac.denominator == 1:
        return str(frac.numerator)
    whole, rest = divmod(frac.numerator, frac.denominator)
    rest_frac = Fraction(rest, frac.denominator)
    if rest_frac not in DECIMAL_AS_FRACTION:
        return f"{float(frac):g}"
    rest_text = DECIMAL_AS_FRACTION[rest_frac]
    return f"{whole} {rest_text}" if whole else rest_text


NUMBER_RE = re.compile(
    r"""^\s*
    (?P<a>\d+(?:\.\d+)?)                 # eerste getal
    (?:\s*/\s*(?P<b>\d+))?               # eventueel /noemer
    (?:\s+(?P<c>\d+)\s*/\s*(?P<d>\d+))?  # eventueel gemengd getal
    """,
    re.VERBOSE,
)


NUMBER_FORM = r"(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)"
RANGE_RE = re.compile(rf"^\s*({NUMBER_FORM})\s*(?:-|to)\s*({NUMBER_FORM})(?![\d/])")


def to_fraction(text):
    """Leest "1", "1.5", "1/2" of "1 1/2" als breuk."""
    text = text.strip()
    mixed = re.match(r"^(\d+)\s+(\d+)/(\d+)$", text)
    if mixed:
        return Fraction(int(mixed.group(1))) + Fraction(int(mixed.group(2)), int(mixed.group(3)))
    return Fraction(text)


def parse_quantity(text):
    """Leest de hoeveelheid vooraan de tekst. Geeft (waarde, resttekst, weergave)."""
    range_match = RANGE_RE.match(text)
    if range_match:
        low, high = to_fraction(range_match.group(1)), to_fraction(range_match.group(2))
        display = f"{format_number(low)}-{format_number(high)}"
        # voor het meervoud van de eenheid telt de bovengrens
        return high, text[range_match.end():].strip(), display

    match = NUMBER_RE.match(text)
    if not match:
        return None, text, ""

    a, b, c, d = match.group("a"), match.group("b"), match.group("c"), match.group("d")
    if b:                                    # "1/2" of "1/2 3/4" (laatste bestaat niet)
        value = Fraction(a) / Fraction(b)
    elif c and d:                            # "1 1/2"
        value = Fraction(a) + Fraction(c) / Fraction(d)
    else:
        value = Fraction(a)
    return value, text[match.end():].strip(), format_number(value)


METRIC_SLASH = re.compile(r"(?i)^\s*(\d+(?:\.\d+)?(?:\s+\d+/\d+)?\s*(?:g|kg|ml|l))\s*/\s*\S.*$")


# Bij deze eenheden is "(400 g)" de inhoud van de verpakking en geen tweede
# schrijfwijze van dezelfde maat; die haakjes blijven dus staan.
PACKAGE_UNITS = {"can", "cans", "jar", "jars", "pack", "packs", "packet", "packets", "tin", "tins",
                 "tub", "tubs", "bag", "bags", "bottle", "bottles", "pot", "pots", "piece", "pieces",
                 "block", "blocks", "cake", "cakes"}


def prefer_metric(text):
    metric_first = METRIC_SLASH.match(text)
    if metric_first:
        return metric_first.group(1).strip()
    """Kiest bij dubbele maten de metrische kant: 75g/3oz -> 75g, 1 cup (240 ml) -> 1 cup."""
    metric = re.compile(r"(?i)^\s*(\d+(?:[.,]\d+)?)\s*(g|kg|ml|l|grams?|kilograms?|millilitres?|milliliters?|litres?|liters?)\s*$")

    # vorm "75g/3oz" of "650g/1lb 8 oz"
    if "/" in text and not re.search(r"\d\s*/\s*\d", text):
        left, right = text.split("/", 1)
        if metric.match(left.strip()):
            return left.strip()
        if metric.match(right.strip()):
            return right.strip()

    # vorm "12 ounces (340g)" of "1 cup (240 milliliters)"
    paren = re.search(r"\(([^)]*)\)", text)
    if paren:
        inside = paren.group(1).strip()
        outside = (text[: paren.start()] + text[paren.end():]).strip()
        inside_metric = bool(metric.match(inside))
        outside_imperial = bool(re.search(r"(?i)\b(oz|ounces?|lb|lbs|pounds?|cups?|tablespoons?|teaspoons?|tbsp|tsp)\b", outside))
        if inside_metric and outside_imperial:
            return inside
        outside_match = re.match(r"^(\d+)(?:\s+(\w+))?$", outside)
        if inside_metric and outside_match:
            if (outside_match.group(2) or "").lower() in PACKAGE_UNITS:
                return text          # "1 jar (400 g)" blijft zo
            # "2 (460g)" -> de hoeveelheid stuks is de bruikbare maat
            return outside
        if not inside_metric:
            return outside if outside else text
    return text


def canonical_unit(word, quantity):
    """Geeft de canonieke eenheid, in meervoud waar dat hoort."""
    unit = UNIT_ALIASES.get(word.lower())
    if unit is None:
        return None
    if unit in SINGULAR_ONLY:
        return unit
    plural = quantity is not None and quantity > 1
    if not plural:
        return unit
    if unit in IRREGULAR_PLURAL:
        return IRREGULAR_PLURAL[unit]
    if "(" in unit:  # "bottle (750 ml)" -> "bottles (750 ml)"
        head, _, tail = unit.partition(" (")
        return f"{head}s ({tail}"
    return unit + "s"


# Bijwoord achteraan hoort ervoor: "sliced thinly" -> "thinly sliced".
ADVERB_FIRST = re.compile(r"\b(chopped|sliced|diced|grated|crushed|minced|shredded|cut)\s+(finely|thinly|coarsely|roughly|thickly)\b")

# Twee bewerkingen achter elkaar krijgen een "and": "peeled crushed".
PREP_AND = re.compile(r"\b(peeled|trimmed|washed|rinsed|deseeded|drained|cooked|boiled)\s+(?=(crushed|sliced|chopped|diced|grated|minced|shredded|halved|quartered|cubed)\b)")

# Hoeveelheid 1 bij een maatwoord dat het al impliceert: "1 pinch" is "Pinch".
SINGLE_TO_WORD = {
    "1 pinch": "Pinch",
    "1 dash": "Dash",
    "1 splash": "Splash",
    "1 handful": "Handful",
    "1 knob": "Knob",
    "1 bunch": "Bunch",
    "1 drizzle": "Drizzle",
}


def normalize_prep(text):
    """Schrijft de bewerking achter de komma in één vorm."""
    prep = text.strip(" ,;.").lower()
    prep = re.sub(r"^(?:of|and|,)\s+", "", prep).strip()
    if not prep:
        return ""
    prep = re.split(r",?\s+or\s+\d", prep)[0].strip(" ,")   # "broken small, or 40 g ground"
    prep = re.split(r",?\s+plus\s+\d", prep)[0].strip(" ,")  # "plus 1 more tsp for the pot"
    prep = ADVERB_FIRST.sub(lambda m: f"{m.group(2)} {m.group(1)}", prep)
    prep = re.sub(r"\bcut (?!into|in )(cubes|chunks|wedges|strips|slices|pieces)\b", r"cut into \1", prep)
    prep = PREP_AND.sub(lambda m: f"{m.group(1)} and ", prep)
    return re.sub(r"\s+", " ", prep).strip()


def prepare_key(text):
    """Sleutels in de tabellen door dezelfde voorbewerking halen als de invoer."""
    return space_units(expand_fractions(clean_text(text))).lower().rstrip(".").strip()


MEASURE_OVERRIDES = {prepare_key(k): v for k, v in MEASURE_OVERRIDES.items()}
NAME_FROM_MEASURE = {(prepare_key(k), name): v for (k, name), v in NAME_FROM_MEASURE.items()}


MEASURE_NOISE = re.compile(r"(?i)^(?:about|approx\.?|approximately|around|add|roughly|some)\s+(?=\d|splash|pinch|dash)")


def normalize_measure(raw, ingredient_name=""):
    """Zet één maat om naar de vaste vorm. Geeft (maat, nieuwe_ingrediëntnaam_of_None)."""
    text = space_units(expand_fractions(clean_text(raw)))
    if not text:
        return "", None

    key = text.lower().rstrip(".").strip()
    if key not in MEASURE_OVERRIDES:
        text = MEASURE_NOISE.sub("", text)
        key = text.lower().rstrip(".").strip()

    # 1) hardcoded uitzonderingen
    if (key, ingredient_name) in NAME_FROM_MEASURE:
        measure, name = NAME_FROM_MEASURE[(key, ingredient_name)]
        return measure, name
    if key in MEASURE_OVERRIDES:
        return MEASURE_OVERRIDES[key], None

    # 2) maten zonder hoeveelheid
    plain = re.sub(r"[.,;]+$", "", key).strip()
    if plain in DESCRIPTIVE:
        return DESCRIPTIVE[plain], None

    # 3) "Juice of 1" en varianten
    juice = re.match(r"^(zest and juice|juice and zest|juice|zest)\s+of\s+(.+)$", plain)
    if juice:
        what = {"juice": "Juice", "zest": "Zest", "zest and juice": "Zest and juice",
                "juice and zest": "Zest and juice"}[juice.group(1)]
        amount = juice.group(2).strip()
        amount = {"one": "1", "two": "2", "three": "3", "half": "1/2", "a": "1"}.get(amount, amount)
        _, _, display = parse_quantity(amount)
        return f"{what} of {display or amount}", None

    # 4) verpakkingsinhoud achteraan even apart zetten: "1 jar (400 g)"
    suffix = ""
    tail = re.search(r"\s*(\([^)]*\))\s*$", text)
    if tail:
        head = text[: tail.start()].strip()
        words = head.split(" ")
        if len(words) == 2 and re.match(r"^\d+(\.\d+)?$", words[0]) and words[1].lower() in PACKAGE_UNITS:
            suffix = " " + tail.group(1)
            text = head

    # 5) metrische kant kiezen bij dubbele maten
    text = space_units(prefer_metric(text))

    # 6) hoeveelheid vooraan
    value, rest, display = parse_quantity(text)
    tokens = rest.split(" ") if rest else []
    if not display:
        first = tokens[0].lower().rstrip(".,") if tokens else ""
        if first in UNIT_ALIASES:
            value, display = Fraction(1), "1"
        else:
            words = re.sub(r"[.,;]+$", "", text).strip()
            if words.lower() in PREP_AS_NAME_PREFIX and ingredient_name:
                # "Black" bij Pepper hoort in de naam, niet in de maat
                return "", f"{PREP_AS_NAME_PREFIX[words.lower()]} {ingredient_name}"
            return (words[:1].upper() + words[1:]) if words else "", None

    # 7) eenheid opzoeken, waar die ook staat ("5 chopped cloves")
    unit = None
    unit_index = None
    for index, token in enumerate(tokens):
        candidate = canonical_unit(token.lower().strip(".,"), value)
        if candidate and all(word.lower().strip(".,") in PRE_UNIT_WORDS for word in tokens[:index]):
            unit, unit_index = candidate, index
            break

    if unit_index is None:
        before, after = tokens, []
    else:
        before, after = tokens[:unit_index], tokens[unit_index + 1:]
        # samengestelde eenheid: "3 cm piece"
        if unit in ("cm", "mm") and after and after[0].lower().strip(".,") in ("piece", "pieces"):
            unit = f"{unit} piece"
            after = after[1:]

    # 8) grootteaanduiding hoort voor de eenheid, de rest is bewerking
    size_words, prep_words = [], []
    for token in before:
        word = token.lower().strip(".,")
        if word in SIZE_WORDS or (word == "fresh" and unit):
            size_words.append(word)
        else:
            prep_words.append(token)
    prep_words += after

    prep = normalize_prep(" ".join(prep_words))
    size = " ".join(size_words)

    new_name = None
    if prep in PREP_AS_NAME_PREFIX and ingredient_name:
        new_name = f"{PREP_AS_NAME_PREFIX[prep]} {ingredient_name}"
        prep = ""
    elif prep == "crushed" and ingredient_name in CRUSHED_AS_NAME:
        new_name = f"Crushed {ingredient_name}"
        prep = ""

    if unit and unit.split(" ")[0] in DECIMAL_UNITS and value is not None and value.denominator != 1:
        display = f"{float(value):g}"

    parts = [display]
    if size:
        parts.append(size)
    if unit:
        parts.append(unit)
    measure = " ".join(parts)
    measure = SINGLE_TO_WORD.get(measure, measure)
    measure += suffix
    if prep:
        measure = f"{measure}, {prep}"
    return measure, new_name


def title_case_name(text):
    """Title Case met kleine woorden klein, streepjes en accenten intact."""
    words = text.split(" ")
    out = []
    for index, word in enumerate(words):
        low = word.lower()
        if index > 0 and low in LOWER_WORDS:
            out.append(low)
            continue
        pieces = re.split(r"([-'])", word)
        rebuilt = ""
        capitalize_next = True
        for piece in pieces:
            if piece in ("-", "'"):
                rebuilt += piece
                capitalize_next = piece == "-"
                continue
            if not piece:
                continue
            if capitalize_next:
                rebuilt += piece[:1].upper() + piece[1:].lower()
            else:
                rebuilt += piece.lower()
            capitalize_next = False
        out.append(rebuilt)
    return " ".join(out)


def normalize_ingredient(raw):
    """Geeft (naam, extra_bewerking)."""
    text = clean_text(raw)
    if not text:
        return "", ""
    text = re.sub(r"\s*[,;]\s*$", "", text)
    key = text.lower().strip()

    for table in (NAME_ALIASES, SYNONYMS):
        if key in table:
            alias = table[key]
            if isinstance(alias, tuple):
                return alias[0], alias[1]
            return alias, ""
    if key in NAME_EXACT:
        return NAME_EXACT[key], ""

    return title_case_name(text), ""


# ---------------------------------------------------------------- bereidingswijze

ABBREVIATIONS = {"approx", "mins", "min", "secs", "sec", "hrs", "hr", "etc", "e.g", "i.e", "dr",
                 "mr", "mrs", "no", "tsp", "tbsp", "oz", "lb", "g", "kg", "ml", "l", "st", "temp"}


def split_long_block(text):
    """Knipt één lang tekstblok in stappen op zinsgrenzen."""
    if len(text) < 200:
        return [text]
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
    steps, buffer = [], ""
    for part in parts:
        tail = re.sub(r"[^a-zA-Z.]", "", buffer.split(" ")[-1]).rstrip(".").lower() if buffer else ""
        if buffer and (len(buffer) < 45 or tail in ABBREVIATIONS):
            buffer = f"{buffer} {part}"
            continue
        if buffer:
            steps.append(buffer)
        buffer = part
    if buffer:
        steps.append(buffer)
    return steps


def normalize_instructions(raw):
    """Eén stap per regel, geen 'step 1', geen eigen nummering, hoofdletter vooraan."""
    text = clean_text(raw.replace("\r\n", "\n").replace("\r", "\n")) if raw else ""
    if not text:
        return ""
    # clean_text plet ook de regeleindes niet, maar spaties rond regels wel
    text = "\n".join(clean_text(line) for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"))

    steps = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if re.fullmatch(r"(?i)step\s*\d*[:.]?", line):
            continue
        if re.fullmatch(r"\d+[.)]?", line):
            continue
        line = re.sub(r"(?i)^step\s*\d+\s*[:.)-]?\s*", "", line).strip()
        line = re.sub(r"^\d+\s*[.)]\s+", "", line).strip()
        if not line:
            continue
        steps.append(line)

    # Ook binnen een reeks stappen knippen we een heel lang stuk op, zodat de
    # stappen in het hele bestand ongeveer even groot zijn.
    split = []
    for step in steps:
        # Eén tekstblok knippen we al vanaf 200 tekens; binnen een reeks stappen
        # pas vanaf 450, anders worden bestaande stappen onnodig opgehakt.
        threshold = 200 if len(steps) == 1 else 450
        split.extend(split_long_block(step) if len(step) > threshold else [step])
    steps = split

    out = []
    for step in steps:
        step = re.sub(r"\s+", " ", step).strip()
        step = step[:1].upper() + step[1:]
        if step:
            out.append(step)
    return "\n".join(out)


# ---------------------------------------------------------------- records

def normalize_record(record, max_slots, ingredient_key, measure_key, instructions_key):
    """Normaliseert één gerecht of drankje; de sleutelvolgorde blijft gelijk."""
    changes = Counter()
    result = dict(record)

    if instructions_key in result:
        before = result[instructions_key] or ""
        after = normalize_instructions(before)
        if after != before:
            changes["instructions"] += 1
        result[instructions_key] = after

    for i in range(1, max_slots + 1):
        ing_field, mea_field = f"{ingredient_key}{i}", f"{measure_key}{i}"
        raw_ing = record.get(ing_field)
        raw_mea = record.get(mea_field)
        if not (raw_ing or "").strip():
            # lege slots houden hun bestaande waarde (None of "")
            continue

        name, extra_prep = normalize_ingredient(raw_ing)
        measure, replacement_name = normalize_measure(raw_mea, name)
        if replacement_name:
            # Ook een naam die uit de maat komt gaat langs de synonymenlijst,
            # zodat "Coarse Salt" alsnog "Salt" wordt.
            name, more_prep = normalize_ingredient(replacement_name)
            extra_prep = extra_prep or more_prep
        if extra_prep:
            measure = f"{measure}, {extra_prep}" if measure else extra_prep.capitalize()

        if name != (raw_ing or "").strip():
            changes["ingredient"] += 1
        if measure != (raw_mea or "").strip():
            changes["measure"] += 1

        result[ing_field] = name
        if mea_field in record or measure:
            result[mea_field] = measure

    return result, changes


def process(path, max_slots, ingredient_key, measure_key, instructions_key, write):
    rows = json.loads(path.read_text(encoding="utf-8"))
    totals = Counter()
    out = []
    for row in rows:
        new, changes = normalize_record(row, max_slots, ingredient_key, measure_key, instructions_key)
        totals.update(changes)
        out.append(new)

    if write:
        compact = path.name == "cocktails.json"
        text = json.dumps(out, ensure_ascii=False, separators=(",", ":")) if compact else json.dumps(out, ensure_ascii=False, indent=2)
        path.write_text(text + ("" if compact else "\n"), encoding="utf-8")

    return out, totals


def report_measures(rows, max_slots, ingredient_key, measure_key):
    counter = Counter()
    for row in rows:
        for i in range(1, max_slots + 1):
            if (row.get(f"{ingredient_key}{i}") or "").strip():
                counter[(row.get(f"{measure_key}{i}") or "").strip()] += 1
    return counter


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="alleen rapporteren, niets wijzigen")
    parser.add_argument("--report", action="store_true", help="alle unieke maten en namen laten zien")
    args = parser.parse_args()
    write = not (args.check or args.report)

    for path, slots, ing_key, mea_key in ((MEALS, 20, "strIngredient", "strMeasure"), (DRINKS, 15, "strIngredient", "strMeasure")):
        if not path.exists():
            print(f"overgeslagen, bestaat niet: {path}", file=sys.stderr)
            continue
        before = report_measures(json.loads(path.read_text(encoding="utf-8")), slots, ing_key, mea_key)
        rows, totals = process(path, slots, ing_key, mea_key, "strInstructions", write)
        after = report_measures(rows, slots, ing_key, mea_key)

        names = Counter()
        for row in rows:
            for i in range(1, slots + 1):
                v = (row.get(f"{ing_key}{i}") or "").strip()
                if v:
                    names[v] += 1

        print(f"\n{path.name}: {len(rows)} records")
        print(f"  maten aangepast        : {totals['measure']}")
        print(f"  namen aangepast        : {totals['ingredient']}")
        print(f"  bereidingswijzen bijgew: {totals['instructions']}")
        print(f"  unieke maten           : {len(before)} -> {len(after)}")
        print(f"  unieke ingrediëntnamen : {len(names)}")
        if args.report:
            print("  --- unieke maten na normalisatie ---")
            for measure, count in sorted(after.items(), key=lambda kv: (-kv[1], kv[0])):
                print(f"    {count:>4}  {measure!r}")
        if write:
            print(f"  weggeschreven naar {path}")


if __name__ == "__main__":
    main()
