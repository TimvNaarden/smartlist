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
    discover.js     De ontdekpagina: kaarten, filters, popup, opslaan, delen.
                    Wordt door Recepten.html en Cocktails.html gebruikt
    shopping.js     De boodschappenlijst, gedeeld tussen beide pagina's
    storage.js      Veilige wrapper om localStorage
    nav.js          Menu en actieve pagina
    recipes.json    790 gerechten uit TheMealDB
    cocktails.json  627 drankjes uit TheCocktailDB
    AH_API.js       Albert Heijn bonusintegratie (nu niet in gebruik)
    AH_proxy.php    Doorgeefluik voor de AH api, met host-allowlist
    Helperfunctions.js  Vertaaltabel voor de AH-integratie
tools/
  fetch_cocktails.py  Bouwt src/API/cocktails.json opnieuw op
docker/
  smartlist.conf    Apache: gzip en cache-headers voor de json-databases
```

## Databases verversen

De site doet tijdens gebruik geen enkele aanvraag naar TheMealDB of
TheCocktailDB; beide databases staan als json in de repository.

```bash
python3 tools/fetch_cocktails.py     # schrijft src/API/cocktails.json
```

`recipes.json` is eerder op dezelfde manier uit TheMealDB gehaald.

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
