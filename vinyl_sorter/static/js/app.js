/* ============================================================
   VinylSorter — Client-side collection renderer
   ============================================================ */

(function () {
    'use strict';

    const container = document.getElementById('collection-container');
    const subtitle = document.getElementById('stats-subtitle');
    const overlay = document.getElementById('modal-overlay');
    const modal = document.getElementById('modal');
    const modalClose = document.getElementById('modal-close');

    // Modal fields
    const modalCoverImg = document.getElementById('modal-cover-img');
    const modalSortNum = document.getElementById('modal-sort-num');
    const modalTitle = document.getElementById('modal-title');
    const modalArtist = document.getElementById('modal-artist');
    const modalYear = document.getElementById('modal-year');
    const modalSortDetails = document.getElementById('modal-sort-details');
    const modalBadges = document.getElementById('modal-badges');

    // ---- Fetch & render ----

    async function init() {
        try {
            const [collectionRes, statsRes] = await Promise.all([
                fetch('/collection'),
                fetch('/collection/stats'),
            ]);

            if (!collectionRes.ok) throw new Error(`Collection fetch failed: ${collectionRes.status}`);
            if (!statsRes.ok) throw new Error(`Stats fetch failed: ${statsRes.status}`);

            const records = await collectionRes.json();
            const stats = await statsRes.json();

            renderStats(stats);

            if (records.length === 0) {
                renderEmpty();
            } else {
                renderCollection(records);
            }
        } catch (err) {
            console.error('Failed to load collection:', err);
            container.innerHTML = `
                <div class="empty-state">
                    <div class="icon">⚠️</div>
                    <p>Could not load the collection.</p>
                    <p style="font-size: 0.85rem; margin-top: 0.5rem; color: var(--text-muted);">${escapeHtml(err.message)}</p>
                </div>`;
        }
    }

    function renderStats(stats) {
        const parts = [];
        if (stats.total_records) parts.push(`${stats.total_records} records`);
        if (stats.total_artists) parts.push(`${stats.total_artists} artists`);
        if (stats.total_compilations) parts.push(`${stats.total_compilations} compilations`);
        subtitle.textContent = parts.join(' · ') || 'Empty collection';
    }

    function renderEmpty() {
        container.innerHTML = `
            <div class="empty-state">
                <div class="icon">🎵</div>
                <p>No records in your collection yet.</p>
            </div>`;
    }

    // ---- Collection rendering with letter dividers ----

    function renderCollection(records) {
        container.innerHTML = '';

        // Separate compilations from non-compilations
        const regular = records.filter(r => !r.is_compilation);
        const compilations = records.filter(r => r.is_compilation);

        // Group regular records by first letter of sort_artist
        let currentLetter = null;
        let currentSection = null;
        let currentGrid = null;

        for (const record of regular) {
            const letter = getFirstLetter(record.sort_artist);

            if (letter !== currentLetter) {
                currentLetter = letter;
                currentSection = createSection(letter);
                currentGrid = currentSection.querySelector('.album-grid');
                container.appendChild(currentSection);
            }

            currentGrid.appendChild(createCard(record));
        }

        // Compilations section at the end
        if (compilations.length > 0) {
            const compSection = createSection('Compilations');
            const compGrid = compSection.querySelector('.album-grid');
            for (const record of compilations) {
                compGrid.appendChild(createCard(record));
            }
            container.appendChild(compSection);
        }
    }

    function getFirstLetter(sortArtist) {
        if (!sortArtist) return '#';
        const ch = sortArtist.charAt(0).toUpperCase();
        return /[A-Z]/.test(ch) ? ch : '#';
    }

    function createSection(label) {
        const section = document.createElement('div');
        section.className = 'album-section';

        const divider = document.createElement('div');
        divider.className = 'letter-divider';
        divider.innerHTML = `<span class="letter">${escapeHtml(label)}</span><span class="line"></span>`;

        const grid = document.createElement('div');
        grid.className = 'album-grid';

        section.appendChild(divider);
        section.appendChild(grid);
        return section;
    }

    function createCard(record) {
        const card = document.createElement('div');
        card.className = 'album-card';
        card.tabIndex = 0;
        card.setAttribute('role', 'button');
        card.setAttribute('aria-label', `${record.release_title} by ${record.release_artist}`);

        if (record.thumb_url) {
            const img = document.createElement('img');
            img.className = 'loading-img';
            img.alt = `${record.release_title} by ${record.release_artist}`;
            img.loading = 'lazy';
            img.onload = function () { this.classList.remove('loading-img'); this.classList.add('loaded'); };
            img.onerror = function () { replacePlaceholder(card, record); };
            img.src = record.thumb_url;
            card.appendChild(img);
        } else {
            appendPlaceholder(card, record);
        }

        card.addEventListener('click', () => openModal(record));
        card.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openModal(record);
            }
        });

        return card;
    }

    function appendPlaceholder(card, record) {
        const ph = document.createElement('div');
        ph.className = 'album-placeholder';
        ph.innerHTML = `<span class="vinyl-icon">💿</span><span class="placeholder-title">${escapeHtml(record.release_title)}</span>`;
        card.appendChild(ph);
    }

    function replacePlaceholder(card, record) {
        card.innerHTML = '';
        appendPlaceholder(card, record);
    }

    // ---- Modal ----

    function openModal(record) {
        // Cover image
        if (record.cover_image_url) {
            modalCoverImg.src = record.cover_image_url;
            modalCoverImg.alt = `${record.release_title} cover art`;
            modalCoverImg.style.display = 'block';
        } else if (record.thumb_url) {
            modalCoverImg.src = record.thumb_url;
            modalCoverImg.alt = `${record.release_title} cover art`;
            modalCoverImg.style.display = 'block';
        } else {
            modalCoverImg.style.display = 'none';
        }

        modalSortNum.textContent = `#${record.sort_sequence}`;
        modalTitle.textContent = record.release_title;
        modalArtist.textContent = record.release_artist;
        modalYear.textContent = record.release_year > 0 ? String(record.release_year) : 'Year unknown';

        // Sort details (show if different from display values)
        const sortParts = [];
        if (record.sort_artist && record.sort_artist !== record.release_artist) {
            sortParts.push(`Sorted as: ${record.sort_artist}`);
        }
        if (record.sort_year > 0 && record.sort_year !== record.release_year) {
            sortParts.push(`Sort year: ${record.sort_year}`);
        }
        modalSortDetails.textContent = sortParts.join(' · ');
        modalSortDetails.style.display = sortParts.length ? 'block' : 'none';

        // Badges
        modalBadges.innerHTML = '';
        if (record.is_live) {
            const badge = document.createElement('span');
            badge.className = 'badge badge-live';
            badge.textContent = 'Live';
            modalBadges.appendChild(badge);
        }
        if (record.is_compilation) {
            const badge = document.createElement('span');
            badge.className = 'badge badge-compilation';
            badge.textContent = 'Compilation';
            modalBadges.appendChild(badge);
        }

        overlay.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        overlay.classList.remove('active');
        document.body.style.overflow = '';
    }

    // Close on overlay click (but not modal itself)
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeModal();
    });

    modalClose.addEventListener('click', closeModal);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeModal();
    });

    // ---- Utilities ----

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    // ---- Go ----
    init();

})();
