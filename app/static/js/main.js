// barloni-gram-seva — minimal vanilla JS

// Mobile nav toggle
(function () {
    var toggle = document.getElementById('navToggle');
    var nav = document.getElementById('nav');
    if (toggle && nav) {
        toggle.addEventListener('click', function () {
            nav.classList.toggle('open');
        });
    }
})();

// Client-side scheme search filtering (progressive enhancement).
// The server already filters; this gives instant feedback while typing.
(function () {
    var input = document.getElementById('schemeFilter');
    if (!input) return;
    input.addEventListener('input', function () {
        var term = input.value.trim().toLowerCase();
        var cards = document.querySelectorAll('[data-scheme-card]');
        cards.forEach(function (card) {
            var hay = (card.getAttribute('data-search') || '').toLowerCase();
            card.style.display = hay.indexOf(term) === -1 ? 'none' : '';
        });
    });
})();

// Show/hide land area field based on land ownership selection
(function () {
    var land = document.getElementById('land_ownership');
    var areaField = document.getElementById('landAreaField');
    if (!land || !areaField) return;
    function sync() {
        areaField.style.display = land.value === 'landless' ? 'none' : '';
    }
    land.addEventListener('change', sync);
    sync();
})();

// Confirm before rejecting a change request
(function () {
    var forms = document.querySelectorAll('[data-confirm]');
    forms.forEach(function (form) {
        form.addEventListener('submit', function (e) {
            if (!window.confirm(form.getAttribute('data-confirm'))) {
                e.preventDefault();
            }
        });
    });
})();
