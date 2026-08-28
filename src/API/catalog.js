// Eén plek waar zowel de gerechten (TheMealDB) als de cocktails (TheCocktailDB)
// worden ingelezen en naar hetzelfde model worden omgezet. De rest van de app
// weet daardoor niets meer over het formaat van de twee databases.
//
// Genormaliseerd item:
// {
//   type: 'meal' | 'drink',
//   id, key, title, image,
//   tags: string[],
//   ingredients: [{ name, measure }],
//   steps: string[],
//   facts: [{ icon, label }],
//   source, video,
// }

export const MEAL = 'meal';
export const DRINK = 'drink';

const SOURCES = {
    [MEAL]: { url: './API/recipes.json', maxIngredients: 20 },
    [DRINK]: { url: './API/cocktails.json', maxIngredients: 15 },
};

const catalog = new Map(); // key -> genormaliseerd item
const loaded = new Map(); // type -> Promise<item[]> zodat we per type maar één keer fetchen

export function itemKey(type, id) {
    return `${type}:${id}`;
}

export function getItem(type, id) {
    return catalog.get(itemKey(type, id)) || null;
}

export function getItems(type) {
    return [...catalog.values()].filter((item) => item.type === type);
}

export function isLoaded(type) {
    return loaded.has(type);
}

// Laadt een database in en cachet zowel het resultaat als de belofte, zodat
// twee gelijktijdige aanroepen niet twee keer dezelfde json downloaden.
export function loadCatalog(type) {
    if (loaded.has(type)) return loaded.get(type);

    const source = SOURCES[type];
    if (!source) return Promise.reject(new Error(`Onbekend catalogustype: ${type}`));

    const promise = fetch(source.url)
        .then((response) => {
            if (!response.ok) throw new Error(`${source.url} gaf status ${response.status}`);
            return response.json();
        })
        .then((rows) => {
            const items = [];
            for (const row of rows || []) {
                const item = type === MEAL ? normalizeMeal(row) : normalizeDrink(row);
                if (!item) continue;
                if (catalog.has(item.key)) continue;
                catalog.set(item.key, item);
                items.push(item);
            }
            return items;
        })
        .catch((err) => {
            // Belofte uit de cache halen, zodat een volgende poging opnieuw mag proberen.
            loaded.delete(type);
            throw err;
        });

    loaded.set(type, promise);
    return promise;
}

function collectIngredients(row, max) {
    const ingredients = [];

    for (let i = 1; i <= max; i++) {
        const name = (row[`strIngredient${i}`] || '').trim();
        if (!name) continue;
        ingredients.push({
            name,
            measure: (row[`strMeasure${i}`] || '').trim(),
        });
    }

    return ingredients;
}

// TheMealDB levert de bereidingswijze als één tekstblok, soms met "step 1"-regels
// of met "1." aan het begin van elke regel. Die ruis halen we eruit.
function splitSteps(text) {
    if (!text) return [];

    const lines = text
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .filter((line) => !/^step\s*\d*[:.]?$/i.test(line))
        .filter((line) => !/^\d+[.)]?$/.test(line))
        .map((line) => line.replace(/^(?:step\s*)?\d+[.)]\s*/i, '').trim())
        .filter(Boolean);

    return lines.length > 0 ? lines : [text.trim()];
}

function pushTag(tags, value) {
    if (!value) return;
    const tag = String(value).trim().toLowerCase();
    if (tag && !tags.includes(tag)) tags.push(tag);
}

function tagsFromField(tags, field) {
    if (!field) return;
    String(field)
        .split(',')
        .forEach((tag) => pushTag(tags, tag));
}

function normalizeMeal(row) {
    if (!row || !row.idMeal) return null;

    const origin = (row.strArea || row.strCountry || '').trim();
    const tags = [];
    pushTag(tags, row.strCategory);
    pushTag(tags, origin);
    tagsFromField(tags, row.strTags);

    const facts = [];
    if (row.strCategory) facts.push({ icon: 'fa-solid fa-utensils', label: row.strCategory });
    if (origin) facts.push({ icon: 'fa-solid fa-earth-europe', label: origin });

    return {
        type: MEAL,
        id: row.idMeal,
        key: itemKey(MEAL, row.idMeal),
        title: (row.strMeal || 'Naamloos gerecht').trim(),
        image: row.strMealThumb || '',
        tags,
        facts,
        ingredients: collectIngredients(row, SOURCES[MEAL].maxIngredients),
        steps: splitSteps(row.strInstructions),
        source: row.strSource || '',
        video: row.strYoutube || '',
    };
}

function normalizeDrink(row) {
    if (!row || !row.idDrink) return null;

    const alcohol = (row.strAlcoholic || '').trim();
    const tags = [];
    pushTag(tags, row.strCategory);
    pushTag(tags, alcohol);
    pushTag(tags, row.strGlass);
    if (row.strIBA) pushTag(tags, 'iba');
    tagsFromField(tags, row.strTags);

    const facts = [];
    if (row.strCategory) facts.push({ icon: 'fa-solid fa-martini-glass-citrus', label: row.strCategory });
    if (alcohol) {
        facts.push({
            icon: /non/i.test(alcohol) ? 'fa-solid fa-bottle-water' : 'fa-solid fa-wine-bottle',
            label: alcohol === 'Alcoholic' ? 'Alcoholisch' : alcohol === 'Non alcoholic' ? 'Alcoholvrij' : alcohol,
        });
    }
    if (row.strGlass) facts.push({ icon: 'fa-solid fa-whiskey-glass', label: row.strGlass });

    return {
        type: DRINK,
        id: row.idDrink,
        key: itemKey(DRINK, row.idDrink),
        title: (row.strDrink || 'Naamloze cocktail').trim(),
        image: row.strDrinkThumb || '',
        tags,
        facts,
        ingredients: collectIngredients(row, SOURCES[DRINK].maxIngredients),
        steps: splitSteps(row.strInstructions),
        source: '',
        video: row.strVideo || '',
    };
}
