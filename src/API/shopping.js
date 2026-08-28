// De boodschappenlijst. Deze module is opzettelijk paginaonafhankelijk: de
// selectie staat in localStorage, dus je kunt op de receptenpagina een gerecht
// aanvinken, doorlopen naar de cocktailpagina en daar een drankje toevoegen.
// Eten en drinken blijven in de lijst zelf netjes gescheiden.

import { AISLES, aisleOf } from './aisles.js';
import { schaalIngredienten, voegMatenSamen } from './amounts.js';
import { DRINK, MEAL, getItem, isLoaded, itemKey, loadCatalog } from './catalog.js';
import { readJSON, writeJSON } from './storage.js';

const SELECTION_KEY = 'smartlist_selection';
const LABEL_KEY = 'smartlist_selection_labels';
const FACTOR_KEY = 'smartlist_selection_factors';
const CHECKED_KEY = 'smartlist_shopping_checked_v2';
const SELECTION_EVENT = 'smartlist:selection';

const SECTIONS = [
    { type: MEAL, title: 'Boodschappen', icon: 'fa-solid fa-basket-shopping', empty: 'Nog geen gerechten geselecteerd.' },
    { type: DRINK, title: 'Drank', icon: 'fa-solid fa-martini-glass-citrus', empty: 'Nog geen cocktails geselecteerd.' },
];

// ---------- Selectie ----------

export function getSelection() {
    const stored = readJSON(SELECTION_KEY, {});
    return {
        [MEAL]: Array.isArray(stored[MEAL]) ? stored[MEAL].map(String) : [],
        [DRINK]: Array.isArray(stored[DRINK]) ? stored[DRINK].map(String) : [],
    };
}

function saveSelection(selection) {
    writeJSON(SELECTION_KEY, selection);
    document.dispatchEvent(new CustomEvent(SELECTION_EVENT, { detail: selection }));
}

export function selectionCount(selection = getSelection()) {
    return selection[MEAL].length + selection[DRINK].length;
}

export function isSelected(type, id) {
    return getSelection()[type].includes(String(id));
}

export function toggleSelection(type, id, shouldSelect) {
    const selection = getSelection();
    const key = String(id);
    const list = selection[type];
    const index = list.indexOf(key);
    const select = shouldSelect === undefined ? index === -1 : shouldSelect;

    if (select && index === -1) list.push(key);
    if (!select && index !== -1) list.splice(index, 1);

    saveSelection(selection);
    return select;
}

export function clearSelection() {
    saveSelection({ [MEAL]: [], [DRINK]: [] });
}

// De titels worden apart bewaard. Zo kan het selectiepaneel op de cocktailpagina
// ook de namen van gekozen gerechten laten zien zonder daarvoor de hele
// receptendatabase te downloaden.
export function rememberLabel(item) {
    const labels = readJSON(LABEL_KEY, {});
    labels[itemKey(item.type, item.id)] = item.title;
    writeJSON(LABEL_KEY, labels);
}

export function getLabel(type, id) {
    const item = getItem(type, id);
    if (item) return item.title;
    return readJSON(LABEL_KEY, {})[itemKey(type, id)] || (type === DRINK ? 'Onbekende cocktail' : 'Onbekend gerecht');
}

// Hoeveel keer een recept op de lijst staat. Zet je een recept in de popup op 6
// personen terwijl het er 4 zijn, dan is de factor 1.5 en rekent de lijst alle
// hoeveelheden mee.
export function getFactor(type, id) {
    const factors = readJSON(FACTOR_KEY, {});
    const value = Number(factors[itemKey(type, id)]);
    return value > 0 ? value : 1;
}

export function setFactor(type, id, factor) {
    const factors = readJSON(FACTOR_KEY, {});
    if (factor && factor !== 1) {
        factors[itemKey(type, id)] = factor;
    } else {
        delete factors[itemKey(type, id)];
    }
    writeJSON(FACTOR_KEY, factors);
    document.dispatchEvent(new CustomEvent(SELECTION_EVENT, { detail: getSelection() }));
}

export function onSelectionChange(handler) {
    document.addEventListener(SELECTION_EVENT, (event) => handler(event.detail));
}

// ---------- Lijst opbouwen ----------

// Voegt dezelfde ingrediënten uit verschillende recepten samen tot één regel.
// De hoeveelheden worden opgeteld, dus drie recepten met knoflook geven "6
// cloves" en niet "3 cloves + 1 clove + 2 cloves".
function mergeIngredients(items) {
    const merged = new Map();

    items.forEach((item) => {
        const ingredients = schaalIngredienten(item.ingredients, getFactor(item.type, item.id));
        ingredients.forEach((ingredient) => {
            const key = ingredient.name.toLowerCase();
            if (!merged.has(key)) {
                merged.set(key, { name: ingredient.name, measures: [], from: [] });
            }
            const entry = merged.get(key);
            if (ingredient.measure) entry.measures.push(ingredient.measure);
            if (!entry.from.includes(item.title)) entry.from.push(item.title);
        });
    });

    return [...merged.values()]
        .map((entry) => ({ ...entry, measure: voegMatenSamen(entry.measures) }))
        .sort((a, b) => a.name.localeCompare(b.name, 'nl'));
}

// Verdeelt de regels over de schappen, in de volgorde waarin je de winkel
// doorloopt. Schappen zonder regels laten we weg.
function groupByAisle(ingredients, fallback) {
    const groups = new Map();

    ingredients.forEach((ingredient) => {
        const id = aisleOf(ingredient.name, fallback);
        if (!groups.has(id)) groups.set(id, []);
        groups.get(id).push(ingredient);
    });

    return AISLES.filter((aisle) => groups.has(aisle.id)).map((aisle) => ({
        ...aisle,
        ingredients: groups.get(aisle.id),
    }));
}

export function buildShoppingList(selection = getSelection()) {
    return SECTIONS.map((section) => {
        const items = selection[section.type].map((id) => getItem(section.type, id)).filter(Boolean);
        const ingredients = mergeIngredients(items);
        return {
            ...section,
            items,
            ingredients,
            aisles: groupByAisle(ingredients, section.type === DRINK ? 'drank' : 'overig'),
        };
    });
}

// ---------- Afgevinkte regels ----------

function getCheckedMap() {
    return readJSON(CHECKED_KEY, {});
}

function checkedKey(type, name) {
    return `${type}:${name.toLowerCase()}`;
}

function setChecked(type, name, checked) {
    const map = getCheckedMap();
    if (checked) {
        map[checkedKey(type, name)] = true;
    } else {
        delete map[checkedKey(type, name)];
    }
    writeJSON(CHECKED_KEY, map);
}

export function clearChecked() {
    writeJSON(CHECKED_KEY, {});
}

// ---------- Popup ----------

// Zorgt dat beide databases beschikbaar zijn voordat we de lijst tekenen. De
// cocktail-json wordt op de receptenpagina dus alleen gedownload wanneer er ook
// echt een drankje in de lijst staat (en omgekeerd).
async function ensureCatalogs(selection) {
    const needed = SECTIONS.filter((section) => selection[section.type].length > 0 && !isLoaded(section.type)).map((section) => section.type);

    await Promise.all(needed.map((type) => loadCatalog(type).catch((err) => console.error('Kon catalogus niet laden:', err))));
}

// `shared` staat aan wanneer iemand een gedeelde lijst opent. Die lijst wordt dan
// los van de eigen selectie getoond, zodat we niet zomaar in andermans lijstje
// gaan roeren.
export async function renderShoppingList(selection = getSelection(), { shared = false } = {}) {
    const modal = document.querySelector('.boodschappenpopup');
    if (!modal) return;

    const container = modal.querySelector('.boodschappensecties');
    const status = modal.querySelector('.boodschappenstatus');
    if (!container) return;

    modal.dataset.shared = shared ? 'ja' : 'nee';
    modal.dataset.selection = encodeSelection(selection);

    const sharedNotice = modal.querySelector('.boodschappengedeeld');
    if (sharedNotice) sharedNotice.hidden = !shared;
    modal.querySelectorAll('.eigenlijstactie').forEach((element) => {
        element.hidden = shared;
    });

    await ensureCatalogs(selection);

    const sections = buildShoppingList(selection);
    const total = sections.reduce((sum, section) => sum + section.ingredients.length, 0);
    const checkedMap = getCheckedMap();

    container.innerHTML = '';

    if (total === 0 && status) {
        status.textContent = shared
            ? 'Deze gedeelde lijst is leeg of kon niet worden gelezen.'
            : 'Selecteer eerst een gerecht of cocktail met het vinkje op de kaart.';
        status.hidden = false;
    } else if (status) {
        status.hidden = true;
    }

    sections.forEach((section) => {
        if (section.items.length === 0) return;

        const wrapper = document.createElement('section');
        wrapper.className = `boodschappensectie sectie-${section.type}`;

        const heading = document.createElement('h4');
        heading.innerHTML = `<i class="${section.icon}"></i> ${section.title}`;

        const count = document.createElement('span');
        count.className = 'sectieaantal';
        count.textContent = `${section.ingredients.length} ${section.ingredients.length === 1 ? 'item' : 'items'}`;
        heading.appendChild(count);

        wrapper.appendChild(heading);

        section.aisles.forEach((aisle) => {
            const aisleHeading = document.createElement('h5');
            aisleHeading.className = 'schapkop';
            aisleHeading.innerHTML = `<i class="${aisle.icoon}" aria-hidden="true"></i> ${aisle.naam}`;

            const list = document.createElement('ul');
            list.className = 'boodschappenlijst';

            aisle.ingredients.forEach((ingredient) => {
                const li = document.createElement('li');
                li.className = 'boodschapitem';

                const label = document.createElement('label');

                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.checked = !!checkedMap[checkedKey(section.type, ingredient.name)];

                const text = document.createElement('span');
                text.textContent = ingredient.measure ? `${ingredient.measure} ${ingredient.name}` : ingredient.name;

                const from = document.createElement('small');
                from.textContent = ingredient.from.join(', ');

                checkbox.addEventListener('change', () => {
                    setChecked(section.type, ingredient.name, checkbox.checked);
                    li.classList.toggle('afgevinkt', checkbox.checked);
                });

                li.classList.toggle('afgevinkt', checkbox.checked);
                label.appendChild(checkbox);
                label.appendChild(text);
                li.appendChild(label);
                li.appendChild(from);
                list.appendChild(li);
            });

            wrapper.appendChild(aisleHeading);
            wrapper.appendChild(list);
        });

        container.appendChild(wrapper);
    });

    modal.classList.add('open');
    document.body.classList.add('geen-scroll');
}

// Neemt een gedeelde lijst over in de eigen selectie.
export function adoptSharedList() {
    const modal = document.querySelector('.boodschappenpopup');
    if (!modal) return getSelection();

    const shared = decodeSelection(modal.dataset.selection || '');
    const own = getSelection();

    [MEAL, DRINK].forEach((sectionType) => {
        shared[sectionType].forEach((id) => {
            if (!own[sectionType].includes(id)) own[sectionType].push(id);
            // Titels meenemen, zodat het selectiepaneel ze ook laat zien als de
            // andere database nog niet is ingelezen.
            const item = getItem(sectionType, id);
            if (item) rememberLabel(item);
        });
    });

    saveSelection(own);
    return own;
}

export function hideShoppingList() {
    const modal = document.querySelector('.boodschappenpopup');
    if (!modal) return;
    modal.classList.remove('open');
    document.body.classList.remove('geen-scroll');
}

// ---------- Delen ----------

// Compacte vorm: m<id> voor een gerecht, d<id> voor een drankje.
export function encodeSelection(selection) {
    return [...selection[MEAL].map((id) => `m${id}`), ...selection[DRINK].map((id) => `d${id}`)].join(',');
}

export function decodeSelection(value) {
    const selection = { [MEAL]: [], [DRINK]: [] };

    (value || '')
        .split(',')
        .map((part) => part.trim())
        .filter(Boolean)
        .forEach((part) => {
            if (part.startsWith('d')) {
                selection[DRINK].push(part.slice(1));
            } else if (part.startsWith('m')) {
                selection[MEAL].push(part.slice(1));
            } else {
                // Oude links bevatten alleen recept-id's zonder prefix.
                selection[MEAL].push(part);
            }
        });

    return selection;
}

export async function shareViaWebShareOrClipboard(shareData, fallbackMessage) {
    if (navigator.share) {
        try {
            await navigator.share(shareData);
            return;
        } catch (err) {
            if (err.name === 'AbortError') return;
            console.error('Delen mislukt:', err);
        }
    }

    try {
        await navigator.clipboard.writeText(shareData.url);
        showToast(fallbackMessage);
    } catch (err) {
        console.error('Kopiëren mislukt:', err);
        showToast('Kopiëren lukte niet. Kopieer de link uit de adresbalk.');
    }
}

export async function shareShoppingList() {
    const encoded = encodeSelection(getSelection());
    if (!encoded) {
        showToast('Je lijst is nog leeg.');
        return;
    }

    const url = new URL(window.location.href);
    url.search = `?boodschappen=${encoded}`;

    await shareViaWebShareOrClipboard(
        {
            title: 'Mijn boodschappenlijst',
            text: 'Bekijk mijn boodschappenlijst op SmartList',
            url: url.toString(),
        },
        'Link gekopieerd naar klembord!'
    );
}

export function shoppingListAsText(sections = buildShoppingList()) {
    return sections
        .filter((section) => section.ingredients.length > 0)
        .map((section) => {
            const blocks = section.aisles.map((aisle) => {
                const lines = aisle.ingredients.map((item) => `- ${item.measure ? `${item.measure} ` : ''}${item.name}`);
                return `${aisle.naam}\n${lines.join('\n')}`;
            });
            return `${section.title.toUpperCase()}\n\n${blocks.join('\n\n')}`;
        })
        .join('\n\n');
}

export async function copyShoppingList() {
    // De lijst die in beeld staat kopiëren, dus ook een gedeelde lijst.
    const modal = document.querySelector('.boodschappenpopup');
    const shown = modal && modal.dataset.selection ? decodeSelection(modal.dataset.selection) : getSelection();
    const text = shoppingListAsText(buildShoppingList(shown));
    if (!text) {
        showToast('Je lijst is nog leeg.');
        return;
    }

    try {
        await navigator.clipboard.writeText(text);
        showToast('Lijst gekopieerd!');
    } catch (err) {
        console.error('Kopiëren mislukt:', err);
        showToast('Kopiëren lukte niet.');
    }
}

// ---------- Melding ----------

let toastTimer = null;

// Kleine melding onderin, in plaats van alert() dat de hele pagina blokkeert.
export function showToast(message) {
    let toast = document.querySelector('.smartlist-toast');
    if (!toast) {
        toast = document.createElement('div');
        toast.className = 'smartlist-toast';
        toast.setAttribute('role', 'status');
        toast.setAttribute('aria-live', 'polite');
        document.body.appendChild(toast);
    }

    toast.textContent = message;
    toast.classList.add('zichtbaar');

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('zichtbaar'), 2800);
}
