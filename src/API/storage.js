// Kleine wrapper rond localStorage. In een privé-venster of met cookies uit gooit
// localStorage een error, dus alles is hier defensief: bij twijfel geven we de
// standaardwaarde terug in plaats van de pagina te laten crashen.

export function readJSON(key, fallback) {
    try {
        const raw = localStorage.getItem(key);
        if (raw === null) return fallback;
        const parsed = JSON.parse(raw);
        return parsed === null || parsed === undefined ? fallback : parsed;
    } catch {
        return fallback;
    }
}

export function writeJSON(key, value) {
    try {
        localStorage.setItem(key, JSON.stringify(value));
        return true;
    } catch {
        return false;
    }
}
