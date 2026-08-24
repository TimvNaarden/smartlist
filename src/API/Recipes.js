import { AHConnector } from "./AH_API.js";

const addedMeals = new Set(); // om dubbele recepten te voorkomen
const mealsById = {}; // hier slaan we alle volledige recepten op
const SAVED_KEY = "smartlist_saved_recipes";
const SHOPPING_CHECKED_KEY = "smartlist_shopping_checked";

let isSharedView = false;
let shoppingSelection = new Set();

// word door Recepten.html aangeroepen: loadRandomRecipes(50)
async function loadRandomRecipes(count = 10) {
  const ah = new AHConnector();
  await ah.init();

  const url = "https://www.themealdb.com/api/json/v1/1/random.php";
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

      if (addedMeals.has(meal.idMeal)) {
        i--;
        continue;
      }

      addRecipe(meal, bonusList);
    } catch (err) {
      console.error("Failed to load random recipe:", err);
    }
  }
}

// laadt alle vooraf gedownloade recepten uit API/recipes.json
async function loadAllRecipes() {
  const ah = new AHConnector();
  await ah.init();

  const bonusList = [];

  try {
    const response = await fetch("./API/recipes.json");
    if (!response.ok) {
      console.error("Failed to load recipes.json:", response.status);
      return;
    }
    const meals = await response.json();

    for (const meal of meals) {
      if (addedMeals.has(meal.idMeal)) continue;
      addRecipe(meal, bonusList);
    }
  } catch (err) {
    console.error("Failed to load all recipes:", err);
  }
}

function buildTags(meal, isBonus) {
  const tags = [];

  if (meal.strCategory) {
    tags.push(meal.strCategory.toLowerCase());
  }
  if (meal.strArea) {
    tags.push(meal.strArea.toLowerCase());
  }
  if (meal.strTags) {
    meal.strTags.split(",").forEach(function (tag) {
      const t = tag.trim().toLowerCase();
      if (t) {
        tags.push(t);
      }
    });
  }
  if (isBonus) {
    tags.push("bonus");
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

  rawBonusProducts.flat().forEach((item) => {
    const parsed = JSON.parse(item);
    result.push({
      ...parsed,
      normalizedName: normalizeName(parsed.name.toLowerCase()),
    });
  });

  return result;
}

function findBonusMatches(meal, bonusList) {
  const mealIngredients = getMealIngredients(meal);
  const matches = [];

  bonusList.forEach((bonus) => {
    for (const [dutch, mealdb] of Object.entries(productTranslations)) {
      if (
        bonus.normalizedName.includes(dutch) &&
        mealIngredients.includes(mealdb)
      ) {
        matches.push(bonus);
        break;
      }
    }
  });

  return matches;
}

// wordt gebruikt door loadRandomRecipes, loadAllRecipes én je AH bonus script
function addRecipe(meal, bonusList) {
  const container = document.querySelector(".recepten-grid");
  if (!container) return;

  const bonusMatches = findBonusMatches(meal, bonusList);
  const isBonus = bonusMatches.length > 0 && bonusMatches[0].name !== "";

  if (isBonus && bonusMatches.length === 0) {
    console.warn("BONUS WITHOUT PRODUCTS", {
      meal: meal.strMeal,
      ingredients: getMealIngredients(meal),
    });
  }

  mealsById[meal.idMeal] = {
    ...meal,
    bonusProducts: bonusMatches,
  };
  addedMeals.add(meal.idMeal);

  const title = meal.strMeal || "Geen titel";
  const image = meal.strMealThumb || "";

  const tags = buildTags(meal, isBonus);

  const card = document.createElement("article");
  card.className = "receptcard";
  card.dataset.tags = tags.join(",");
  card.dataset.id = meal.idMeal;

  card.addEventListener("click", function () {
    showReceptInfo(meal.idMeal);
  });

  const img = document.createElement("img");
  img.src = image;
  img.alt = title;

  const content = document.createElement("div");
  content.className = "receptcontent";

  const info = document.createElement("div");
  info.className = "receptinfo";

  const infoInner = document.createElement("div");
  infoInner.style.display = "block";
  infoInner.style.marginLeft = "0.5rem";
  infoInner.style.marginBottom = "0.5rem";

  const spanCategory = document.createElement("span");
  spanCategory.innerHTML =
    '<i class="fa-solid fa-leaf"></i> ' + (meal.strCategory || "");

  const spanArea = document.createElement("span");
  spanArea.innerHTML =
    '<i class="fa-solid fa-earth-europe"></i> ' + (meal.strArea || "");

  const titleEl = document.createElement("h3");
  titleEl.className = "recepttitel";
  titleEl.textContent = title;

  if (isBonus) {
    const bonusDiv = document.createElement("div");
    bonusDiv.className = "receptbonus";

    infoInner.appendChild(bonusDiv);
  }

  infoInner.appendChild(spanCategory);
  infoInner.appendChild(spanArea);
  infoInner.appendChild(titleEl);

  info.appendChild(infoInner);
  content.appendChild(info);

  // knop om recept snel op te slaan zonder de popup te openen
  const quickSaveBtn = document.createElement("button");
  quickSaveBtn.type = "button";
  quickSaveBtn.className = "receptcard-saveknop";
  quickSaveBtn.title = "Opslaan";
  quickSaveBtn.innerHTML = isRecipeSaved(meal.idMeal)
    ? '<i class="fa-solid fa-bookmark"></i>'
    : '<i class="fa-regular fa-bookmark"></i>';
  quickSaveBtn.addEventListener("click", function (e) {
    e.stopPropagation();
    toggleSaveRecipe(meal.idMeal);
    quickSaveBtn.innerHTML = isRecipeSaved(meal.idMeal)
      ? '<i class="fa-solid fa-bookmark"></i>'
      : '<i class="fa-regular fa-bookmark"></i>';
  });

  // checkbox om recept te selecteren voor de boodschappenlijst
  const selectBox = document.createElement("input");
  selectBox.type = "checkbox";
  selectBox.className = "receptselectbox";
  selectBox.title = "Selecteer voor boodschappenlijst";
  selectBox.addEventListener("click", function (e) {
    e.stopPropagation();
    toggleShoppingSelection(meal.idMeal, selectBox.checked);
  });

  card.appendChild(img);
  card.appendChild(quickSaveBtn);
  card.appendChild(selectBox);
  card.appendChild(content);

  container.appendChild(card);
}

// popup vullen en openen
function showReceptInfo(mealId) {
  const meal = mealsById[mealId];
  if (!meal) {
    console.error("Meal not found for popup:", mealId);
    return;
  }

  const modal = document.querySelector(".receptpopup");
  if (!modal) return;

  modal.dataset.currentId = mealId;
  updateSaveButtonState(mealId);

  const img = modal.querySelector(".receptpopupimg img");
  const titleEl = modal.querySelector(".receptpopuptitel");
  const ingList = modal.querySelector(".receptpopupingr");
  const stepsList = modal.querySelector(".receptbereid");
  const bonus = modal.querySelector(".receptbonus");
  bonus.innerHTML = "";
  if (bonus && meal.bonusProducts && meal.bonusProducts.length > 0) {
    bonus.appendChild(document.createTextNode("Bonusproducten:\r\n"));
    bonus.appendChild(document.createElement("br"));
    for (let bonusProduct of meal.bonusProducts) {
      bonus.appendChild(
        document.createTextNode(
          bonusProduct.name +
            ": " +
            bonusProduct.bonusMechanism.toLowerCase() +
            "\r\n",
        ),
      );
      bonus.appendChild(document.createElement("br"));
    }
  }

  if (img) {
    img.src = meal.strMealThumb || "";
    img.alt = meal.strMeal || "";
  }
  if (titleEl) {
    titleEl.textContent = meal.strMeal || "";
  }

  if (ingList) {
    ingList.innerHTML = "";
    for (let i = 1; i <= 20; i++) {
      const ing = meal["strIngredient" + i];
      const measure = meal["strMeasure" + i];
      if (ing && ing.trim()) {
        const li = document.createElement("li");
        const text = ((measure || "").trim() + " " + ing.trim()).trim();
        li.textContent = text;
        ingList.appendChild(li);
      }
    }
  }

  if (stepsList) {
    stepsList.innerHTML = "";
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
        const li = document.createElement("li");
        li.textContent = meal.strInstructions;
        stepsList.appendChild(li);
      } else {
        lines.forEach(function (line) {
          if (line.toLowerCase().includes("step")) return;
          for (let i = 1; i <= 20; i++) {
            if (line.startsWith(i + ".")) {
              line = line.substring((i + ".").length).trim();
            } else if (line == i.toString()) {
              return;
            }
          }
          const li = document.createElement("li");
          li.textContent = line;
          stepsList.appendChild(li);
        });
      }
    }
  }

  modal.classList.add("open");
  document.body.style.overflow = "hidden";
}

function hideReceptInfo() {
  const modal = document.querySelector(".receptpopup");
  if (!modal) return;
  modal.classList.remove("open");
  document.body.style.overflow = "";
}

// ---------- Opslaan (favorieten) ----------

function getSavedRecipeIds() {
  const raw = localStorage.getItem(SAVED_KEY);
  try {
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function isRecipeSaved(mealId) {
  return getSavedRecipeIds().includes(mealId);
}

function saveRecipe(mealId) {
  const saved = getSavedRecipeIds();
  if (!saved.includes(mealId)) {
    saved.push(mealId);
    localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
  }
  updateSaveButtonState(mealId);
}

function unsaveRecipe(mealId) {
  const saved = getSavedRecipeIds().filter((id) => id !== mealId);
  localStorage.setItem(SAVED_KEY, JSON.stringify(saved));
  updateSaveButtonState(mealId);
}

function toggleSaveRecipe(mealId) {
  isRecipeSaved(mealId) ? unsaveRecipe(mealId) : saveRecipe(mealId);
}

function updateSaveButtonState(mealId) {
  const btn = document.querySelector(".receptsaveknop");
  if (!btn) return;
  const saved = isRecipeSaved(mealId);
  btn.classList.toggle("saved", saved);
  btn.innerHTML = saved
    ? '<i class="fa-solid fa-bookmark"></i>'
    : '<i class="fa-regular fa-bookmark"></i>';
}

// rendert alle opgeslagen recepten die al in mealsById staan
function loadSavedRecipes() {
  const container = document.querySelector(".recepten-grid");
  if (!container) return;
  container.innerHTML = "";
  addedMeals.clear();

  const savedIds = getSavedRecipeIds();
  savedIds.forEach((id) => {
    const meal = mealsById[id];
    if (meal) {
      addRecipe(meal, meal.bonusProducts || []);
    }
  });
}

// ---------- Delen ----------

async function shareViaWebShareOrClipboard(shareData, fallbackMessage) {
  if (navigator.share) {
    try {
      await navigator.share(shareData);
    } catch (err) {
      if (err.name !== "AbortError") {
        console.error("Delen mislukt:", err);
      }
    }
  } else {
    try {
      await navigator.clipboard.writeText(shareData.url);
      alert(fallbackMessage);
    } catch (err) {
      console.error("Kopiëren mislukt:", err);
    }
  }
}

async function shareRecipe(mealId) {
  const meal = mealsById[mealId];
  if (!meal) return;

  const shareUrl = `${window.location.origin}${window.location.pathname}?recept=${mealId}`;
  await shareViaWebShareOrClipboard(
    {
      title: meal.strMeal,
      text: `Bekijk dit recept: ${meal.strMeal}`,
      url: shareUrl,
    },
    "Link gekopieerd naar klembord!",
  );
}

async function shareAllSavedRecipes() {
  const savedIds = getSavedRecipeIds();
  if (savedIds.length === 0) {
    alert("Je hebt nog geen recepten opgeslagen.");
    return;
  }

  const shareUrl = `${window.location.origin}${window.location.pathname}?recepten=${savedIds.join(",")}`;
  await shareViaWebShareOrClipboard(
    {
      title: "Mijn opgeslagen recepten",
      text: `Bekijk mijn ${savedIds.length} opgeslagen recepten op SmartList`,
      url: shareUrl,
    },
    "Link gekopieerd naar klembord!",
  );
}

function showRecipesByIds(ids) {
  isSharedView = true;
  document.querySelectorAll(".receptcard").forEach((card) => {
    card.style.display = ids.includes(card.dataset.id) ? "block" : "none";
  });
  toggleSharedBanner(true);
}

function exitSharedView() {
  if (!isSharedView) return;
  isSharedView = false;

  document.querySelectorAll(".receptcard").forEach((card) => {
    card.style.display = "block";
  });

  const url = new URL(window.location.href);
  url.searchParams.delete("recepten");
  window.history.replaceState({}, "", url);
  toggleSharedBanner(false);
}

function toggleSharedBanner(show) {
  const banner = document.querySelector(".gedeeldbanner");
  if (banner) banner.style.display = show ? "flex" : "none";
}

// ---------- Boodschappenlijst ----------

function toggleShoppingSelection(mealId, isSelected) {
  isSelected ? shoppingSelection.add(mealId) : shoppingSelection.delete(mealId);
  updateShoppingSelectionUI();
}

function buildShoppingList(mealIds) {
  const itemsMap = {};

  mealIds.forEach((id) => {
    const meal = mealsById[id];
    if (!meal) return;

    for (let i = 1; i <= 20; i++) {
      const ing = meal[`strIngredient${i}`];
      const measure = meal[`strMeasure${i}`];
      if (!ing || !ing.trim()) continue;

      const key = ing.trim().toLowerCase();
      if (!itemsMap[key]) {
        itemsMap[key] = { name: ing.trim(), measures: [], recipes: [] };
      }
      if (measure && measure.trim())
        itemsMap[key].measures.push(measure.trim());
      itemsMap[key].recipes.push(meal.strMeal);
    }
  });

  return Object.values(itemsMap).sort((a, b) => a.name.localeCompare(b.name));
}

function getCheckedItems() {
  const raw = localStorage.getItem(SHOPPING_CHECKED_KEY);
  try {
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function setItemChecked(itemName, checked) {
  const checkedMap = getCheckedItems();
  checkedMap[itemName] = checked;
  localStorage.setItem(SHOPPING_CHECKED_KEY, JSON.stringify(checkedMap));
}

function renderShoppingList(mealIds) {
  const modal = document.querySelector(".boodschappenpopup");
  const list = modal ? modal.querySelector(".boodschappenlijst") : null;
  if (!modal || !list) return;

  if (!mealIds || mealIds.length === 0) {
    alert("Selecteer eerst een of meer recepten.");
    return;
  }

  list.innerHTML = "";
  const items = buildShoppingList(mealIds);
  const checkedMap = getCheckedItems();

  items.forEach((item) => {
    const li = document.createElement("li");
    li.className = "boodschapitem";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = !!checkedMap[item.name];
    checkbox.addEventListener("change", () => {
      setItemChecked(item.name, checkbox.checked);
      li.classList.toggle("afgevinkt", checkbox.checked);
    });

    const label = document.createElement("span");
    const measureText = item.measures.length
      ? item.measures.join(" + ") + " "
      : "";
    label.textContent = `${measureText}${item.name}`;

    const recipesUsed = document.createElement("small");
    recipesUsed.textContent =
      " (" + [...new Set(item.recipes)].join(", ") + ")";

    li.classList.toggle("afgevinkt", checkbox.checked);
    li.appendChild(checkbox);
    li.appendChild(label);
    li.appendChild(recipesUsed);
    list.appendChild(li);
  });

  modal.dataset.mealIds = mealIds.join(",");
  modal.classList.add("open");
  document.body.style.overflow = "hidden";
}

function hideShoppingList() {
  const modal = document.querySelector(".boodschappenpopup");
  if (!modal) return;
  modal.classList.remove("open");
  document.body.style.overflow = "";
}

async function shareShoppingList() {
  const modal = document.querySelector(".boodschappenpopup");
  const mealIds = modal ? modal.dataset.mealIds : null;
  if (!mealIds) return;

  const shareUrl = `${window.location.origin}${window.location.pathname}?boodschappen=${mealIds}`;
  await shareViaWebShareOrClipboard(
    {
      title: "Mijn boodschappenlijst",
      text: "Bekijk mijn boodschappenlijst op SmartList",
      url: shareUrl,
    },
    "Link gekopieerd naar klembord!",
  );
}

function removeFromShoppingSelection(mealId) {
  shoppingSelection.delete(mealId);

  const card = document.querySelector(`.receptcard[data-id="${mealId}"]`);
  if (card) {
    const checkbox = card.querySelector(".receptselectbox");
    if (checkbox) checkbox.checked = false;
  }
  updateShoppingSelectionUI();
}

function updateShoppingSelectionUI() {
  const badge = document.querySelector(".selectiebadge");
  const list = document.querySelector(".selectielijst");
  const count = shoppingSelection.size;

  if (badge) {
    badge.textContent = count;
    badge.style.display = count > 0 ? "inline-flex" : "none";
  }

  if (list) {
    list.innerHTML = "";
    if (count === 0) {
      list.innerHTML =
        '<li class="selectieleeg">Nog geen recepten geselecteerd</li>';
      return;
    }
    [...shoppingSelection].forEach((id) => {
      const meal = mealsById[id];
      if (!meal) return;

      const li = document.createElement("li");
      li.className = "selectieitem";

      const naam = document.createElement("span");
      naam.textContent = meal.strMeal;

      const verwijderBtn = document.createElement("button");
      verwijderBtn.type = "button";
      verwijderBtn.title = "Verwijderen";
      verwijderBtn.innerHTML = '<i class="fa-solid fa-xmark"></i>';
      verwijderBtn.addEventListener("click", () =>
        removeFromShoppingSelection(id),
      );

      li.appendChild(naam);
      li.appendChild(verwijderBtn);
      list.appendChild(li);
    });
  }
}

function toggleSelectieDropdown() {
  const dropdown = document.querySelector(".selectiedropdown");
  if (dropdown) dropdown.classList.toggle("open");
}

// functies ook expliciet op window zetten (zeker dat HTML en module script ze zien)
window.loadRandomRecipes = loadRandomRecipes;
window.loadAllRecipes = loadAllRecipes;
window.loadSavedRecipes = loadSavedRecipes;
window.addRecipe = addRecipe;
window.showReceptInfo = showReceptInfo;
window.hideReceptInfo = hideReceptInfo;
window.addedMeals = addedMeals;
window.mealsById = mealsById;

window.toggleSaveRecipe = toggleSaveRecipe;
window.isRecipeSaved = isRecipeSaved;
window.shareRecipe = shareRecipe;
window.shareAllSavedRecipes = shareAllSavedRecipes;
window.showRecipesByIds = showRecipesByIds;
window.exitSharedView = exitSharedView;
window.isSharedView = () => isSharedView;

window.toggleShoppingSelection = toggleShoppingSelection;
window.renderShoppingList = renderShoppingList;
window.hideShoppingList = hideShoppingList;
window.shareShoppingList = shareShoppingList;

window.getShoppingSelection = () => [...shoppingSelection];
window.removeFromShoppingSelection = removeFromShoppingSelection;
window.updateShoppingSelectionUI = updateShoppingSelectionUI;
window.toggleSelectieDropdown = toggleSelectieDropdown;

// Sluiten wanneer naast pop up wordt geklikt
const popup = document.querySelector(".receptpopup");
if (popup) {
  popup.addEventListener("click", function (e) {
    if (e.target === popup) {
      hideReceptInfo();
    }
  });
}

const shoppingPopup = document.querySelector(".boodschappenpopup");
if (shoppingPopup) {
  shoppingPopup.addEventListener("click", function (e) {
    if (e.target === shoppingPopup) {
      hideShoppingList();
    }
  });
}
