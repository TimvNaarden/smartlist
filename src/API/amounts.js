// Hoeveelheden bij elkaar optellen voor de boodschappenlijst.
//
// Drie recepten die elk knoflook gebruiken leverden eerder "3 cloves + 1 clove +
// 2 cloves" op. Dat hoort "6 cloves" te zijn. Alles wat in dezelfde eenheid staat
// wordt opgeteld; wat niet bij elkaar past blijft naast elkaar staan.
//
// De maten in de json staan in één vaste vorm (zie tools/normalize_data.py):
// "<getal> <eenheid>[, bewerking]" of een omschrijving als "To taste". Daar kan
// deze module dus op vertrouwen.

// Eenheden die nooit een meervoud krijgen.
const GEEN_MEERVOUD = new Set(['g', 'kg', 'ml', 'l', 'cl', 'dl', 'oz', 'lb', 'tsp', 'tbsp', 'cm', 'mm']);

// Meervouden die niet op -s eindigen.
const MEERVOUD = {
    leaf: 'leaves',
    pinch: 'pinches',
    dash: 'dashes',
    splash: 'splashes',
    bunch: 'bunches',
    wedge: 'wedges',
    inch: 'inches',
};

const ENKELVOUD = Object.fromEntries(Object.entries(MEERVOUD).map(([een, meer]) => [meer, een]));

// Grootteaanduidingen zijn geen eenheid en krijgen dus geen meervoud.
const GROOTTES = new Set(['large', 'medium', 'small', 'whole', 'thin', 'thick', 'extra', 'jumbo', 'baby', 'big', 'fresh']);

// Bij metrische eenheden schrijven we 1.5 en niet 1 1/2; bij de rest omgekeerd.
const DECIMAAL = new Set(['g', 'kg', 'ml', 'l', 'cl', 'dl', 'cm', 'mm']);

// Eenheden die in elkaar overgaan zodra het genoeg wordt.
const OPSCHALEN = {
    g: { grens: 1000, naar: 'kg', factor: 1000 },
    ml: { grens: 1000, naar: 'l', factor: 1000 },
};

const BREUKEN = [
    [1 / 8, '1/8'],
    [1 / 4, '1/4'],
    [1 / 3, '1/3'],
    [3 / 8, '3/8'],
    [1 / 2, '1/2'],
    [5 / 8, '5/8'],
    [2 / 3, '2/3'],
    [3 / 4, '3/4'],
    [7 / 8, '7/8'],
];

// "2", "1.5", "1/2" en "1 1/2" naar een getal.
function leesGetal(text) {
    const gemengd = text.match(/^(\d+)\s+(\d+)\/(\d+)$/);
    if (gemengd) return Number(gemengd[1]) + Number(gemengd[2]) / Number(gemengd[3]);

    const breuk = text.match(/^(\d+)\/(\d+)$/);
    if (breuk) return Number(breuk[1]) / Number(breuk[2]);

    const getal = Number(text);
    return Number.isFinite(getal) ? getal : null;
}

// Een getal terugschrijven als heel getal, breuk of decimaal.
function schrijfGetal(waarde, metrisch) {
    const afgerond = Math.round(waarde * 1000) / 1000;
    if (Number.isInteger(afgerond)) return String(afgerond);
    if (metrisch) return String(afgerond);

    const heel = Math.floor(afgerond);
    const rest = afgerond - heel;
    const breuk = BREUKEN.find(([waardeBreuk]) => Math.abs(rest - waardeBreuk) < 0.01);
    if (!breuk) return String(afgerond);
    return heel ? `${heel} ${breuk[1]}` : breuk[1];
}

function enkelvoud(eenheid) {
    if (!eenheid) return '';
    if (GEEN_MEERVOUD.has(eenheid) || GROOTTES.has(eenheid)) return eenheid;

    const [kop, ...staart] = eenheid.split(' ');
    if (GEEN_MEERVOUD.has(kop) || GROOTTES.has(kop)) return eenheid;
    const nieuweKop = ENKELVOUD[kop] || (kop.endsWith('s') && !kop.endsWith('ss') ? kop.slice(0, -1) : kop);
    return [nieuweKop, ...staart].join(' ');
}

function meervoud(eenheid, aantal) {
    if (!eenheid || GEEN_MEERVOUD.has(eenheid) || GROOTTES.has(eenheid) || aantal <= 1) return eenheid;

    // "1 can (400 g)" -> "2 cans (400 g)": alleen het eerste woord verbuigt.
    const [kop, ...staart] = eenheid.split(' ');
    if (GROOTTES.has(kop) || GEEN_MEERVOUD.has(kop)) return eenheid;
    const nieuweKop = MEERVOUD[kop] || (kop.endsWith('s') ? kop : `${kop}s`);
    return [nieuweKop, ...staart].join(' ');
}

// Splitst één maat in een hoeveelheid, een eenheid en de rest.
export function leesMaat(raw) {
    const tekst = (raw || '').split(',')[0].trim(); // de bewerking hoort niet op een boodschappenlijst
    if (!tekst) return null;

    const match = tekst.match(/^(\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:\.\d+)?)\s*(.*)$/);
    if (!match) return { tekst, aantal: null, eenheid: '', hoeveelheid: false };

    const aantal = leesGetal(match[1]);
    const staart = match[2].trim();

    // Een bereik als "15-20" of iets als "2 x 400 g" telt niet op, maar het is
    // wel een hoeveelheid: die blijft in de lijst staan.
    if (aantal === null || staart.startsWith('-') || staart.startsWith('x ')) {
        return { tekst, aantal: null, eenheid: '', hoeveelheid: true };
    }

    // De maat kan een verpakkingsinhoud bevatten: "1 can (400 g)".
    const eenheid = staart.toLowerCase();
    return { tekst, aantal, eenheid };
}

/**
 * Voegt de maten van hetzelfde ingrediënt samen.
 *
 * ["3 cloves, minced", "1 clove", "2 cloves"]  ->  "6 cloves"
 * ["100 g", "1/2 kg"]                          ->  "600 g"
 * ["1 tbsp", "2 tsp"]                          ->  "1 tbsp + 2 tsp"
 * ["To taste", "1 tsp"]                        ->  "1 tsp"
 * ["To taste", "Pinch"]                        ->  "To taste + Pinch"
 */
export function voegMatenSamen(maten) {
    const perEenheid = new Map(); // eenheid in enkelvoud -> totaal
    const losse = []; // hoeveelheden die niet optellen, zoals "15-20"
    const omschrijvingen = []; // "To taste", "Pinch", "For frying"

    (maten || []).forEach((raw) => {
        const maat = leesMaat(raw);
        if (!maat) return;

        if (maat.aantal === null) {
            const lijst = maat.hoeveelheid ? losse : omschrijvingen;
            if (!lijst.includes(maat.tekst)) lijst.push(maat.tekst);
            return;
        }

        let aantal = maat.aantal;
        let eenheid = enkelvoud(maat.eenheid);

        // kg bij g optellen, l bij ml
        const grover = Object.entries(OPSCHALEN).find(([, regel]) => regel.naar === eenheid);
        if (grover) {
            aantal *= grover[1].factor;
            [eenheid] = grover;
        }

        perEenheid.set(eenheid, (perEenheid.get(eenheid) || 0) + aantal);
    });

    // "1 small" en "1" bij hetzelfde ingrediënt zijn samen "2": op een
    // boodschappenlijst gaat het om het aantal, niet om de maat van de ui.
    if (perEenheid.size > 1) {
        [...perEenheid.keys()].filter((eenheid) => GROOTTES.has(eenheid)).forEach((eenheid) => {
            if (perEenheid.has('')) {
                perEenheid.set('', perEenheid.get('') + perEenheid.get(eenheid));
                perEenheid.delete(eenheid);
            }
        });
    }

    const delen = [...perEenheid.entries()].map(([eenheid, totaal]) => {
        let aantal = totaal;
        let naam = eenheid;

        const regel = OPSCHALEN[eenheid];
        if (regel && aantal >= regel.grens) {
            aantal /= regel.factor;
            naam = regel.naar;
        }

        const getal = schrijfGetal(aantal, DECIMAAL.has(naam));
        return naam ? `${getal} ${meervoud(naam, aantal)}` : getal;
    });

    // Staat er een echte hoeveelheid, dan zegt "to taste" er niets meer bij.
    const alles = [...delen, ...losse];
    if (alles.length > 0) return alles.join(' + ');
    return omschrijvingen.join(' + ');
}

// ---------------------------------------------------------------- opschalen

// Bij opschalen komen er rare getallen uit: de helft van 225 g is 112.5 g. Niemand
// weegt dat af, dus grammen en milliliters worden netjes afgerond.
function rondAf(waarde, eenheid) {
    if (!DECIMAAL.has(eenheid)) return waarde;
    if (eenheid === 'kg' || eenheid === 'l') return Math.round(waarde * 100) / 100;
    if (waarde >= 500) return Math.round(waarde / 25) * 25;
    if (waarde >= 20) return Math.round(waarde / 5) * 5;
    return Math.round(waarde * 2) / 2;
}

const REEKS = /^(\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:\.\d+)?)\s*-\s*(\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:\.\d+)?)\s*(.*)$/;
const ENKEL = /^(\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:\.\d+)?)\s*(.*)$/;
const SAP = /^(Juice|Zest|Zest and juice) of (\d+\s+\d+\/\d+|\d+\/\d+|\d+(?:\.\d+)?)$/;

/**
 * Rekent één maat om naar een ander aantal personen.
 *
 *   schaalMaat('100 g', 2)              -> '200 g'
 *   schaalMaat('2 cloves, minced', 2)   -> '4 cloves, minced'
 *   schaalMaat('1-2 tbsp', 2)           -> '2-4 tbsp'
 *   schaalMaat('Juice of 1', 3)         -> 'Juice of 3'
 *   schaalMaat('To taste', 2)           -> 'To taste'
 *
 * Omschrijvingen zonder getal blijven staan: een snufje zout blijft een snufje.
 */
export function schaalMaat(raw, factor) {
    const tekst = (raw || '').trim();
    if (!tekst || !factor || factor === 1) return tekst;

    // De bewerking achter de komma blijft ongemoeid.
    const komma = tekst.indexOf(',');
    const kop = komma === -1 ? tekst : tekst.slice(0, komma);
    const staart = komma === -1 ? '' : tekst.slice(komma);

    const sap = kop.match(SAP);
    if (sap) {
        const aantal = leesGetal(sap[2]);
        if (aantal !== null) return `${sap[1]} of ${schrijfGetal(aantal * factor, false)}${staart}`;
    }

    const reeks = kop.match(REEKS);
    if (reeks) {
        const laag = leesGetal(reeks[1]);
        const hoog = leesGetal(reeks[2]);
        const eenheid = reeks[3].trim();
        if (laag !== null && hoog !== null) {
            const basis = enkelvoud(eenheid.toLowerCase());
            const decimaal = DECIMAAL.has(basis);
            const nieuwLaag = rondAf(laag * factor, basis);
            const nieuwHoog = rondAf(hoog * factor, basis);
            const nieuweEenheid = meervoud(basis, nieuwHoog);
            const staartEenheid = nieuweEenheid ? ` ${nieuweEenheid}` : '';
            return `${schrijfGetal(nieuwLaag, decimaal)}-${schrijfGetal(nieuwHoog, decimaal)}${staartEenheid}${staart}`;
        }
    }

    const enkel = kop.match(ENKEL);
    if (enkel) {
        const aantal = leesGetal(enkel[1]);
        const rest = enkel[2].trim();
        if (aantal !== null) {
            // Een verpakkingsinhoud tussen haakjes hoort niet mee te schalen.
            const haakje = rest.match(/^(.*?)\s*(\([^)]*\))$/);
            const eenheidTekst = (haakje ? haakje[1] : rest).trim();
            const inhoud = haakje ? ` ${haakje[2]}` : '';
            const basis = enkelvoud(eenheidTekst.toLowerCase());
            const nieuw = rondAf(aantal * factor, basis);
            const eenheid = meervoud(basis, nieuw);
            const delen = [schrijfGetal(nieuw, DECIMAAL.has(basis))];
            if (eenheid) delen.push(eenheid);
            return `${delen.join(' ')}${inhoud}${staart}`;
        }
    }

    return tekst;
}

/** Rekent de ingrediënten van een gerecht om. */
export function schaalIngredienten(ingredienten, factor) {
    return (ingredienten || []).map((ingredient) => ({
        ...ingredient,
        measure: schaalMaat(ingredient.measure, factor),
    }));
}
