/* ============================================================
   VinylSorter — Cover Flow Module
   ============================================================
   A 3D perspective album browser inspired by Apple's Cover Flow.

   Usage:
     CoverFlow.init(containerEl, records, { onOpenModal: fn })
     CoverFlow.goTo(index)
     CoverFlow.getCurrentIndex()
     CoverFlow.destroy()
   ============================================================ */

// eslint-disable-next-line no-unused-vars
var CoverFlow = (function () {
    'use strict';

    // --- Configuration ---
    const CFG = {
        VISIBLE_SIDE: 6,           // albums visible on each side of center
        RENDER_BUFFER: 10,         // extra items to keep in DOM beyond visible
        ITEM_SIZE: 350,            // px — center album size (matches CSS) — bumped ~10%
        SIDE_OFFSET: 200,          // px — distance of first side album from center (pushed out so sides don't overlap center)
        SIDE_SPACING: 70,          // px — distance between stacked side albums
        SIDE_ROTATION: 65,         // degrees — Y-rotation for side albums
        SIDE_SCALE: 0.75,          // scale factor for immediate side albums
        TRANSITION_MS: 380,        // ms — CSS transition duration (matches CSS)
        OPACITY_STEP: 0.04,        // opacity reduction per step from center (much gentler fade)
        DEBOUNCE_WHEEL_MS: 120,    // ms — wheel event debounce (less sensitive)
        WHEEL_THRESHOLD: 80,       // accumulated delta before triggering a step
        PRELOAD_AHEAD: 5,          // images to preload ahead/behind current
        NAV_HINT_HIDE_MS: 5000,    // ms — hide nav hint after first interaction
    };

    // --- State ---
    let _container = null;
    let _stage = null;
    let _track = null;
    let _infoPanel = null;
    let _navHint = null;
    let _records = [];
    let _currentIndex = 0;
    let _renderedItems = new Map(); // index -> DOM element
    let _onOpenModal = null;
    let _destroyed = false;

    // Touch tracking
    let _touchStartX = 0;
    let _touchStartY = 0;
    let _touchMoved = false;

    // Wheel debounce
    let _lastWheelTime = 0;
    let _wheelAccum = 0;

    // Image preload cache
    let _preloadedUrls = new Set();

    // Bound handlers (for cleanup)
    let _boundKeydown = null;
    let _boundWheel = null;
    let _boundTouchStart = null;
    let _boundTouchMove = null;
    let _boundTouchEnd = null;

    // --- Helpers ---

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str || '';
        return div.innerHTML;
    }

    function getFirstLetter(sortArtist) {
        if (!sortArtist) return '#';
        const ch = sortArtist.charAt(0).toUpperCase();
        return /[A-Z]/.test(ch) ? ch : '#';
    }

    function clamp(val, min, max) {
        return Math.max(min, Math.min(max, val));
    }

    // --- DOM Creation ---

    function createItemElement(record, index) {
        const el = document.createElement('div');
        el.className = 'coverflow-item';
        el.dataset.index = index;

        if (record.thumb_url || record.cover_image_url) {
            const img = document.createElement('img');
            img.alt = record.release_title + ' by ' + record.release_artist;
            img.loading = 'lazy';
            // Use cover_image_url if available for higher quality, else thumb
            img.src = record.cover_image_url || record.thumb_url;
            img.onerror = function () {
                el.innerHTML = '';
                el.appendChild(createPlaceholder(record));
            };
            el.appendChild(img);
        } else {
            el.appendChild(createPlaceholder(record));
        }

        el.addEventListener('click', function () {
            const idx = parseInt(this.dataset.index, 10);
            if (idx === _currentIndex) {
                // Center album — open modal
                if (_onOpenModal) _onOpenModal(record);
            } else {
                // Side album — navigate to it
                goTo(idx);
            }
        });

        return el;
    }

    function createPlaceholder(record) {
        const ph = document.createElement('div');
        ph.className = 'coverflow-placeholder';
        ph.innerHTML =
            '<span class="vinyl-icon">💿</span>' +
            '<span class="placeholder-title">' + escapeHtml(record.release_title) + '</span>';
        return ph;
    }

    function buildInfoPanel() {
        const info = document.createElement('div');
        info.className = 'coverflow-info';
        info.innerHTML =
            '<div class="cf-title"></div>' +
            '<div class="cf-artist"></div>' +
            '<div class="cf-year"></div>' +
            '<div class="cf-position"></div>' +
            '<div class="cf-letter-indicator"></div>';
        return info;
    }

    function buildNavHint() {
        const hint = document.createElement('div');
        hint.className = 'coverflow-nav-hint';
        hint.textContent = '← → arrow keys · scroll · swipe · click';
        return hint;
    }

    // --- Positioning ---

    function positionItem(el, offset) {
        // offset = distance from center (negative = left, positive = right)
        let tx, ry, sc, op, z;

        if (offset === 0) {
            // Center — always on top
            tx = 0;
            ry = 0;
            sc = 1;
            op = 1;
            z = 100;
            el.classList.add('cf-center');
        } else {
            el.classList.remove('cf-center');
            const absOffset = Math.abs(offset);
            const sign = offset > 0 ? 1 : -1;

            // Translation: first side album is offset, then they stack closer
            tx = sign * (CFG.SIDE_OFFSET + (absOffset - 1) * CFG.SIDE_SPACING);

            // Rotation: tilt away from center
            ry = -sign * CFG.SIDE_ROTATION;

            // Scale: shrink slightly for depth
            sc = Math.max(0.5, CFG.SIDE_SCALE - (absOffset - 1) * 0.03);

            // Opacity: gentler fade — stay mostly opaque near center
            op = Math.max(0.35, 1 - absOffset * CFG.OPACITY_STEP);

            // Z-index: side albums always below center, closer = higher
            z = 50 - absOffset;
        }

        el.style.transform =
            'translate3d(' + tx + 'px, 0, 0) ' +
            'rotateY(' + ry + 'deg) ' +
            'scale3d(' + sc + ', ' + sc + ', 1)';
        el.style.opacity = op;
        el.style.zIndex = Math.max(0, z);
    }

    // --- Virtual Rendering ---

    function getVisibleRange() {
        const half = CFG.VISIBLE_SIDE + CFG.RENDER_BUFFER;
        const start = Math.max(0, _currentIndex - half);
        const end = Math.min(_records.length - 1, _currentIndex + half);
        return { start: start, end: end };
    }

    function reconcileDOM() {
        const range = getVisibleRange();
        const needed = new Set();

        for (let i = range.start; i <= range.end; i++) {
            needed.add(i);
        }

        // Remove items no longer in range
        _renderedItems.forEach(function (el, idx) {
            if (!needed.has(idx)) {
                if (el.parentNode) el.parentNode.removeChild(el);
                _renderedItems.delete(idx);
            }
        });

        // Add items that are needed but not rendered
        needed.forEach(function (idx) {
            if (!_renderedItems.has(idx)) {
                const el = createItemElement(_records[idx], idx);
                _track.appendChild(el);
                _renderedItems.set(idx, el);
            }
        });

        // Position all visible items
        _renderedItems.forEach(function (el, idx) {
            const offset = idx - _currentIndex;
            positionItem(el, offset);
        });
    }

    // --- Info Update ---

    function updateInfo() {
        if (!_infoPanel || _records.length === 0) return;

        const record = _records[_currentIndex];
        const titleEl = _infoPanel.querySelector('.cf-title');
        const artistEl = _infoPanel.querySelector('.cf-artist');
        const yearEl = _infoPanel.querySelector('.cf-year');
        const posEl = _infoPanel.querySelector('.cf-position');
        const letterEl = _infoPanel.querySelector('.cf-letter-indicator');

        titleEl.textContent = record.release_title;
        artistEl.textContent = record.release_artist;
        yearEl.textContent = record.release_year > 0 ? String(record.release_year) : 'Year unknown';
        posEl.textContent = '#' + record.sort_sequence + ' of ' + _records.length;

        const letter = getFirstLetter(record.sort_artist);
        const isComp = record.is_compilation;
        letterEl.textContent = isComp ? 'Compilations' : ('Section: ' + letter);
    }

    // --- Image Preloading ---

    function preloadNearby() {
        const start = Math.max(0, _currentIndex - CFG.PRELOAD_AHEAD);
        const end = Math.min(_records.length - 1, _currentIndex + CFG.PRELOAD_AHEAD);

        for (let i = start; i <= end; i++) {
            const url = _records[i].cover_image_url || _records[i].thumb_url;
            if (url && !_preloadedUrls.has(url)) {
                _preloadedUrls.add(url);
                var img = new Image();
                img.src = url;
            }
        }
    }

    // --- Navigation ---

    function goTo(index) {
        if (_records.length === 0) return;
        index = clamp(index, 0, _records.length - 1);
        if (index === _currentIndex) return;

        _currentIndex = index;
        reconcileDOM();
        updateInfo();
        preloadNearby();
        hideNavHint();
    }

    function goRelative(delta) {
        goTo(_currentIndex + delta);
    }

    function hideNavHint() {
        if (_navHint && !_navHint.classList.contains('hidden')) {
            _navHint.classList.add('hidden');
        }
    }

    // --- Event Handlers ---

    function onKeydown(e) {
        // Don't capture keys if modal is open or input is focused
        if (document.querySelector('.modal-overlay.active')) return;
        var tag = document.activeElement && document.activeElement.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;

        // Only handle when coverflow is visible
        if (!_container || !_container.classList.contains('active')) return;

        if (e.key === 'ArrowLeft') {
            e.preventDefault();
            goRelative(-1);
        } else if (e.key === 'ArrowRight') {
            e.preventDefault();
            goRelative(1);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            if (_records.length > 0 && _onOpenModal) {
                _onOpenModal(_records[_currentIndex]);
            }
        } else if (e.key === 'Home') {
            e.preventDefault();
            goTo(0);
        } else if (e.key === 'End') {
            e.preventDefault();
            goTo(_records.length - 1);
        } else if (e.key === 'PageUp') {
            e.preventDefault();
            goRelative(-10);
        } else if (e.key === 'PageDown') {
            e.preventDefault();
            goRelative(10);
        }
    }

    function onWheel(e) {
        if (!_container || !_container.classList.contains('active')) return;

        // Prevent page scroll
        e.preventDefault();

        var now = Date.now();
        // Determine scroll direction — use deltaX for horizontal trackpad, deltaY otherwise
        var delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;

        _wheelAccum += delta;

        if (now - _lastWheelTime < CFG.DEBOUNCE_WHEEL_MS) return;
        _lastWheelTime = now;

        // Threshold for a step — handle both fine (trackpad) and coarse (mouse wheel) scrolling
        var threshold = (e.deltaMode === 1) ? 3 : CFG.WHEEL_THRESHOLD;
        if (Math.abs(_wheelAccum) >= threshold) {
            var steps = _wheelAccum > 0 ? 1 : -1;
            _wheelAccum = 0;
            goRelative(steps);
        }
    }

    function onTouchStart(e) {
        if (!_container || !_container.classList.contains('active')) return;
        if (e.touches.length !== 1) return;

        _touchStartX = e.touches[0].clientX;
        _touchStartY = e.touches[0].clientY;
        _touchMoved = false;
    }

    function onTouchMove(e) {
        if (!_container || !_container.classList.contains('active')) return;
        _touchMoved = true;
    }

    function onTouchEnd(e) {
        if (!_container || !_container.classList.contains('active')) return;
        if (!_touchMoved) return;

        var dx = e.changedTouches[0].clientX - _touchStartX;
        var dy = e.changedTouches[0].clientY - _touchStartY;

        // Only respond to horizontal swipes
        if (Math.abs(dx) > Math.abs(dy) && Math.abs(dx) > 30) {
            e.preventDefault();
            // Swipe right → go left (previous), swipe left → go right (next)
            var steps = dx > 0 ? -1 : 1;
            // For longer swipes, move more
            if (Math.abs(dx) > 120) steps *= 3;
            else if (Math.abs(dx) > 70) steps *= 2;
            goRelative(steps);
        }
    }

    // --- Public API ---

    function init(containerEl, records, options) {
        _destroyed = false;
        _container = containerEl;
        _records = records || [];
        _onOpenModal = (options && options.onOpenModal) || null;
        _currentIndex = 0;
        _renderedItems = new Map();
        _preloadedUrls = new Set();

        // Build DOM structure
        _container.innerHTML = '';

        if (_records.length === 0) {
            _container.innerHTML =
                '<div class="coverflow-empty">' +
                '<div class="icon">🎵</div>' +
                '<p>No records in your collection yet.</p>' +
                '</div>';
            return;
        }

        _stage = document.createElement('div');
        _stage.className = 'coverflow-stage';

        _track = document.createElement('div');
        _track.className = 'coverflow-track';
        _stage.appendChild(_track);

        // Left/right nav arrows
        var leftArrow = document.createElement('button');
        leftArrow.className = 'cf-nav-arrow cf-nav-left';
        leftArrow.innerHTML = '&#8249;'; // ‹
        leftArrow.setAttribute('aria-label', 'Previous album');
        leftArrow.addEventListener('click', function () { goRelative(-1); });
        _stage.appendChild(leftArrow);

        var rightArrow = document.createElement('button');
        rightArrow.className = 'cf-nav-arrow cf-nav-right';
        rightArrow.innerHTML = '&#8250;'; // ›
        rightArrow.setAttribute('aria-label', 'Next album');
        rightArrow.addEventListener('click', function () { goRelative(1); });
        _stage.appendChild(rightArrow);

        _container.appendChild(_stage);

        _infoPanel = buildInfoPanel();
        _container.appendChild(_infoPanel);

        _navHint = buildNavHint();
        _container.appendChild(_navHint);

        // Auto-hide nav hint
        setTimeout(function () {
            hideNavHint();
        }, CFG.NAV_HINT_HIDE_MS);

        // Initial render
        reconcileDOM();
        updateInfo();
        preloadNearby();

        // Bind events
        _boundKeydown = onKeydown;
        _boundWheel = onWheel;
        _boundTouchStart = onTouchStart;
        _boundTouchMove = onTouchMove;
        _boundTouchEnd = onTouchEnd;

        document.addEventListener('keydown', _boundKeydown);
        _container.addEventListener('wheel', _boundWheel, { passive: false });
        _container.addEventListener('touchstart', _boundTouchStart, { passive: true });
        _container.addEventListener('touchmove', _boundTouchMove, { passive: true });
        _container.addEventListener('touchend', _boundTouchEnd, { passive: false });
    }

    function getCurrentIndex() {
        return _currentIndex;
    }

    function getRecordAtIndex(index) {
        return _records[index] || null;
    }

    function destroy() {
        _destroyed = true;

        if (_boundKeydown) document.removeEventListener('keydown', _boundKeydown);
        if (_container && _boundWheel) _container.removeEventListener('wheel', _boundWheel);
        if (_container && _boundTouchStart) _container.removeEventListener('touchstart', _boundTouchStart);
        if (_container && _boundTouchMove) _container.removeEventListener('touchmove', _boundTouchMove);
        if (_container && _boundTouchEnd) _container.removeEventListener('touchend', _boundTouchEnd);

        _renderedItems.clear();
        if (_container) _container.innerHTML = '';

        _container = null;
        _stage = null;
        _track = null;
        _infoPanel = null;
        _navHint = null;
        _records = [];
    }

    return {
        init: init,
        goTo: goTo,
        getCurrentIndex: getCurrentIndex,
        getRecordAtIndex: getRecordAtIndex,
        destroy: destroy,
    };

})();
