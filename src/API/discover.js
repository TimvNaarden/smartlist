// Ontdekpagina: wordt zowel door Recepten.html (eten) als Cocktails.html
// (drinken) gebruikt. Het enige verschil zijn de teksten en de database die
// wordt ingelezen; de kaarten, filters, popup en boodschappenknoppen zijn gelijk.

import { schaalIngredienten } from './amounts.js';
import { DRINK, MEAL, getItem, getItems, loadCatalog } from './catalog.js';
import { readJSON, writeJSON } from './storage.js';
import {
    adoptSharedList,
    getFactor,
    setFactor,
    clearChecked,
    clearSelection,
    copyShoppingList,
    decodeSelection,
    getLabel,
    getSelection,
    hideShoppingList,
    isSelected,
    onSelectionChange,
    rememberLabel,
    renderShoppingList,
    selectionCount,
    shareShoppingList,
    shareViaWebShareOrClipboard,
    showToast,
    toggleSelection,
} from './shopping.js';

const PAGES = {
    [MEAL]: {
        savedKey: 'smartlist_saved_recipes',
        itemParam: 'recept',
        listParam: 'recepten',
        one: 'recept',
        many: 'recepten',
        savedTitle: 'Mijn opgeslagen recepten',
        stepsTitle: 'Bereidingswijze',
    },
    [DRINK]: {
        savedKey: 'smartlist_saved_cocktails',
        itemParam: 'cocktail',
        listParam: 'cocktails',
        one: 'cocktail',
        many: 'cocktails',
        savedTitle: 'Mijn opgeslagen cocktails',
        stepsTitle: 'Zo maak je het',
    },
};

let page = null; // configuratie van de actieve pagina
let type = MEAL;
let activeTag = 'all';
let searchTerm = '';
let withTerms = []; // ingrediënten die je in huis hebt
let withoutTerms = []; // ingrediënten die je niet wil
let sharedIds = null; // gevuld zolang een gedeelde lijst wordt bekeken

// ---------- Opslaan ----------

function getSavedIds() {
    const saved = readJSON(page.savedKey, []);
    return Array.isArray(saved) ? saved.map(String) : [];
}

function isSaved(id) {
    return getSavedIds().includes(String(id));
}

function toggleSaved(id) {
    const saved = getSavedIds();
    const key = String(id);
    const index = saved.indexOf(key);

    index === -1 ? saved.push(key) : saved.splice(index, 1);
    writeJSON(page.savedKey, saved);

    refreshSaveButtons(key);
    if (activeTag === 'opgeslagen') applyFilters();
    return index === -1;
}

function bookmarkIcon(saved) {
    return saved ? '<i class="fa-solid fa-bookmark"></i>' : '<i class="fa-regular fa-bookmark"></i>';
}

function refreshSaveButtons(id) {
    const saved = isSaved(id);

    document.querySelectorAll(`.receptcard[data-id="${id}"] .kaartsaveknop`).forEach((button) => {
        button.innerHTML = bookmarkIcon(saved);
        button.classList.toggle('saved', saved);
        button.setAttribute('aria-pressed', String(saved));
    });

    const popup = document.querySelector('.detailpopup');
    if (popup && popup.dataset.currentId === String(id)) {
        const button = popup.querySelector('.detailsaveknop');
        if (button) {
            button.innerHTML = bookmarkIcon(saved);
            button.classList.toggle('saved', saved);
            button.setAttribute('aria-pressed', String(saved));
        }
    }
}

// ---------- Kaarten ----------

function buildCard(item) {
    const card = document.createElement('article');
    card.className = 'receptcard';
    card.dataset.id = item.id;
    card.dataset.tags = item.tags.join(',');
    card.dataset.title = item.title.toLowerCase();
    // Alle ingrediëntnamen op de kaart: daarmee kan het filteren op ingrediënt
    // zonder de catalogus opnieuw te doorlopen.
    card.dataset.ingredients = item.ingredients.map((ingredient) => ingredient.name.toLowerCase()).join('|');

    const image = document.createElement('img');
    image.src = item.image;
    image.alt = item.title;
    image.loading = 'lazy';
    image.decoding = 'async';

    const openButton = document.createElement('button');
    openButton.type = 'button';
    openButton.className = 'kaartopen';
    openButton.innerHTML = `<span class="sr-only">Bekijk ${item.title}</span>`;
    openButton.addEventListener('click', () => openDetail(item.id));

    const saveButton = document.createElement('button');
    saveButton.type = 'button';
    saveButton.className = 'kaartsaveknop';
    saveButton.title = 'Opslaan';
    saveButton.innerHTML = bookmarkIcon(isSaved(item.id));
    saveButton.setAttribute('aria-label', `${item.title} opslaan`);
    saveButton.setAttribute('aria-pressed', String(isSaved(item.id)));
    saveButton.addEventListener('click', (event) => {
        event.stopPropagation();
        const saved = toggleSaved(item.id);
        showToast(saved ? 'Opgeslagen.' : 'Verwijderd uit opgeslagen.');
    });

    const selectLabel = document.createElement('label');
    selectLabel.className = 'kaartselect';
    selectLabel.title = 'Op de boodschappenlijst';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'kaartselectbox';
    checkbox.checked = isSelected(type, item.id);
    checkbox.setAttribute('aria-label', `${item.title} op de boodschappenlijst zetten`);
    checkbox.addEventListener('change', (event) => {
        event.stopPropagation();
        rememberLabel(item);
        toggleSelection(type, item.id, checkbox.checked);
    });

    selectLabel.appendChild(checkbox);

    const content = document.createElement('div');
    content.className = 'receptcontent';

    const facts = document.createElement('div');
    facts.className = 'receptinfo';
    item.facts.slice(0, 3).forEach((fact) => {
        const span = document.createElement('span');
        span.innerHTML = `<i class="${fact.icon}" aria-hidden="true"></i> ${fact.label}`;
        facts.appendChild(span);
    });

    const title = document.createElement('h3');
    title.className = 'recepttitel';
    title.textContent = item.title;

    const match = document.createElement('span');
    match.className = 'kaarttreffers';
    match.hidden = true;

    content.appendChild(facts);
    content.appendChild(title);
    content.appendChild(match);

    card.appendChild(image);
    card.appendChild(openButton);
    card.appendChild(saveButton);
    card.appendChild(selectLabel);
    card.appendChild(content);

    return card;
}

function renderCards(items) {
    const container = document.querySelector('.recepten-grid');
    if (!container) return;

    const fragment = document.createDocumentFragment();
    items.forEach((item) => fragment.appendChild(buildCard(item)));

    container.innerHTML = '';
    container.appendChild(fragment);
}

// ---------- Filteren ----------

// "aubergine, feta" -> ['aubergine', 'feta']
function splitTerms(value) {
    return (value || '')
        .toLowerCase()
        .split(/[,;\n]+/)
        .map((term) => term.trim())
        .filter(Boolean);
}

function countMatches(card, terms) {
    const names = card.dataset.ingredients || '';
    return terms.filter((term) => names.includes(term)).length;
}

function applyFilters() {
    const cards = [...document.querySelectorAll('.receptcard')];
    const savedIds = activeTag === 'opgeslagen' ? getSavedIds() : null;
    let visible = 0;

    cards.forEach((card) => {
        // De zoekbalk kijkt naar de titel én naar de ingrediënten, zodat je op
        // "aubergine" kunt zoeken en niet alleen op een gerechtnaam.
        const matchesSearch = !searchTerm
            || card.dataset.title.includes(searchTerm)
            || (card.dataset.ingredients || '').includes(searchTerm);
        const matchesShared = !sharedIds || sharedIds.includes(card.dataset.id);

        let matchesTag = true;
        if (savedIds) {
            matchesTag = savedIds.includes(card.dataset.id);
        } else if (activeTag !== 'all') {
            matchesTag = card.dataset.tags.split(',').includes(activeTag);
        }

        const treffers = withTerms.length ? countMatches(card, withTerms) : 0;
        const matchesWith = !withTerms.length || treffers > 0;
        const matchesWithout = !withoutTerms.length || countMatches(card, withoutTerms) === 0;

        const show = matchesSearch && matchesTag && matchesShared && matchesWith && matchesWithout;
        card.hidden = !show;
        card.dataset.treffers = String(treffers);

        const badge = card.querySelector('.kaarttreffers');
        if (badge) {
            badge.hidden = !withTerms.length || !show;
            badge.textContent = `${treffers} van je ${withTerms.length} ingrediënten`;
            badge.classList.toggle('compleet', treffers === withTerms.length);
        }

        if (show) visible++;
    });

    sortCards(cards);

    const empty = document.querySelector('.geenresultaten');
    if (empty) {
        empty.hidden = visible > 0;
        if (visible === 0) {
            empty.textContent =
                activeTag === 'opgeslagen' && !searchTerm
                    ? `Je hebt nog geen ${page.many} opgeslagen. Gebruik het bladwijzericoon op een kaart.`
                    : `Geen ${page.many} gevonden. Probeer een andere zoekterm of filter.`;
        }
    }

    const counter = document.querySelector('.resultaataantal');
    if (counter) counter.textContent = `${visible} van ${cards.length}`;
}

// Met een lijstje "wat heb ik in huis" staan de recepten met de meeste treffers
// bovenaan. Zonder dat lijstje blijft de oorspronkelijke volgorde staan.
let originalOrder = null;

function sortCards(cards) {
    const container = document.querySelector('.recepten-grid');
    if (!container) return;
    if (!originalOrder) originalOrder = cards.slice();

    const wanted = withTerms.length
        ? cards.slice().sort((a, b) => Number(b.dataset.treffers || 0) - Number(a.dataset.treffers || 0))
        : originalOrder;

    // Alleen herschikken als de volgorde echt verandert; dat scheelt werk bij
    // meer dan duizend kaarten.
    const current = [...container.children];
    if (current.length === wanted.length && current.every((card, index) => card === wanted[index])) return;

    const fragment = document.createDocumentFragment();
    wanted.forEach((card) => fragment.appendChild(card));
    container.appendChild(fragment);
}

function initFilters() {
    const buttons = document.querySelectorAll('.tagknop');
    const search = document.querySelector('.zoekbalk input');

    buttons.forEach((button) => {
        button.setAttribute('aria-pressed', String(button.classList.contains('active')));
        button.addEventListener('click', () => {
            exitSharedView();
            buttons.forEach((other) => {
                other.classList.remove('active');
                other.setAttribute('aria-pressed', 'false');
            });
            button.classList.add('active');
            button.setAttribute('aria-pressed', 'true');
            activeTag = button.dataset.tag || 'all';
            applyFilters();
        });
    });

    if (search) {
        search.addEventListener('input', () => {
            exitSharedView();
            searchTerm = search.value.trim().toLowerCase();
            applyFilters();
        });
    }

    initIngredientFilters();
}

function initIngredientFilters() {
    const paneel = document.querySelector('.ingredientfilters');
    const knop = document.querySelector('.filterknop');
    const met = document.querySelector('.filter-met');
    const zonder = document.querySelector('.filter-zonder');

    if (knop && paneel) {
        knop.setAttribute('aria-expanded', 'false');
        knop.addEventListener('click', () => {
            const open = paneel.hidden;
            paneel.hidden = !open;
            knop.setAttribute('aria-expanded', String(open));
            knop.classList.toggle('actief', open);
        });
    }

    const bijwerken = () => {
        exitSharedView();
        withTerms = splitTerms(met ? met.value : '');
        withoutTerms = splitTerms(zonder ? zonder.value : '');
        const teller = document.querySelector('.filtertelling');
        if (teller) {
            const aantal = withTerms.length + withoutTerms.length;
            teller.textContent = aantal ? String(aantal) : '';
            teller.hidden = aantal === 0;
        }
        applyFilters();
    };

    [met, zonder].forEach((veld) => veld && veld.addEventListener('input', bijwerken));

    document.querySelectorAll('.filterleegknop').forEach((button) =>
        button.addEventListener('click', () => {
            if (met) met.value = '';
            if (zonder) zonder.value = '';
            bijwerken();
        })
    );
}

// ---------- Gedeelde lijst ----------

function showSharedIds(ids) {
    sharedIds = ids.map(String);
    const banner = document.querySelector('.gedeeldbanner');
    if (banner) banner.hidden = false;
    applyFilters();
}

function exitSharedView() {
    if (!sharedIds) return;
    sharedIds = null;

    const banner = document.querySelector('.gedeeldbanner');
    if (banner) banner.hidden = true;

    const url = new URL(window.location.href);
    url.searchParams.delete(page.listParam);
    window.history.replaceState({}, '', url);
}

// ---------- Detailpopup ----------

function openDetail(id) {
    const item = getItem(type, id);
    const popup = document.querySelector('.detailpopup');
    if (!item || !popup) return;

    popup.dataset.currentId = item.id;

    const image = popup.querySelector('.detailmedia img');
    if (image) {
        image.src = item.image;
        image.alt = item.title;
    }

    const title = popup.querySelector('.detailtitel');
    if (title) title.textContent = item.title;

    const facts = popup.querySelector('.detailfacts');
    if (facts) {
        facts.innerHTML = '';
        item.facts.forEach((fact) => {
            const span = document.createElement('span');
            span.innerHTML = `<i class="${fact.icon}" aria-hidden="true"></i> ${fact.label}`;
            facts.appendChild(span);
        });
    }

    renderIngredients(popup, item);
    renderServings(popup, item);

    const stepsTitle = popup.querySelector('.detailstappentitel');
    if (stepsTitle) stepsTitle.textContent = page.stepsTitle;

    const steps = popup.querySelector('.detailstappen');
    if (steps) {
        steps.innerHTML = '';
        item.steps.forEach((step) => {
            const li = document.createElement('li');
            li.textContent = step;
            steps.appendChild(li);
        });
    }

    const source = popup.querySelector('.detailbron');
    if (source) {
        source.innerHTML = '';
        if (item.video) source.appendChild(externalLink(item.video, 'fa-brands fa-youtube', 'Bekijk de video'));
        if (item.source) source.appendChild(externalLink(item.source, 'fa-solid fa-link', 'Origineel recept'));
        // Recepten uit de Wikibooks Cookbook staan onder CC BY-SA; die licentie
        // vraagt om naamsvermelding bij de tekst en bij de foto.
        if (item.creativeCommons) {
            const licence = document.createElement('p');
            licence.className = 'detaillicentie';
            licence.append('Tekst van Wikibooks Cookbook, ');
            licence.appendChild(externalLink('https://creativecommons.org/licenses/by-sa/4.0/', '', 'CC BY-SA 4.0'));
            if (item.imageSource) {
                licence.append('. Foto: ');
                licence.appendChild(externalLink(item.imageSource, '', 'Wikimedia Commons'));
            }
            licence.append('.');
            source.appendChild(licence);
        }
    }

    const selectButton = popup.querySelector('.detaillijstknop');
    if (selectButton) updateDetailSelectButton(selectButton, item);

    refreshSaveButtons(item.id);

    popup.hidden = false;
    popup.classList.add('open');
    document.body.classList.add('geen-scroll');

    const closeButton = popup.querySelector('.detailsluitknop');
    if (closeButton) closeButton.focus();
}

// ---------- Aantal personen en opschalen ----------

function renderIngredients(popup, item) {
    const list = popup.querySelector('.detailingredienten');
    if (!list) return;

    const factor = getFactor(type, item.id);
    list.innerHTML = '';
    schaalIngredienten(item.ingredients, factor).forEach((ingredient) => {
        const li = document.createElement('li');
        li.textContent = `${ingredient.measure ? `${ingredient.measure} ` : ''}${ingredient.name}`;
        list.appendChild(li);
    });
}

// Het aantal personen staat in de data bij de gerechten waar de bron het noemt.
// Bij de rest weten we het niet, en dan verandert de knop in een vermenigvuldiger:
// een verzonnen getal tonen zou net echt lijken.
function renderServings(popup, item) {
    const balk = popup.querySelector('.detailporties');
    if (!balk) return;

    const factor = getFactor(type, item.id);
    const label = balk.querySelector('.portietekst');
    const uitleg = balk.querySelector('.portieuitleg');

    if (item.servings) {
        const aantal = item.servings * factor;
        const afgerond = Number.isInteger(aantal) ? aantal : Math.round(aantal * 10) / 10;
        label.textContent = `${afgerond} ${item.servingsUnit}`;
        if (uitleg) {
            uitleg.textContent = item.servingsFromSource ? '' : 'schatting';
            uitleg.hidden = item.servingsFromSource;
        }
    } else {
        label.textContent = factor === 1 ? 'zoals in het recept' : `${formatFactor(factor)} het recept`;
        if (uitleg) {
            uitleg.textContent = 'aantal personen onbekend';
            uitleg.hidden = false;
        }
    }

    balk.dataset.factor = String(factor);
    const minder = balk.querySelector('.portiemin');
    if (minder) minder.disabled = factor <= 0.5;
}

function formatFactor(factor) {
    if (factor === 0.5) return 'half';
    return `${Number.isInteger(factor) ? factor : Math.round(factor * 10) / 10}×`;
}

// Eén stap erbij of eraf. Met een bekend aantal personen gaat het per persoon,
// zonder dat aantal in halve en hele keren.
function stepFactor(item, richting) {
    const factor = getFactor(type, item.id);

    if (item.servings) {
        const personen = Math.round(item.servings * factor) + richting;
        const grens = Math.max(1, Math.min(24, personen));
        return grens / item.servings;
    }

    const stappen = [0.5, 1, 2, 3, 4, 6, 8];
    const index = stappen.indexOf(factor);
    const nieuw = index === -1 ? 1 : Math.max(0, Math.min(stappen.length - 1, index + richting));
    return stappen[nieuw];
}

function initServings() {
    const popup = document.querySelector('.detailpopup');
    const balk = popup && popup.querySelector('.detailporties');
    if (!balk) return;

    balk.querySelectorAll('[data-stap]').forEach((button) =>
        button.addEventListener('click', () => {
            const item = getItem(type, popup.dataset.currentId);
            if (!item) return;
            setFactor(type, item.id, stepFactor(item, Number(button.dataset.stap)));
            renderIngredients(popup, item);
            renderServings(popup, item);
        })
    );

    const herstel = balk.querySelector('.portieherstel');
    if (herstel) {
        herstel.addEventListener('click', () => {
            const item = getItem(type, popup.dataset.currentId);
            if (!item) return;
            setFactor(type, item.id, 1);
            renderIngredients(popup, item);
            renderServings(popup, item);
        });
    }
}

function externalLink(href, icon, label) {
    const link = document.createElement('a');
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = label;
    if (icon) {
        const symbol = document.createElement('i');
        symbol.className = icon;
        symbol.setAttribute('aria-hidden', 'true');
        link.prepend(document.createTextNode(' '));
        link.prepend(symbol);
    }
    return link;
}

function updateDetailSelectButton(button, item) {
    const selected = isSelected(type, item.id);
    button.classList.toggle('actief', selected);
    button.innerHTML = selected
        ? '<i class="fa-solid fa-check" aria-hidden="true"></i> Staat op je lijst'
        : '<i class="fa-solid fa-cart-plus" aria-hidden="true"></i> Zet op boodschappenlijst';
}

function closeDetail() {
    const popup = document.querySelector('.detailpopup');
    if (!popup) return;
    popup.classList.remove('open');
    popup.hidden = true;
    document.body.classList.remove('geen-scroll');
}

function initDetailPopup() {
    const popup = document.querySelector('.detailpopup');
    if (!popup) return;

    popup.addEventListener('click', (event) => {
        if (event.target === popup) closeDetail();
    });

    popup.querySelectorAll('.detailsluitknop').forEach((button) => button.addEventListener('click', closeDetail));

    const saveButton = popup.querySelector('.detailsaveknop');
    if (saveButton) {
        saveButton.addEventListener('click', () => {
            const id = popup.dataset.currentId;
            if (!id) return;
            const saved = toggleSaved(id);
            showToast(saved ? 'Opgeslagen.' : 'Verwijderd uit opgeslagen.');
        });
    }

    const shareButton = popup.querySelector('.detailshareknop');
    if (shareButton) {
        shareButton.addEventListener('click', () => shareItem(popup.dataset.currentId));
    }

    const listButton = popup.querySelector('.detaillijstknop');
    if (listButton) {
        listButton.addEventListener('click', () => {
            const item = getItem(type, popup.dataset.currentId);
            if (!item) return;
            rememberLabel(item);
            const selected = toggleSelection(type, item.id);
            updateDetailSelectButton(listButton, item);
            showToast(selected ? `${item.title} staat op je lijst.` : `${item.title} van je lijst gehaald.`);
        });
    }
}

// ---------- Delen ----------

async function shareItem(id) {
    const item = getItem(type, id);
    if (!item) return;

    const url = new URL(window.location.href);
    url.search = `?${page.itemParam}=${item.id}`;

    await shareViaWebShareOrClipboard(
        { title: item.title, text: `Bekijk deze ${page.one}: ${item.title}`, url: url.toString() },
        'Link gekopieerd naar klembord!'
    );
}

async function shareSaved() {
    const savedIds = getSavedIds();
    if (savedIds.length === 0) {
        showToast(`Je hebt nog geen ${page.many} opgeslagen.`);
        return;
    }

    const url = new URL(window.location.href);
    url.search = `?${page.listParam}=${savedIds.join(',')}`;

    await shareViaWebShareOrClipboard(
        { title: page.savedTitle, text: `Bekijk mijn ${savedIds.length} opgeslagen ${page.many} op SmartList`, url: url.toString() },
        'Link gekopieerd naar klembord!'
    );
}

// ---------- Selectiepaneel en boodschappenlijst ----------

function renderSelectionPanel() {
    const selection = getSelection();
    const total = selectionCount(selection);

    const badge = document.querySelector('.selectiebadge');
    if (badge) {
        badge.textContent = total;
        badge.hidden = total === 0;
    }

    const list = document.querySelector('.selectielijst');
    if (!list) return;

    list.innerHTML = '';

    if (total === 0) {
        const empty = document.createElement('li');
        empty.className = 'selectieleeg';
        empty.textContent = 'Nog niets geselecteerd. Vink een kaart aan om te beginnen.';
        list.appendChild(empty);
        return;
    }

    // Eten en drinken blijven ook hier van elkaar gescheiden.
    [
        { type: MEAL, title: 'Gerechten', icon: 'fa-solid fa-utensils' },
        { type: DRINK, title: 'Drankjes', icon: 'fa-solid fa-martini-glass-citrus' },
    ].forEach((group) => {
        const ids = selection[group.type];
        if (ids.length === 0) return;

        const heading = document.createElement('li');
        heading.className = 'selectiekop';
        heading.innerHTML = `<i class="${group.icon}" aria-hidden="true"></i> ${group.title} (${ids.length})`;
        list.appendChild(heading);

        ids.forEach((id) => {
            const li = document.createElement('li');
            li.className = 'selectieitem';

            const name = document.createElement('span');
            name.textContent = getLabel(group.type, id);

            const remove = document.createElement('button');
            remove.type = 'button';
            remove.title = 'Van de lijst halen';
            remove.setAttribute('aria-label', `${name.textContent} van de lijst halen`);
            remove.innerHTML = '<i class="fa-solid fa-xmark" aria-hidden="true"></i>';
            remove.addEventListener('click', () => toggleSelection(group.type, id, false));

            li.appendChild(name);
            li.appendChild(remove);
            list.appendChild(li);
        });
    });
}

function initSelectionPanel() {
    const dropdown = document.querySelector('.selectiedropdown');
    const button = document.querySelector('.selectieknop');
    if (!dropdown || !button) return;

    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', (event) => {
        event.stopPropagation();
        const open = dropdown.classList.toggle('open');
        button.setAttribute('aria-expanded', String(open));
    });

    // Sluiten bij een klik buiten het paneel; anders blijft het openstaan.
    document.addEventListener('click', (event) => {
        if (!dropdown.contains(event.target)) {
            dropdown.classList.remove('open');
            button.setAttribute('aria-expanded', 'false');
        }
    });
}

function initShoppingList() {
    document.querySelectorAll('.lijstknop').forEach((button) =>
        button.addEventListener('click', () => {
            renderShoppingList();
        })
    );

    const popup = document.querySelector('.boodschappenpopup');
    if (!popup) return;

    popup.addEventListener('click', (event) => {
        if (event.target === popup) hideShoppingList();
    });

    popup.querySelectorAll('.detailsluitknop').forEach((button) => button.addEventListener('click', hideShoppingList));

    const shareButton = popup.querySelector('.boodschappendeelknop');
    if (shareButton) shareButton.addEventListener('click', shareShoppingList);

    const copyButton = popup.querySelector('.boodschappenkopieerknop');
    if (copyButton) copyButton.addEventListener('click', copyShoppingList);

    const resetButton = popup.querySelector('.boodschappenresetknop');
    if (resetButton) {
        resetButton.addEventListener('click', () => {
            clearChecked();
            clearSelection();
            renderShoppingList();
            showToast('Lijst leeggemaakt.');
        });
    }

    const adoptButton = popup.querySelector('.boodschappenovernemenknop');
    if (adoptButton) {
        adoptButton.addEventListener('click', () => {
            const selection = adoptSharedList();

            const url = new URL(window.location.href);
            url.searchParams.delete('boodschappen');
            window.history.replaceState({}, '', url);

            renderShoppingList(selection);
            showToast('De gedeelde lijst staat nu in je eigen lijst.');
        });
    }
}

// ---------- Opstarten ----------

export async function initDiscoverPage(options) {
    type = options.type;
    page = PAGES[type];

    initFilters();
    initDetailPopup();
    initServings();
    initSelectionPanel();
    initShoppingList();

    document.querySelectorAll('.deelknop-opgeslagen').forEach((button) => button.addEventListener('click', shareSaved));

    document.querySelectorAll('.gedeeldsluiten').forEach((button) =>
        button.addEventListener('click', () => {
            exitSharedView();
            applyFilters();
        })
    );

    document.addEventListener('keydown', (event) => {
        if (event.key !== 'Escape') return;
        closeDetail();
        hideShoppingList();
    });

    onSelectionChange(() => {
        renderSelectionPanel();
        syncSelectBoxes();
    });

    const grid = document.querySelector('.recepten-grid');
    if (grid) grid.setAttribute('aria-busy', 'true');

    try {
        await loadCatalog(type);
    } catch (err) {
        console.error('Kon de database niet laden:', err);
        const empty = document.querySelector('.geenresultaten');
        if (empty) {
            empty.hidden = false;
            empty.textContent = `De ${page.many} konden niet worden geladen. Probeer de pagina te herladen.`;
        }
    }

    renderCards(getItems(type));
    if (grid) grid.removeAttribute('aria-busy');

    renderSelectionPanel();
    applyFilters();
    handleDeepLink();
}

function syncSelectBoxes() {
    const selection = getSelection()[type];
    document.querySelectorAll('.receptcard').forEach((card) => {
        const checkbox = card.querySelector('.kaartselectbox');
        if (checkbox) checkbox.checked = selection.includes(card.dataset.id);
    });
}

// Links die iemand heeft gedeeld: één item, een lijst met opgeslagen items, of
// een complete boodschappenlijst met eten én drinken.
function handleDeepLink() {
    const params = new URLSearchParams(window.location.search);

    const itemId = params.get(page.itemParam);
    if (itemId && getItem(type, itemId)) {
        openDetail(itemId);
        return;
    }

    const listIds = params.get(page.listParam);
    if (listIds) {
        showSharedIds(listIds.split(',').filter(Boolean));
        return;
    }

    const shopping = params.get('boodschappen');
    if (shopping) {
        renderShoppingList(decodeSelection(shopping), { shared: true });
    }
}
