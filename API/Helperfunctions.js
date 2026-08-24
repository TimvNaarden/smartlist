function extractProductName(title) {
    const normalized = normalizeName(title);
    for (const [dutch, mealdb] of Object.entries(productTranslations)) {
        if (normalized == dutch)  {
            return mealdb; // can be null (intentionally ignored)
        } 
    }

    return null;
}
function normalizeName(name) {
    let result = name.toLowerCase();

    STOP_WORDS.forEach((word) => {
        result = result.replace(new RegExp(`\\b${word}\\b`, 'g'), '');
    });

    return result.replace(/\s+/g, ' ').trim();
}
const productTranslations = {
    //IGNORE
    appelmoes: null,
    appelcompote: null,
    rabarber: null,
    vlaaifruit: null,
    wraps: null,
    nachos: null,
    runder: null,
    knaks: null, 
    kipgehakt: null,

    kip: 'chicken',
    kipkluifjes: 'chicken wings',
    kipfilet: 'chicken',
    kippenbout: 'chicken',
    kippenpoten: 'chicken',
    kipburger: 'chicken',

    rund: 'beef',
    rundvlees: 'beef',
    ossenhaas: 'beef',
    entrecote: 'beef',
    ribeye: 'beef',
    sukade: 'beef',
    stoofvlees: 'stock',
    gehakt: 'minced beef',

    varken: 'pork',
    varkens: 'pork',
    varkenshaas: 'pork',
    varkensoester: 'pork',
    spek: 'bacon',
    beenham: 'ham',

    tonijn: 'tuna',
    zalm: 'salmon',
    kabeljauw: 'cod',
};

const STOP_WORDS = [
    'ah',
    'excellent',
    'unox',
    'hak',
    'extra',
    'kwaliteit',
    'vers',
    'scharrel',
    'biologisch',
    'biologische',
    'schotel',
    'ovenschotel',
    'verspakket',
    'met',
    'stukjes',
    'saus',
    'room',
    'gekruid',
    'naturel',
    'pittig',
    'magnetron',
    'voor',
    'in',
    'de',
    'oven',
    'knaks',
    'olie',
    'fish tales',
    'skipjack',
    'tuinkruiden',
    'runder',
    'unox kip'
];
