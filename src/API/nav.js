// Navigatie: het mobiele menu openen/sluiten en de huidige pagina markeren.
// Stond eerder als losse copy-paste inline scripts in elke pagina.

function currentPage() {
    const path = window.location.pathname.split('/').pop();
    return (path || 'index.html').toLowerCase();
}

function markActiveLink() {
    const page = currentPage();

    document.querySelectorAll('nav a[href]').forEach((link) => {
        const target = link.getAttribute('href').split('/').pop().toLowerCase();
        if (target && target === page) {
            link.classList.add('actief');
            link.setAttribute('aria-current', 'page');
        }
    });
}

function initSidemenu() {
    const sidemenu = document.querySelector('.sidemenu');
    const openButton = document.querySelector('.menuknop');
    if (!sidemenu || !openButton) return;

    const open = () => {
        sidemenu.classList.add('open');
        openButton.setAttribute('aria-expanded', 'true');
    };

    const close = () => {
        sidemenu.classList.remove('open');
        openButton.setAttribute('aria-expanded', 'false');
    };

    openButton.setAttribute('aria-expanded', 'false');
    openButton.addEventListener('click', (event) => {
        event.preventDefault();
        sidemenu.classList.contains('open') ? close() : open();
    });

    sidemenu.querySelectorAll('.sidemenu-sluit').forEach((button) => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            close();
        });
    });

    // Sluiten na een keuze en bij Escape, zodat het menu niet blijft hangen.
    sidemenu.querySelectorAll('a:not(.sidemenu-sluit)').forEach((link) => link.addEventListener('click', close));
    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') close();
    });
}

markActiveLink();
initSidemenu();
