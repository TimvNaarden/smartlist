# SmartList

Kies gerechten en drankjes en krijg er één boodschappenlijst uit, met eten en
drinken netjes gescheiden. Statische site: html, css en ES modules, geserveerd
door Apache in een php-container.

## Lokaal draaien

```bash
docker compose -f docker-compose.host.yaml up --build   # http://localhost:8080
```

Of zonder Docker, alleen voor het front-end deel:

```bash
python3 -m http.server 8080 --directory src
```

De php-proxy (`src/API/AH_proxy.php`) werkt alleen in de container, de rest van
de site werkt met elke statische server.

## Structuur

```
src/
  index.html        Homepagina met twee ingangen: eten en drinken
  Recepten.html     Ontdekpagina voor gerechten
  Cocktails.html    Ontdekpagina voor cocktails en mocktails
  Contact.html
  styles.css        Alle styling, met kleurtokens per thema
  API/
    catalog.js      Leest recipes.json en cocktails.json en zet beide om naar
                    hetzelfde model (titel, ingrediënten, stappen, tags)
    amounts.js      Telt hoeveelheden van hetzelfde ingrediënt bij elkaar op
    discover.js     De ontdekpagina: kaarten, filters, popup, opslaan, delen.
                    Wordt door Recepten.html en Cocktails.html gebruikt
    shopping.js     De boodschappenlijst, gedeeld tussen beide pagina's
    storage.js      Veilige wrapper om localStorage
    nav.js          Menu en actieve pagina
    recipes.json    1110 gerechten: 790 uit TheMealDB, 320 uit Wikibooks
    cocktails.json  627 drankjes uit TheCocktailDB
    AH_API.js       Albert Heijn bonusintegratie (nu niet in gebruik)
    AH_proxy.php    Doorgeefluik voor de AH api, met host-allowlist
    Helperfunctions.js  Vertaaltabel voor de AH-integratie
tools/
  fetch_cocktails.py  Bouwt src/API/cocktails.json opnieuw op
  fetch_wikibooks.py  Haalt extra gerechten uit de Wikibooks Cookbook
  fetch_images.py     Zet de afbeeldingen van die gerechten in de repo
  normalize_data.py   Maakt maten, namen en stappen in beide databases gelijk
  classify_meals.py   Zet categorie en keuken van de gerechten goed
  check_data.py       Controleert beide databases op fouten
docker/
  smartlist.conf    Apache: gzip en cache-headers voor de json-databases
```

## Databases verversen

De site doet tijdens gebruik geen enkele aanvraag naar TheMealDB, TheCocktailDB
of Wikibooks; alle gegevens staan als json in de repository.

```bash
python3 tools/fetch_cocktails.py           # src/API/cocktails.json opnieuw opbouwen
python3 tools/fetch_wikibooks.py --limit 320  # extra gerechten toevoegen
python3 tools/fetch_images.py              # de afbeeldingen daarvan binnenhalen
python3 tools/normalize_data.py            # maten en namen gelijktrekken
python3 tools/classify_meals.py            # categorie en keuken goedzetten
python3 tools/check_data.py                # controleren
```

Die volgorde is belangrijk: `fetch_images.py` leest en schrijft recipes.json, dus
`normalize_data.py` hoort erna te komen. `normalize_data.py` is idempotent, dus
nog een keer draaien kan altijd.

### Waar de gerechten vandaan komen

| Bron | Aantal | id-bereik |
| --- | --- | --- |
| TheMealDB | 790 | 52764 - 53579 |
| Wikibooks Cookbook | 320 | 90001 - 90320 |

TheMealDB bevat in totaal 793 gerechten en die staan er vrijwel allemaal al in;
die bron is dus uitgeput. De Wikibooks Cookbook is de tweede bron: 3792 recepten,
waarvan er 589 een afbeelding en een bruikbare structuur hebben. Daarvan zijn de
320 gekozen die het beste passen bij de gerechten die al opgeslagen waren
(Aziatisch, Spaans, Turks, bijgerechten en nagerechten), en die de
kwaliteitscontrole in `fetch_wikibooks.py` doorkomen.

De id's beginnen bij 90001 zodat ze nooit botsen met nieuwe id's van TheMealDB.

### Licentie van de Wikibooks-gerechten

De tekst van de Wikibooks Cookbook staat onder CC BY-SA 4.0 en de afbeeldingen
onder hun eigen licentie op Wikimedia Commons. Per gerecht staat daarom:

- `strSource` - de Wikibooks-pagina
- `strImageSource` - de bestandspagina van de afbeelding op Commons
- `strCreativeCommonsConfirmed` - `"Yes"`

De popup laat bij die gerechten "Tekst van Wikibooks Cookbook, CC BY-SA 4.0" zien
met een link naar de bron en naar de foto. Haal die vermelding niet weg: de
licentie vraagt erom.

De afbeeldingen staan in `src/Images/recipes/` in plaats van dat ze van Commons
worden gehaald. Commons knijpt het aantal verzoeken per bezoeker af (http 429) en
bij het doorbladeren van meer dan duizend kaarten loop je daar tegenaan.

## Eén vorm voor maten en namen

`tools/normalize_data.py` schrijft alle hoeveelheden in dezelfde vorm en geeft elk
ingrediënt één naam. Dat is nodig omdat de boodschappenlijst ingrediënten
samenvoegt op naam: zonder dit levert "1 tbsp olive oil" naast "1 tablespoon of
olive oil" twee regels op.

De vorm is:

```
<hoeveelheid> <eenheid>[, bewerking]      1 tbsp | 100 g | 2 cloves, minced
<omschrijving>                            To taste | Pinch | For frying
```

Wat er onder andere gelijkgetrokken is:

| Was | Is |
| --- | --- |
| `1 tablespoon`, `1 tbs`, `1 tblsp`, `1 tbls` | `1 tbsp` |
| `1 teaspoon`, `1 Tsp` | `1 tsp` |
| `100g`, `100 Grams`, `100 g` | `100 g` |
| `½ tsp`, `0.5 tsp`, `1/2 tsp` | `1/2 tsp` |
| `75g/3oz`, `1 cup (240 ml)` | `75 g`, `1 cup` |
| `2 cloves minced`, `1 chopped` | `2 cloves, minced`, `1, chopped` |
| `sliced thinly` | `thinly sliced` |
| `Sprinking`, `Spinkling` | `For sprinkling` |
| `cilantro`, `Coriander Leaves` | `Coriander` |
| `scallions`, `green onions` | `Spring Onions` |
| `all purpose flour` | `Plain Flour` |
| `powdered sugar`, `superfine sugar` | `Icing Sugar`, `Caster Sugar` |
| `chicken broth`, `tomato paste` | `Chicken Stock`, `Tomato Puree` |
| `ground beef`, `shrimp` | `Minced Beef`, `Prawns` |

De bereidingswijze wordt één stap per regel, zonder `step 1`-regels en zonder
eigen nummering; de nummers komen van de `<ol>` in de pagina. Stappen langer dan
450 tekens worden op zinsgrenzen gesplitst.

### Hoeveelheden optellen op de lijst

`src/API/amounts.js` telt de hoeveelheden van hetzelfde ingrediënt bij elkaar op,
zodat drie recepten met knoflook één regel geven:

| Uit de recepten | Op de lijst |
| --- | --- |
| `3 cloves, minced` + `1 clove` + `2 cloves` | `6 cloves` |
| `1 tsp` + `1/2 tsp` | `1 1/2 tsp` |
| `500 g` + `800 g` | `1.3 kg` |
| `1 small` + `1` | `2` |
| `To taste` + `1 tsp` | `1 tsp` |
| `1 tbsp` + `2 tsp` | `1 tbsp + 2 tsp` |

Wat niet bij elkaar past blijft naast elkaar staan. De bewerking (`, minced`)
gaat er af: op een boodschappenlijst gaat het om de hoeveelheid, niet om wat je er
straks mee doet. Metrische eenheden houden een decimaal getal, de rest krijgt
breuken, en gram gaat in kilo over zodra het meer dan 1000 wordt.

## Categorie en keuken

`tools/classify_meals.py` repareert de indeling. De categorieën van TheMealDB
mengen gangen (Dessert, Side, Starter), hoofdbestanddelen (Beef, Chicken) en dieet
(Vegan, Vegetarian). Of een cake onder Dessert of onder Vegetarian hoort is een
keuze, geen fout, dus het script verandert alleen wat de ingrediënten
tegenspreken:

- een gerecht onder Vegetarian of Vegan met vlees of vis erin
- Vegan met zuivel of ei erin
- een categorie die een hoofdbestanddeel noemt dat er helemaal niet in zit

Vissaus, oestersaus, gedroogde garnaal en bouillonblokjes gelden als smaakmaker,
niet als hoofdbestanddeel: een Thaise curry met vissaus is geen visgerecht. Ze
zijn ook geen reden om het label Vegetarian weg te halen, want iedereen ruilt ze
in voor de plantaardige variant. Plantaardige vervangers (`almond milk`,
`vegan butter`, `flax eggs`, `peanut butter`) gelden niet als zuivel of ei.

Bij een afgekapte ingrediëntenlijst (alle 20 plekken gevuld) of een
plaatsvervanger als `Your Choice of Meat` blijft de bestaande categorie staan; dan
weet de bron het beter dan de lijst.

`strArea` en `strCountry` worden op elkaar afgestemd. Er stond bij 145 gerechten
geen keuken terwijl het land wel bekend was, en bij 142 stond de landsnaam in
`strArea` (`Netherlands` in plaats van `Dutch`). De filters en de kaarten gebruiken
`strArea`, dus die moet de vaste vorm van TheMealDB hebben.

## Boodschappenlijst

De selectie staat in `localStorage`, niet in het geheugen van één pagina. Je kunt
dus op de receptenpagina een gerecht aanvinken, doorlopen naar de cocktailpagina
en daar een drankje toevoegen: beide staan daarna in dezelfde lijst, onder de
koppen **Boodschappen** en **Drank**.

Gebruikte sleutels:

| Sleutel | Inhoud |
| --- | --- |
| `smartlist_selection` | gekozen id's per soort (`meal`, `drink`) |
| `smartlist_selection_labels` | titels van gekozen items, zodat de andere database niet hoeft te worden geladen om een naam te tonen |
| `smartlist_shopping_checked_v2` | afgevinkte regels per sectie |
| `smartlist_saved_recipes` | opgeslagen gerechten |
| `smartlist_saved_cocktails` | opgeslagen cocktails |

## Deelbare links

| Link | Doet |
| --- | --- |
| `Recepten.html?recept=52771` | opent dat recept direct |
| `Cocktails.html?cocktail=17222` | opent die cocktail direct |
| `Recepten.html?recepten=1,2,3` | toont alleen die gerechten |
| `Cocktails.html?cocktails=1,2,3` | toont alleen die cocktails |
| `Recepten.html?boodschappen=m52771,d17222` | toont een gedeelde boodschappenlijst (`m` = gerecht, `d` = drankje) |

Een gedeelde boodschappenlijst verandert niets aan de eigen lijst; er staat een
knop om hem over te nemen.

## Albert Heijn bonus

`AH_API.js` haalt de weekbonus bij Albert Heijn op en `Helperfunctions.js` bevat
de vertaaltabel van Nederlandse productnamen naar de Engelse ingrediëntnamen van
TheMealDB. Die koppeling staat nu uit: geen enkele pagina laadt deze bestanden,
en de kaarten en popup tonen dus geen bonusproducten. Weer aansluiten betekent:
de bonuslijst ophalen, per gerecht matchen op de genormaliseerde ingrediëntnamen
en het resultaat aan het item uit `catalog.js` hangen.

`AH_proxy.php` accepteert alleen https-adressen op `api.ah.nl`. Zonder die
controle is het bestand een open proxy waarmee iedereen willekeurige adressen via
de server kan opvragen.
