/* ============================================================
   VinylSorter — Client-side collection renderer
   ============================================================ */

(function () {
    'use strict';

    const container = document.getElementById('collection-container');
    const cfContainer = document.getElementById('coverflow-container');
    const subtitle = document.getElementById('stats-subtitle');
    const overlay = document.getElementById('modal-overlay');
    const modal = document.getElementById('modal');
    const modalClose = document.getElementById('modal-close');

    // View toggle elements
    const viewToggle = document.getElementById('view-toggle');
    const btnGrid = document.getElementById('btn-grid');
    const btnFlow = document.getElementById('btn-flow');

    // Sort toggle elements
    const sortToggle = document.getElementById('sort-toggle');
    const btnSortOriginal = document.getElementById('btn-sort-original');
    const btnSortYear = document.getElementById('btn-sort-year');
    const btnSortAdded = document.getElementById('btn-sort-added');

    // Shared state
    let _allRecords = [];    // flat sorted array from API (canonical order from server)
    let _currentView = 'grid';
    let _currentSort = 'original';
    let _coverFlowReady = false;

    // Modal fields
    const modalCoverImg = document.getElementById('modal-cover-img');
    const modalSortNum = document.getElementById('modal-sort-num');
    const modalTitle = document.getElementById('modal-title');
    const modalArtist = document.getElementById('modal-artist');
    const modalYear = document.getElementById('modal-year');
    const modalSortDetails = document.getElementById('modal-sort-details');
    const modalBadges = document.getElementById('modal-badges');
    const modalDiscogsLink = document.getElementById('modal-discogs-link');

    // ---- View Toggle ----

    function initViewToggle() {
        // Restore saved preference
        var saved = localStorage.getItem('vinylsort-view');
        if (saved === 'flow' || saved === 'grid') {
            _currentView = saved;
        }

        btnGrid.addEventListener('click', function () { switchView('grid'); });
        btnFlow.addEventListener('click', function () { switchView('flow'); });

        // Apply initial state (after data load)
        updateToggleUI();
    }

    function switchView(view) {
        if (view === _currentView) return;
        _currentView = view;
        localStorage.setItem('vinylsort-view', view);
        updateToggleUI();
        applyView();
    }

    function updateToggleUI() {
        btnGrid.classList.toggle('active', _currentView === 'grid');
        btnFlow.classList.toggle('active', _currentView === 'flow');
    }

    // ---- Sort Toggle ----

    function initSortToggle() {
        var saved = localStorage.getItem('vinylsort-sort');
        if (saved === 'original' || saved === 'year' || saved === 'added') {
            _currentSort = saved;
        }

        btnSortOriginal.addEventListener('click', function () { switchSort('original'); });
        btnSortYear.addEventListener('click', function () { switchSort('year'); });
        btnSortAdded.addEventListener('click', function () { switchSort('added'); });

        updateSortToggleUI();
    }

    function switchSort(sort) {
        if (sort === _currentSort) return;
        _currentSort = sort;
        localStorage.setItem('vinylsort-sort', sort);
        updateSortToggleUI();
        rerender();
    }

    function updateSortToggleUI() {
        btnSortOriginal.classList.toggle('active', _currentSort === 'original');
        btnSortYear.classList.toggle('active', _currentSort === 'year');
        btnSortAdded.classList.toggle('active', _currentSort === 'added');
    }

    function applySort(records) {
        var arr = records.slice();  // never mutate _allRecords
        switch (_currentSort) {
            case 'year':
                return arr.sort(function (a, b) {
                    if (a.sort_year !== b.sort_year) return a.sort_year - b.sort_year;
                    return a.sort_sequence - b.sort_sequence;
                });
            case 'added':
                return arr.sort(function (a, b) {
                    var ta = a.date_added ? Date.parse(a.date_added) : 0;
                    var tb = b.date_added ? Date.parse(b.date_added) : 0;
                    if (ta !== tb) return tb - ta;  // newest first
                    return a.sort_sequence - b.sort_sequence;
                });
            case 'original':
            default:
                return arr;
        }
    }

    /** Re-render the visible collection from _allRecords with the current sort applied. */
    function rerender() {
        if (_allRecords.length === 0) return;
        var sorted = applySort(_allRecords);
        if (_currentView === 'flow') {
            // Re-init CoverFlow with the new ordering so the carousel reflects it.
            if (typeof CoverFlow !== 'undefined') {
                _coverFlowReady = false;
                CoverFlow.destroy();
                CoverFlow.init(cfContainer, sorted, { onOpenModal: openModal });
                _coverFlowReady = true;
            }
        } else {
            renderCollection(sorted);
        }
    }

    function applyView() {
        if (_currentView === 'grid') {
            container.style.display = '';
            cfContainer.classList.remove('active');

            // If switching from flow, try to scroll grid near the same album
            if (_coverFlowReady && typeof CoverFlow !== 'undefined') {
                scrollGridToIndex(CoverFlow.getCurrentIndex());
            }
        } else {
            container.style.display = 'none';
            cfContainer.classList.add('active');

            // Initialize CoverFlow if not yet done
            if (!_coverFlowReady && _allRecords.length > 0) {
                CoverFlow.init(cfContainer, applySort(_allRecords), {
                    onOpenModal: openModal,
                });
                _coverFlowReady = true;
            }

            // Try to sync position from grid scroll
            if (_coverFlowReady) {
                var gridIndex = getApproxGridIndex();
                if (gridIndex >= 0) {
                    CoverFlow.goTo(gridIndex);
                }
            }
        }
    }

    /** Approximate which album the user is looking at in the grid (by scroll position). */
    function getApproxGridIndex() {
        // Find the first album card that is in or near the viewport
        var cards = container.querySelectorAll('.album-card');
        var viewportTop = window.scrollY + window.innerHeight * 0.3;

        for (var i = 0; i < cards.length; i++) {
            var rect = cards[i].getBoundingClientRect();
            var cardTop = rect.top + window.scrollY;
            if (cardTop >= viewportTop - 200) {
                // Cards don't store index directly, but they're in order.
                // Match by position in the full records array.
                return i;
            }
        }
        return 0;
    }

    /** Scroll the grid view so an album near the given index is visible. */
    function scrollGridToIndex(index) {
        var cards = container.querySelectorAll('.album-card');
        if (index >= 0 && index < cards.length) {
            cards[index].scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    // ---- Fetch & render ----

    async function init() {
        initViewToggle();
        initSortToggle();

        try {
            const [collectionRes, statsRes] = await Promise.all([
                fetch('/collection'),
                fetch('/collection/stats'),
            ]);

            if (!collectionRes.ok) throw new Error(`Collection fetch failed: ${collectionRes.status}`);
            if (!statsRes.ok) throw new Error(`Stats fetch failed: ${statsRes.status}`);

            const records = await collectionRes.json();
            const stats = await statsRes.json();

            _allRecords = records;

            renderStats(stats);

            if (records.length === 0) {
                renderEmpty();
                viewToggle.style.display = 'none'; // hide toggle for empty collections
                sortToggle.style.display = 'none';
            } else {
                renderCollection(applySort(_allRecords));
                // Apply saved view preference now that data is loaded
                applyView();
            }
        } catch (err) {
            console.error('Failed to load collection:', err);
            container.innerHTML = `
                <div class="empty-state">
                    <div class="icon">⚠️</div>
                    <p>Could not load the collection.</p>
                    <p style="font-size: 0.85rem; margin-top: 0.5rem; color: var(--text-muted);">${escapeHtml(err.message)}</p>
                </div>`;
            viewToggle.style.display = 'none';
            sortToggle.style.display = 'none';
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

        // Divider strategy depends on the active sort. For "original" we keep the
        // legacy first-letter-of-sort_artist grouping plus a trailing Compilations
        // section. For "year" / "added" we group by the sort key itself, treat
        // compilations like any other record, and bucket missing-key records into
        // a final "Unknown" section. Within each section, records stay in the
        // order applySort() produced (sort tiebreaker handles intra-section order).
        const groups = computeSections(records);

        for (const group of groups) {
            const section = createSection(group.label);
            const grid = section.querySelector('.album-grid');
            for (const record of group.records) {
                grid.appendChild(createCard(record));
            }
            container.appendChild(section);
        }
    }

    /**
     * Slice the sorted records into divider sections. For "original" this is the
     * legacy first-letter-of-sort_artist grouping with a trailing Compilations
     * section. For "year" / "added" it's a bucket-by-key grouping (with an
     * "Unknown" bucket at the bottom for missing keys) — compilations are not
     * split out under those modes.
     */
    function computeSections(records) {
        if (_currentSort === 'year') {
            return bucketBy(records, function (r) {
                return r.sort_year > 0 ? String(r.sort_year) : null;
            }, 'Unknown');
        }
        if (_currentSort === 'added') {
            return bucketBy(records, function (r) {
                if (!r.date_added) return null;
                var d = new Date(r.date_added);
                if (isNaN(d.getTime())) return null;
                var y = d.getUTCFullYear();
                var m = String(d.getUTCMonth() + 1);
                if (m.length < 2) m = '0' + m;
                return y + '-' + m;
            }, 'Unknown');
        }
        // original (default): letter-grouped + trailing Compilations
        return originalSections(records);
    }

    /**
     * Group records by a key function. Records whose key is null/undefined land
     * in a final bucket labeled `unknownLabel`. Because records arrive pre-sorted
     * by applySort(), rendering in iteration order retains the desired section
     * ordering (year ascending, added descending).
     */
    function bucketBy(records, keyFn, unknownLabel) {
        const order = [];
        const map = {};
        const unknowns = [];
        for (const record of records) {
            const key = keyFn(record);
            if (key === null || key === undefined) {
                unknowns.push(record);
                continue;
            }
            if (!map[key]) {
                map[key] = [];
                order.push(key);
            }
            map[key].push(record);
        }
        const sections = [];
        for (const key of order) {
            sections.push({ label: key, records: map[key] });
        }
        if (unknowns.length > 0) {
            sections.push({ label: unknownLabel, records: unknowns });
        }
        return sections;
    }

    /** Legacy first-letter-of-sort_artist grouping + trailing Compilations section. */
    function originalSections(records) {
        const regular = records.filter(function (r) { return !r.is_compilation; });
        const compilations = records.filter(function (r) { return r.is_compilation; });

        const sections = [];
        let currentLetter = null;
        let bucket = null;
        for (const record of regular) {
            const letter = getFirstLetter(record.sort_artist);
            if (letter !== currentLetter) {
                currentLetter = letter;
                bucket = { label: letter, records: [] };
                sections.push(bucket);
            }
            bucket.records.push(record);
        }
        if (compilations.length > 0) {
            sections.push({ label: 'Compilations', records: compilations });
        }
        return sections;
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

        // Discogs deep link
        if (record.discogs_id && record.discogs_id > 0) {
            modalDiscogsLink.href = 'https://www.discogs.com/release/' + record.discogs_id;
            modalDiscogsLink.removeAttribute('aria-disabled');
        } else {
            modalDiscogsLink.href = '#';
            modalDiscogsLink.setAttribute('aria-disabled', 'true');
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
