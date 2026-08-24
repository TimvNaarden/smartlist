import { AHConnector } from './AH_API.js';
const addedMeals = new Set(); // om dubbele recepten te voorkomen
const mealsById = {}; // hier slaan we alle volledige recepten op

// word door Recepten.html aangeroepen: loadRandomRecipes(20)
async function loadRandomRecipes(count = 10) {
    const ah = new AHConnector();
    await ah.init();

    const url = 'https://www.themealdb.com/api/json/v1/1/random.php';
    const bonusProducts = await ah.GetBonusProducts();
    const bonusList = parseBonusProducts(bonusProducts);
    for (let i = 0; i < count; i++) {
        try {
            const response = await fetch(url);
            const data = await response.json();
            if (!data.meals || !data.meals[0]) {
                continue;
            }

            const meal = data.meals[0];

            // sla over als we deze al hebben
            if (addedMeals.has(meal.idMeal)) {
                i--;
                continue;
            }

            addRecipe(meal, bonusList);
        } catch (err) {
            console.error('Failed to load random recipe:', err);
        }
    }
}

// maak tags om te filteren
function buildTags(meal, isBonus) {
    const tags = [];

    if (meal.strCategory) {
        tags.push(meal.strCategory.toLowerCase());
    }
    if (meal.strArea) {
        tags.push(meal.strArea.toLowerCase());
    }
    if (meal.strTags) {
        meal.strTags.split(',').forEach(function (tag) {
            const t = tag.trim().toLowerCase();
            if (t) {
                tags.push(t);
            }
        });
    }
    if (isBonus) {
        tags.push('bonus');
    }

    return tags;
}

function getMealIngredients(meal) {
    const ingredients = [];

    for (let i = 1; i <= 20; i++) {
        const value = meal[`strIngredient${i}`];
        if (value && value.trim()) {
            ingredients.push(value.toLowerCase().trim());
        }
    }

    return ingredients;
}
function parseBonusProducts(rawBonusProducts) {
    const result = [];

    rawBonusProducts.flat().forEach(item => {
        const parsed = JSON.parse(item);
        result.push({
            ...parsed,
            normalizedName: normalizeName(parsed.name.toLowerCase())
        });
    });

    return result;
}
function findBonusMatches(meal, bonusList) {
    const mealIngredients = getMealIngredients(meal);
    const matches = [];

    bonusList.forEach(bonus => {
        for (const [dutch, mealdb] of Object.entries(productTranslations)) {
            if (
                bonus.normalizedName.includes(dutch) &&
                mealIngredients.includes(mealdb)
            ) {
                matches.push(bonus);
                break; // prevent duplicate match of same bonus item
            }
        }
    });

    return matches;
}
// wordt gebruikt door loadRandomRecipes én door je AH bonus script
function addRecipe(meal, bonusList) {
    const container = document.querySelector('.recepten-grid');
    if (!container) return;

    const bonusMatches = findBonusMatches(meal, bonusList);
    const isBonus = bonusMatches.length > 0 && bonusMatches[0].name !== '';

    if (isBonus && bonusMatches.length === 0) {
    console.warn('BONUS WITHOUT PRODUCTS', {
        meal: meal.strMeal,
        ingredients: getMealIngredients(meal)
    });
}

    // recept opslaan voor de popup
    mealsById[meal.idMeal] = {
        ...meal,
        bonusProducts: bonusMatches  
    };
    addedMeals.add(meal.idMeal);

    const title = meal.strMeal || 'Geen titel';
    const image = meal.strMealThumb || '';

    const tags = buildTags(meal, isBonus);

    const card = document.createElement('article');
    card.className = 'receptcard';
    card.dataset.tags = tags.join(',');
    card.dataset.id = meal.idMeal;

    // klik op kaart opent popup met juiste info
    card.addEventListener('click', function () {
        showReceptInfo(meal.idMeal);
    });

    const img = document.createElement('img');
    img.src = image;
    img.alt = title;

    const content = document.createElement('div');
    content.className = 'receptcontent';

    const info = document.createElement('div');
    info.className = 'receptinfo';

    const infoInner = document.createElement('div');
    infoInner.style.display = 'block';
    infoInner.style.marginLeft = '0.5rem';
    infoInner.style.marginBottom = '0.5rem';

    const spanCategory = document.createElement('span');
    spanCategory.innerHTML = '<i class="fa-solid fa-leaf"></i> ' + (meal.strCategory || '');

    const spanArea = document.createElement('span');
    spanArea.innerHTML = '<i class="fa-solid fa-earth-europe"></i> ' + (meal.strArea || '');

    const titleEl = document.createElement('h3');
    titleEl.className = 'recepttitel';
    titleEl.textContent = title;

    if(isBonus){
        const bonusDiv = document.createElement('div');
        bonusDiv.className = 'receptbonus';

        infoInner.appendChild(bonusDiv);
    }

    infoInner.appendChild(spanCategory);
    infoInner.appendChild(spanArea);
    infoInner.appendChild(titleEl);

    info.appendChild(infoInner);
    content.appendChild(info);

    card.appendChild(img);
    card.appendChild(content);


    container.appendChild(card);
}

// popup vullen en openen
function showReceptInfo(mealId) {
    const meal = mealsById[mealId];
    if (!meal) {
        console.error('Meal not found for popup:', mealId);
        return;
    }

    const modal = document.querySelector('.receptpopup');
    if (!modal) return;

    const img = modal.querySelector('.receptpopupimg img');
    const titleEl = modal.querySelector('.receptpopuptitel');
    const ingList = modal.querySelector('.receptpopupingr');
    const stepsList = modal.querySelector('.receptbereid');
    const bonus = modal.querySelector('.receptbonus');
    bonus.innerHTML = '';
    if (bonus && meal.bonusProducts && meal.bonusProducts.length > 0) {
        bonus.appendChild(document.createTextNode('Bonusproducten:\r\n'));
        bonus.appendChild(document.createElement('br'));
        for(let bonusProduct of meal.bonusProducts) {
             bonus.appendChild(document.createTextNode(bonusProduct.name + ': ' + bonusProduct.bonusMechanism.toLowerCase() + '\r\n'));
             bonus.appendChild(document.createElement('br'));
        }
    }


    // afbeelding en titel
    if (img) {
        img.src = meal.strMealThumb || '';
        img.alt = meal.strMeal || '';
    }
    if (titleEl) {
        titleEl.textContent = meal.strMeal || '';
    }

    // ingrediënten lijst
    if (ingList) {
        ingList.innerHTML = '';
        for (let i = 1; i <= 20; i++) {
            const ing = meal['strIngredient' + i];
            const measure = meal['strMeasure' + i];
            if (ing && ing.trim()) {
                const li = document.createElement('li');
                const text = ((measure || '').trim() + ' ' + ing.trim()).trim();
                li.textContent = text;
                ingList.appendChild(li);
            }
        }
    }

    // bereidingswijze
    if (stepsList) {
        stepsList.innerHTML = '';
        if (meal.strInstructions) {
            const lines = meal.strInstructions
                .split(/\r?\n/)
                .map(function (line) {
                    return line.trim();
                })
                .filter(function (line) {
                    return line.length > 0;
                });

            if (lines.length === 0) {
                const li = document.createElement('li');
                li.textContent = meal.strInstructions;
                stepsList.appendChild(li);
            } else {
                lines.forEach(function (line) {
                    if(line.toLowerCase().includes('step')) return;
                    for(let i = 1; i <= 20; i++) {
                        if(line.startsWith(i + '.')) {
                            line = line.substring((i + '.').length).trim();
                        }
                        else if(line == i.toString()) {
                            return;
                        }
                    }
                    const li = document.createElement('li');
                    li.textContent = line;
                    stepsList.appendChild(li);
                });
            }
        }
    }

    modal.classList.add('open');
    document.body.style.overflow = 'hidden';
}

// popup sluiten, wordt in je HTML gebruikt bij de X-knop
function hideReceptInfo() {
    const modal = document.querySelector('.receptpopup');
    if (!modal) return;
    modal.classList.remove('open');
    document.body.style.overflow = '';
}

// functies ook expliciet op window zetten (zeker dat HTML en module script ze zien)
window.loadRandomRecipes = loadRandomRecipes;
window.addRecipe = addRecipe;
window.showReceptInfo = showReceptInfo;
window.hideReceptInfo = hideReceptInfo;
window.addedMeals = addedMeals;

// Sluiten wanneer naast pop up wordt geklikt
const popup = document.querySelector('.receptpopup');

if (popup) {
    popup.addEventListener('click', function (e) {
        if (e.target === popup) {
            hideReceptInfo();
        }
    });
}
