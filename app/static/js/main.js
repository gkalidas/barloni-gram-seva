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

// Inline "add document" on the admin scheme form. Saves to the shared master
// list, then appends a (checked) checkbox without losing the rest of the form.
(function () {
    var btn = document.getElementById('addDocBtn');
    var input = document.getElementById('newDocName');
    var list = document.getElementById('documentsList');
    if (!btn || !input || !list) return;

    function exists(name) {
        var boxes = list.querySelectorAll('input[name="documents"]');
        for (var i = 0; i < boxes.length; i++) {
            if (boxes[i].value.toLowerCase() === name.toLowerCase()) return boxes[i];
        }
        return null;
    }

    function addDoc() {
        var name = input.value.trim();
        if (!name) return;
        var existing = exists(name);
        if (existing) { existing.checked = true; input.value = ''; return; }

        var body = new URLSearchParams();
        body.append('name', name);
        btn.disabled = true;
        fetch('/admin/documents/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
            body: body.toString()
        })
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (!data.ok) { alert(data.error || 'Could not add document.'); return; }
                var hit = exists(data.name);
                if (hit) { hit.checked = true; input.value = ''; return; }
                var label = document.createElement('label');
                label.className = 'checkbox-field';
                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.name = 'documents';
                cb.value = data.name;
                cb.checked = true;
                label.appendChild(cb);
                label.appendChild(document.createTextNode(' ' + data.name));
                list.appendChild(label);
                input.value = '';
            })
            .catch(function () { alert('Could not add document.'); })
            .finally(function () { btn.disabled = false; });
    }

    btn.addEventListener('click', addDoc);
    input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); addDoc(); }
    });
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

// Document locker: pick several files at once, then choose a type + number for
// each. One row per selected file, in the same order the files are submitted.
(function () {
    var fileInput = document.getElementById('docFiles');
    var rows = document.getElementById('docRows');
    var proto = document.getElementById('docNameProto');
    if (!fileInput || !rows || !proto) return;

    fileInput.addEventListener('change', function () {
        rows.innerHTML = '';
        Array.prototype.forEach.call(fileInput.files, function (f) {
            var row = document.createElement('div');
            row.className = 'field doc-upload-row';

            var name = document.createElement('div');
            name.className = 'hint';
            name.textContent = '📎 ' + f.name;

            var sel = proto.cloneNode(true);
            sel.removeAttribute('id');
            sel.hidden = false;
            sel.name = 'document_name';
            sel.required = true;

            var num = document.createElement('input');
            num.type = 'text';
            num.name = 'doc_number';
            num.placeholder = 'Document number (optional)';
            num.style.marginTop = '0.3rem';

            row.appendChild(name);
            row.appendChild(sel);
            row.appendChild(num);
            rows.appendChild(row);
        });
    });
})();

// Share profile + approved documents to WhatsApp. On mobile browsers that
// support file sharing this attaches the document files via the native share
// sheet (pick WhatsApp); elsewhere it opens WhatsApp with the text summary.
(function () {
    var btn = document.getElementById('waShareBtn');
    var dataEl = document.getElementById('shareData');
    if (!btn) return;
    var data = { text: '', files: [] };
    if (dataEl) { try { data = JSON.parse(dataEl.textContent); } catch (e) {} }

    function waLink(text) {
        return 'https://wa.me/?text=' + encodeURIComponent(text);
    }

    btn.addEventListener('click', function () {
        if (!window.confirm('This shares your personal profile details'
            + (data.files && data.files.length ? ' and your approved document files' : '')
            + ' on WhatsApp. Continue?')) return;

        var hasFiles = data.files && data.files.length;
        if (!hasFiles || !navigator.canShare) {
            window.open(waLink(data.text), '_blank');
            return;
        }

        btn.disabled = true;
        Promise.all(data.files.map(function (f) {
            return fetch(f.url)
                .then(function (r) { return r.ok ? r.blob() : null; })
                .then(function (b) { return b ? new File([b], f.name, { type: b.type }) : null; })
                .catch(function () { return null; });
        })).then(function (results) {
            var files = results.filter(Boolean);
            if (files.length && navigator.canShare({ files: files })) {
                return navigator.share({ text: data.text, files: files });
            }
            window.open(waLink(data.text), '_blank');
        }).catch(function (e) {
            if (e && e.name !== 'AbortError') window.open(waLink(data.text), '_blank');
        }).finally(function () {
            btn.disabled = false;
        });
    });
})();
