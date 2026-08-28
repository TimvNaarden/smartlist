// Ontdekpagina: wordt zowel door Recepten.html (eten) als Cocktails.html
// (drinken) gebruikt. Het enige verschil zijn de teksten en de database die
// wordt ingelezen; de kaarten, filters, popup en boodschappenknoppen zijn gelijk.

import { DRINK, MEAL, getItem, getItems, loadCatalog } from './catalog.js';
import { readJSON, writeJSON } from './storage.js';
import {
    adoptSharedList,
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
    item.facts.slice(0, 2).forEach((fact) => {
        const span = document.createElement('span');
        span.innerHTML = `<i class="${fact.icon}" aria-hidden="true"></i> ${fact.label}`;
        facts.appendChild(span);
    });

    const title = document.createElement('h3');
    title.className = 'recepttitel';
    title.textContent = item.title;

    content.appendChild(facts);
    content.appendChild(title);

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

function applyFilters() {
    const cards = document.querySelectorAll('.receptcard');
    const savedIds = activeTag === 'opgeslagen' ? getSavedIds() : null;
    let visible = 0;

    cards.forEach((card) => {
        const matchesSearch = !searchTerm || card.dataset.title.includes(searchTerm);
        const matchesShared = !sharedIds || sharedIds.includes(card.dataset.id);

        let matchesTag = true;
        if (savedIds) {
            matchesTag = savedIds.includes(card.dataset.id);
        } else if (activeTag !== 'all') {
            matchesTag = card.dataset.tags.split(',').includes(activeTag);
        }

        const show = matchesSearch && matchesTag && matchesShared;
        card.hidden = !show;
        if (show) visible++;
    });

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

    const ingredients = popup.querySelector('.detailingredienten');
    if (ingredients) {
        ingredients.innerHTML = '';
        item.ingredients.forEach((ingredient) => {
            const li = document.createElement('li');
            li.textContent = `${ingredient.measure ? `${ingredient.measure} ` : ''}${ingredient.name}`;
            ingredients.appendChild(li);
        });
    }

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

function externalLink(href, icon, label) {
    const link = document.createElement('a');
    link.href = href;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.innerHTML = `<i class="${icon}" aria-hidden="true"></i> ${label}`;
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
