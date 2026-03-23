/* Wizards Engine — DataTable component
 *
 * Sortable, filterable table with responsive card layout for mobile.
 * Used by GM Feed, Game Objects browser, Sessions, and Queue Groups.
 *
 * Usage:
 *   var table = new window.components.DataTable(containerEl, {
 *     columns:    [...],        // column config array (required)
 *     onRowClick: fn,           // called with rowData when a row is activated
 *     rowActions: [...],        // action button config array (optional)
 *     emptyMessage: '...',      // shown when no rows match filters (optional)
 *   });
 *   table.setRows(arrayOfObjects);  // populate or replace data
 *   table.setLoading(true|false);   // show/hide loading skeleton
 *   table.destroy();                // remove listeners, clear container
 *
 * Column config object:
 *   {
 *     key:      'fieldName',          // property name on row data
 *     label:    'Column Header',      // display label
 *     sortable: true|false,           // click header to sort (default false)
 *     filter:   'text'|'select'|null, // filter control type (default null)
 *     render:   function(value, row), // optional custom renderer; returns HTML string
 *     width:    '120px',             // optional CSS width
 *     linkTo:   function(row),        // optional; if provided, wraps cell in <a href>
 *     hideMobile: true|false,         // hide column on mobile (<600px) (default false)
 *   }
 *
 * Row action config object:
 *   {
 *     label:    'Edit',              // button text
 *     callback: function(rowData),   // called when button is clicked
 *     className: 'outline secondary', // optional extra classes on the <button>
 *   }
 *
 * ARIA: role="grid", aria-sort on sorted header, scope="col" on all headers.
 * Keyboard: arrow keys navigate rows, Enter activates onRowClick, tab between filters.
 * Responsive: table on desktop (>=600px), stacked cards on mobile (<600px).
 *
 * Registers as window.components.DataTable.
 *
 * Dependencies (must be loaded before this file):
 *   utils.js — window.utils.esc
 */

window.components = window.components || {};

/**
 * DataTable constructor.
 *
 * @param {HTMLElement} containerEl — the element to render into
 * @param {object}      options
 * @param {Array}       options.columns       — column config array
 * @param {function}    [options.onRowClick]  — called with row data on activation
 * @param {Array}       [options.rowActions]  — action button config array
 * @param {string}      [options.emptyMessage] — empty state text
 */
window.components.DataTable = function DataTable(containerEl, options) {
  var _container   = containerEl;
  var _alive       = true;
  var _options     = options || {};
  var _columns     = _options.columns || [];
  var _onRowClick  = typeof _options.onRowClick === "function" ? _options.onRowClick : null;
  var _rowActions  = Array.isArray(_options.rowActions) ? _options.rowActions : [];
  var _emptyMsg    = _options.emptyMessage || "No items found.";

  // Internal state
  var _rows        = [];   // full dataset supplied by caller
  var _loading     = false;
  var _sortKey     = null; // currently sorted column key
  var _sortDir     = "asc"; // "asc" | "desc"
  var _globalFilter = "";  // global text search value
  var _colFilters  = {};   // per-column select filter values { key: value }

  // Track delegated event listener so we can remove it on destroy
  var _clickListener = null;
  var _keydownListener = null;
  var _filterListeners = []; // { el, type, fn } tuples

  // --------------------------------------------------------------------------
  // Private helpers
  // --------------------------------------------------------------------------

  var _esc = function (s) { return window.utils.esc(s); };

  /**
   * Return the value of a nested key path like "a.b.c" from an object.
   * Also handles flat keys.
   * @param {object} obj
   * @param {string} key
   * @returns {*}
   */
  function _getValue(obj, key) {
    if (!obj || !key) return "";
    if (key.indexOf(".") === -1) return obj[key];
    var parts = key.split(".");
    var val = obj;
    for (var i = 0; i < parts.length; i++) {
      if (val == null) return "";
      val = val[parts[i]];
    }
    return val;
  }

  /**
   * Convert a value to a lowercase string for comparison.
   * @param {*} v
   * @returns {string}
   */
  function _str(v) {
    if (v == null) return "";
    return String(v).toLowerCase();
  }

  /**
   * Apply current sort, global filter, and per-column filters to _rows.
   * @returns {Array} filtered and sorted subset
   */
  function _applyFilters() {
    var result = _rows.slice();

    // Per-column select filters
    var colKeys = Object.keys(_colFilters);
    for (var c = 0; c < colKeys.length; c++) {
      var ck = colKeys[c];
      var cv = _colFilters[ck];
      if (!cv) continue;
      result = result.filter(function (row) {
        return _str(_getValue(row, ck)) === _str(cv);
      });
    }

    // Global text filter — searches all column values
    if (_globalFilter) {
      var needle = _globalFilter.toLowerCase();
      result = result.filter(function (row) {
        for (var ci = 0; ci < _columns.length; ci++) {
          var cellVal = _getValue(row, _columns[ci].key);
          if (_str(cellVal).indexOf(needle) !== -1) return true;
        }
        return false;
      });
    }

    // Sort
    if (_sortKey) {
      var sk = _sortKey;
      var dir = _sortDir === "asc" ? 1 : -1;
      result.sort(function (a, b) {
        var av = _str(_getValue(a, sk));
        var bv = _str(_getValue(b, sk));
        if (av < bv) return -1 * dir;
        if (av > bv) return 1 * dir;
        return 0;
      });
    }

    return result;
  }

  /**
   * Collect distinct display values for a column (for select filter options).
   * @param {string} key
   * @returns {Array<string>}
   */
  function _distinctValues(key) {
    var seen = {};
    var vals = [];
    for (var i = 0; i < _rows.length; i++) {
      var v = String(_getValue(_rows[i], key) || "");
      if (!seen[v]) {
        seen[v] = true;
        vals.push(v);
      }
    }
    vals.sort();
    return vals;
  }

  // --------------------------------------------------------------------------
  // Rendering — filter bar
  // --------------------------------------------------------------------------

  /**
   * Build the filter bar HTML (global search + per-column selects).
   * @returns {string} HTML
   */
  function _renderFilterBar() {
    var hasAnyFilter = false;
    for (var i = 0; i < _columns.length; i++) {
      if (_columns[i].filter) { hasAnyFilter = true; break; }
    }

    var html = '<div class="dt-filters" role="search">';

    // Global text filter
    html +=
      '<label class="dt-filter-global">' +
        '<span class="dt-filter-label">Search</span>' +
        '<input type="search"' +
        '       class="dt-filter-input"' +
        '       data-dt-filter="global"' +
        '       placeholder="Filter..."' +
        '       value="' + _esc(_globalFilter) + '"' +
        '       aria-label="Filter all columns">' +
      '</label>';

    // Per-column filters
    for (var ci = 0; ci < _columns.length; ci++) {
      var col = _columns[ci];
      if (!col.filter) continue;

      if (col.filter === "select") {
        var vals = _distinctValues(col.key);
        var current = _colFilters[col.key] || "";
        html +=
          '<label class="dt-filter-select-wrap">' +
            '<span class="dt-filter-label">' + _esc(col.label) + '</span>' +
            '<select class="dt-filter-select"' +
            '        data-dt-filter="select"' +
            '        data-dt-col="' + _esc(col.key) + '"' +
            '        aria-label="Filter by ' + _esc(col.label) + '">' +
              '<option value="">All</option>';
        for (var vi = 0; vi < vals.length; vi++) {
          html +=
            '<option value="' + _esc(vals[vi]) + '"' +
            (current === vals[vi] ? ' selected' : '') + '>' +
            _esc(vals[vi]) +
            '</option>';
        }
        html += '</select></label>';

      } else if (col.filter === "text") {
        html +=
          '<label class="dt-filter-col-wrap">' +
            '<span class="dt-filter-label">' + _esc(col.label) + '</span>' +
            '<input type="search"' +
            '       class="dt-filter-input"' +
            '       data-dt-filter="col-text"' +
            '       data-dt-col="' + _esc(col.key) + '"' +
            '       placeholder="' + _esc(col.label) + '..."' +
            '       value="' + _esc(_colFilters[col.key] || "") + '"' +
            '       aria-label="Filter by ' + _esc(col.label) + '">' +
          '</label>';
      }
    }

    html += '</div>';
    return html;
  }

  // --------------------------------------------------------------------------
  // Rendering — table (desktop)
  // --------------------------------------------------------------------------

  /**
   * Build the <thead> HTML.
   * @returns {string} HTML
   */
  function _renderThead() {
    var html = '<thead><tr>';
    for (var i = 0; i < _columns.length; i++) {
      var col = _columns[i];
      var ariaSortAttr = "";
      var sortIndicator = "";
      var sortClass = "";
      if (col.sortable) {
        if (_sortKey === col.key) {
          ariaSortAttr = ' aria-sort="' + (_sortDir === "asc" ? "ascending" : "descending") + '"';
          sortIndicator = _sortDir === "asc" ? " \u25b2" : " \u25bc"; // ▲ or ▼
          sortClass = " dt-th--sorted";
        } else {
          ariaSortAttr = ' aria-sort="none"';
        }
      }
      var hideClass = col.hideMobile ? " dt-th--hide-mobile" : "";
      var widthStyle = col.width ? ' style="width:' + _esc(col.width) + '"' : "";
      html +=
        '<th class="dt-th' + sortClass + hideClass + '"' +
            ' scope="col"' +
            ariaSortAttr +
            widthStyle +
            (col.sortable ? ' data-dt-sort="' + _esc(col.key) + '" tabindex="0" role="columnheader"' : ' role="columnheader"') +
            '>' +
          _esc(col.label) + sortIndicator +
        '</th>';
    }
    if (_rowActions.length > 0) {
      html += '<th class="dt-th dt-th--actions" scope="col" role="columnheader">Actions</th>';
    }
    html += '</tr></thead>';
    return html;
  }

  /**
   * Render a single table cell's content.
   * If the column has a render() function, delegate to it.
   * If the column has linkTo(), wrap in an <a>.
   * @param {object} col
   * @param {object} row
   * @returns {string} HTML
   */
  function _renderCell(col, row) {
    var rawVal = _getValue(row, col.key);
    var cellHtml;
    if (typeof col.render === "function") {
      cellHtml = col.render(rawVal, row);
    } else {
      cellHtml = _esc(rawVal == null ? "" : String(rawVal));
    }
    if (typeof col.linkTo === "function") {
      var href = col.linkTo(row);
      cellHtml = '<a href="' + _esc(href) + '" class="dt-cell-link">' + cellHtml + '</a>';
    }
    return cellHtml;
  }

  /**
   * Build action buttons HTML for a row.
   * @param {object} row
   * @param {number} rowIdx — index in the filtered rows array (for data attributes)
   * @returns {string} HTML
   */
  function _renderRowActions(row, rowIdx) {
    if (_rowActions.length === 0) return "";
    var html = '<td class="dt-td dt-td--actions">';
    for (var ai = 0; ai < _rowActions.length; ai++) {
      var action = _rowActions[ai];
      var extraClass = action.className ? " " + action.className : "";
      html +=
        '<button class="dt-action-btn' + _esc(extraClass) + '"' +
        '        data-dt-action="' + ai + '"' +
        '        data-dt-row="' + rowIdx + '">' +
          _esc(action.label) +
        '</button>';
    }
    html += '</td>';
    return html;
  }

  /**
   * Build the <tbody> HTML for the filtered/sorted rows.
   * @param {Array} rows — filtered and sorted rows
   * @returns {string} HTML
   */
  function _renderTbody(rows) {
    if (rows.length === 0) {
      var colspan = _columns.length + (_rowActions.length > 0 ? 1 : 0);
      return (
        '<tbody>' +
          '<tr class="dt-row dt-row--empty">' +
            '<td class="dt-td dt-td--empty" colspan="' + colspan + '">' +
              _esc(_emptyMsg) +
            '</td>' +
          '</tr>' +
        '</tbody>'
      );
    }

    var html = '<tbody>';
    for (var ri = 0; ri < rows.length; ri++) {
      var row = rows[ri];
      var clickable = _onRowClick ? ' tabindex="0" data-dt-row="' + ri + '"' : "";
      html += '<tr class="dt-row' + (_onRowClick ? " dt-row--clickable" : "") + '"' + clickable + '>';
      for (var ci = 0; ci < _columns.length; ci++) {
        var col = _columns[ci];
        var hideClass = col.hideMobile ? " dt-td--hide-mobile" : "";
        html +=
          '<td class="dt-td' + hideClass + '">' +
            _renderCell(col, row) +
          '</td>';
      }
      html += _renderRowActions(row, ri);
      html += '</tr>';
    }
    html += '</tbody>';
    return html;
  }

  // --------------------------------------------------------------------------
  // Rendering — mobile card layout
  // --------------------------------------------------------------------------

  /**
   * Build stacked card HTML for a single row (mobile view).
   * @param {object} row
   * @param {number} rowIdx
   * @returns {string} HTML
   */
  function _renderCard(row, rowIdx) {
    var clickable = _onRowClick
      ? ' tabindex="0" data-dt-row="' + rowIdx + '" role="button"'
      : "";
    var html = '<div class="dt-card' + (_onRowClick ? " dt-card--clickable" : "") + '"' + clickable + '>';
    for (var ci = 0; ci < _columns.length; ci++) {
      var col = _columns[ci];
      html +=
        '<div class="dt-card__field">' +
          '<span class="dt-card__label">' + _esc(col.label) + '</span>' +
          '<span class="dt-card__value">' + _renderCell(col, row) + '</span>' +
        '</div>';
    }
    if (_rowActions.length > 0) {
      html += '<div class="dt-card__actions">';
      for (var ai = 0; ai < _rowActions.length; ai++) {
        var action = _rowActions[ai];
        var extraClass = action.className ? " " + action.className : "";
        html +=
          '<button class="dt-action-btn' + _esc(extraClass) + '"' +
          '        data-dt-action="' + ai + '"' +
          '        data-dt-row="' + rowIdx + '">' +
            _esc(action.label) +
          '</button>';
      }
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  /**
   * Build the card list HTML for all filtered/sorted rows.
   * @param {Array} rows
   * @returns {string} HTML
   */
  function _renderCardList(rows) {
    if (rows.length === 0) {
      return '<p class="dt-empty">' + _esc(_emptyMsg) + '</p>';
    }
    var html = '<div class="dt-cards">';
    for (var ri = 0; ri < rows.length; ri++) {
      html += _renderCard(rows[ri], ri);
    }
    html += '</div>';
    return html;
  }

  // --------------------------------------------------------------------------
  // Rendering — loading skeleton
  // --------------------------------------------------------------------------

  /**
   * Build a loading skeleton shimmer HTML.
   * @returns {string} HTML
   */
  function _renderSkeleton() {
    var html = '<div class="dt-skeleton" aria-busy="true" aria-label="Loading...">';
    for (var i = 0; i < 5; i++) {
      html += '<div class="dt-skeleton__row">';
      for (var ci = 0; ci < Math.min(_columns.length, 4); ci++) {
        html += '<div class="dt-skeleton__cell"></div>';
      }
      html += '</div>';
    }
    html += '</div>';
    return html;
  }

  // --------------------------------------------------------------------------
  // Rendering — main render
  // --------------------------------------------------------------------------

  /**
   * Stores a reference to the filtered rows used in the last render.
   * Used by event handlers to look up row data by index.
   */
  var _filteredRows = [];

  /**
   * Re-render the entire component into _container.
   */
  function _render() {
    if (!_container || !_alive) return;

    _unwireEvents();

    if (_loading && _rows.length === 0) {
      _container.innerHTML = _renderSkeleton();
      return;
    }

    _filteredRows = _applyFilters();

    var html = '<div class="dt-root">';
    html += _renderFilterBar();

    // Table layout (hidden on mobile via CSS, shown on desktop)
    html +=
      '<div class="dt-table-wrap">' +
        '<table class="dt-table" role="grid">' +
          _renderThead() +
          _renderTbody(_filteredRows) +
        '</table>' +
      '</div>';

    // Card layout (shown on mobile, hidden on desktop via CSS)
    html +=
      '<div class="dt-cards-wrap">' +
        _renderCardList(_filteredRows) +
      '</div>';

    html += '</div>'; // .dt-root

    _container.innerHTML = html;
    _wireEvents();
  }

  // --------------------------------------------------------------------------
  // Event wiring
  // --------------------------------------------------------------------------

  /**
   * Remove all delegated listeners previously added by _wireEvents().
   */
  function _unwireEvents() {
    if (_clickListener) {
      _container.removeEventListener("click", _clickListener);
      _clickListener = null;
    }
    if (_keydownListener) {
      _container.removeEventListener("keydown", _keydownListener);
      _keydownListener = null;
    }
    for (var i = 0; i < _filterListeners.length; i++) {
      var item = _filterListeners[i];
      item.el.removeEventListener(item.type, item.fn);
    }
    _filterListeners = [];
  }

  /**
   * Activate a row by index — fires onRowClick if set.
   * @param {number} rowIdx — index into _filteredRows
   */
  function _activateRow(rowIdx) {
    if (!_onRowClick) return;
    var row = _filteredRows[rowIdx];
    if (row != null) {
      _onRowClick(row);
    }
  }

  /**
   * Wire delegated click and keyboard listeners on the container.
   */
  function _wireEvents() {
    // ---- Click delegation ------------------------------------------------
    _clickListener = function (evt) {
      var target = evt.target;

      // Row action button
      var actionBtn = target.closest ? target.closest("[data-dt-action]") : null;
      if (actionBtn) {
        evt.stopPropagation();
        var actionIdx = parseInt(actionBtn.getAttribute("data-dt-action"), 10);
        var rowIdx    = parseInt(actionBtn.getAttribute("data-dt-row"), 10);
        var action = _rowActions[actionIdx];
        var row    = _filteredRows[rowIdx];
        if (action && typeof action.callback === "function" && row != null) {
          action.callback(row);
        }
        return;
      }

      // Sortable column header
      var th = target.closest ? target.closest("[data-dt-sort]") : null;
      if (th) {
        var key = th.getAttribute("data-dt-sort");
        if (key === _sortKey) {
          _sortDir = _sortDir === "asc" ? "desc" : "asc";
        } else {
          _sortKey = key;
          _sortDir = "asc";
        }
        _render();
        return;
      }

      // Clickable table row (tbody tr)
      var tr = target.closest ? target.closest("tr[data-dt-row]") : null;
      if (tr && !target.closest("[data-dt-action]")) {
        _activateRow(parseInt(tr.getAttribute("data-dt-row"), 10));
        return;
      }

      // Clickable card (mobile)
      var card = target.closest ? target.closest(".dt-card[data-dt-row]") : null;
      if (card && !target.closest("[data-dt-action]")) {
        _activateRow(parseInt(card.getAttribute("data-dt-row"), 10));
        return;
      }
    };
    _container.addEventListener("click", _clickListener);

    // ---- Keyboard delegation ---------------------------------------------
    _keydownListener = function (evt) {
      var target = evt.target;

      // Sortable header — Enter or Space to sort
      if (target.hasAttribute && target.hasAttribute("data-dt-sort")) {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          target.click();
          return;
        }
      }

      // Row / card — Enter to activate
      if (evt.key === "Enter" &&
          (target.hasAttribute("data-dt-row") || (target.closest && target.closest("[data-dt-row]")))) {
        var rowEl = target.hasAttribute("data-dt-row")
          ? target
          : (target.closest ? target.closest("[data-dt-row]") : null);
        if (rowEl && !target.closest("[data-dt-action]")) {
          evt.preventDefault();
          _activateRow(parseInt(rowEl.getAttribute("data-dt-row"), 10));
          return;
        }
      }

      // Arrow key navigation between table rows / cards
      if (evt.key === "ArrowDown" || evt.key === "ArrowUp") {
        var focusedRow = target.closest ? target.closest("[data-dt-row]") : null;
        if (!focusedRow) return;
        evt.preventDefault();
        var allRows = _container.querySelectorAll(
          "tr[data-dt-row], .dt-card[data-dt-row]"
        );
        var currentIdx = -1;
        for (var i = 0; i < allRows.length; i++) {
          if (allRows[i] === focusedRow || allRows[i].contains(target)) {
            currentIdx = i;
            break;
          }
        }
        var delta = evt.key === "ArrowDown" ? 1 : -1;
        var nextIdx = currentIdx + delta;
        if (nextIdx >= 0 && nextIdx < allRows.length) {
          allRows[nextIdx].focus();
        }
      }
    };
    _container.addEventListener("keydown", _keydownListener);

    // ---- Filter inputs ---------------------------------------------------

    // Global search
    var globalInput = _container.querySelector('[data-dt-filter="global"]');
    if (globalInput) {
      var globalFn = function (evt) {
        _globalFilter = evt.target.value;
        _render();
      };
      globalInput.addEventListener("input", globalFn);
      _filterListeners.push({ el: globalInput, type: "input", fn: globalFn });
    }

    // Per-column text filters
    var colTextInputs = _container.querySelectorAll('[data-dt-filter="col-text"]');
    for (var ti = 0; ti < colTextInputs.length; ti++) {
      (function (input) {
        var fn = function (evt) {
          var col = input.getAttribute("data-dt-col");
          _colFilters[col] = evt.target.value;
          _render();
        };
        input.addEventListener("input", fn);
        _filterListeners.push({ el: input, type: "input", fn: fn });
      })(colTextInputs[ti]);
    }

    // Per-column select filters
    var selects = _container.querySelectorAll('[data-dt-filter="select"]');
    for (var si = 0; si < selects.length; si++) {
      (function (select) {
        var fn = function (evt) {
          var col = select.getAttribute("data-dt-col");
          _colFilters[col] = evt.target.value;
          _render();
        };
        select.addEventListener("change", fn);
        _filterListeners.push({ el: select, type: "change", fn: fn });
      })(selects[si]);
    }
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  var _self = {
    /**
     * Replace the table data and re-render.
     * @param {Array} rows — array of row data objects
     */
    setRows: function (rows) {
      _rows    = Array.isArray(rows) ? rows : [];
      _loading = false;
      _render();
    },

    /**
     * Toggle the loading skeleton state.
     * Pass true before fetching data; false (or call setRows) when done.
     * @param {boolean} isLoading
     */
    setLoading: function (isLoading) {
      _loading = !!isLoading;
      if (_loading) {
        _rows = [];
        _render();
      }
    },

    /**
     * Destroy this instance: remove listeners and clear the container.
     */
    destroy: function () {
      _alive = false;
      _unwireEvents();
      if (_container) {
        _container.innerHTML = "";
      }
    },
  };

  // Perform an initial render (shows empty or skeleton state)
  _render();

  return _self;
};
