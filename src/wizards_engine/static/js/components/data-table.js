/* Wizards Engine — DataTable component
 *
 * Reusable sortable, filterable data table component.
 *
 * Usage:
 *   var dt = new window.components.DataTable(containerEl, {
 *     columns: [
 *       { key: 'name', label: 'Name', sortable: true },
 *       { key: 'type', label: 'Type', sortable: true, filter: 'select' },
 *       { key: 'note', label: 'Note', render: function(val, row) { return '<em>' + val + '</em>'; } },
 *     ],
 *     onRowClick: function(row) { router.navigate('#/detail/' + row.id); },
 *     emptyMessage: 'No items found.',
 *   });
 *   dt.setRows(arrayOfObjects);   // renders / replaces all rows
 *   dt.appendRows(arrayOfObjects); // appends without clearing
 *   dt.destroy();                 // unmount and remove listeners
 *
 * Column config keys:
 *   key         {string}   — property name from row data object
 *   label       {string}   — column header text
 *   sortable    {boolean}  — click header to sort (default false)
 *   filter      {string}   — 'text' | 'select' | undefined — per-column filter
 *   render      {function} — (value, row) => HTML string
 *   width       {string}   — CSS width e.g. '120px'
 *   hideMobile  {boolean}  — hide column below 600px (default false)
 *   linkTo      {function} — (row) => hash string for row-level link
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
 * @param {HTMLElement} containerEl — element to render into
 * @param {object} opts
 * @param {Array}    opts.columns      — column config array (see above)
 * @param {function} [opts.onRowClick] — called with row data on row click
 * @param {string}   [opts.emptyMessage] — message when no rows match filters
 */
window.components.DataTable = function DataTable(containerEl, opts) {
  var _container = containerEl;
  var _columns   = (opts && opts.columns)      || [];
  var _onRowClick = (opts && opts.onRowClick)  || null;
  var _emptyMsg  = (opts && opts.emptyMessage) || "No items found.";
  var _alive     = true;

  // All rows (unfiltered, unsorted).
  var _rows = [];

  // Current sort state.
  var _sortKey = null;
  var _sortDir = "asc"; // 'asc' | 'desc'

  // Current global text filter value.
  var _globalFilter = "";

  // Per-column select filter values { columnKey: selectedValue }.
  var _selectFilters = {};

  // Derived: rows after applying all filters and sort.
  var _visibleRows = [];

  var _esc = function (s) { return window.utils.esc(s); };

  // --------------------------------------------------------------------------
  // Filter + sort logic
  // --------------------------------------------------------------------------

  /**
   * Recompute _visibleRows from _rows, current filters, and current sort.
   */
  function _recompute() {
    var rows = _rows.slice();

    // Global text filter — case-insensitive match against all string values.
    if (_globalFilter) {
      var needle = _globalFilter.toLowerCase();
      rows = rows.filter(function (row) {
        for (var i = 0; i < _columns.length; i++) {
          var col = _columns[i];
          var val = row[col.key];
          if (val !== undefined && val !== null) {
            if (String(val).toLowerCase().indexOf(needle) !== -1) {
              return true;
            }
          }
        }
        return false;
      });
    }

    // Per-column select filters.
    for (var key in _selectFilters) {
      if (!_selectFilters.hasOwnProperty(key)) continue;
      var filterVal = _selectFilters[key];
      if (!filterVal) continue;
      rows = rows.filter(function (row) {
        return String(row[key] === undefined || row[key] === null ? "" : row[key]) === filterVal;
      });
    }

    // Sort.
    if (_sortKey) {
      var dir = _sortDir === "desc" ? -1 : 1;
      var sk = _sortKey;
      rows.sort(function (a, b) {
        var av = a[sk] === undefined || a[sk] === null ? "" : a[sk];
        var bv = b[sk] === undefined || b[sk] === null ? "" : b[sk];
        if (typeof av === "number" && typeof bv === "number") {
          return dir * (av - bv);
        }
        av = String(av).toLowerCase();
        bv = String(bv).toLowerCase();
        if (av < bv) return -dir;
        if (av > bv) return dir;
        return 0;
      });
    }

    _visibleRows = rows;
  }

  // --------------------------------------------------------------------------
  // HTML building helpers
  // --------------------------------------------------------------------------

  /**
   * Build the filter bar HTML (global text + per-column selects).
   * @returns {string}
   */
  function _buildFilterBar() {
    var hasSelectFilters = false;
    for (var i = 0; i < _columns.length; i++) {
      if (_columns[i].filter === "select") { hasSelectFilters = true; break; }
    }

    var html = '<div class="dt-filters">';

    // Global text search input.
    html +=
      '<div class="dt-filter-global">' +
        '<input type="search" id="dt-global-filter" class="dt-search-input"' +
          ' placeholder="Filter..." aria-label="Filter rows"' +
          ' value="' + _esc(_globalFilter) + '">' +
      '</div>';

    // Per-column select dropdowns.
    if (hasSelectFilters) {
      for (var j = 0; j < _columns.length; j++) {
        var col = _columns[j];
        if (col.filter !== "select") continue;

        // Collect distinct values.
        var seen = {};
        var vals = [];
        for (var k = 0; k < _rows.length; k++) {
          var v = _rows[k][col.key];
          var sv = v === undefined || v === null ? "" : String(v);
          if (!seen[sv]) {
            seen[sv] = true;
            vals.push(sv);
          }
        }
        vals.sort();

        var current = _selectFilters[col.key] || "";
        html +=
          '<div class="dt-filter-select">' +
            '<select id="dt-filter-' + _esc(col.key) + '" class="dt-select"' +
              ' aria-label="Filter by ' + _esc(col.label) + '"' +
              ' data-col="' + _esc(col.key) + '">' +
              '<option value="">All ' + _esc(col.label) + '</option>';

        for (var m = 0; m < vals.length; m++) {
          html +=
            '<option value="' + _esc(vals[m]) + '"' +
            (vals[m] === current ? ' selected' : '') +
            '>' + _esc(vals[m] || "(blank)") + '</option>';
        }

        html += '</select></div>';
      }
    }

    html += '</div>';
    return html;
  }

  /**
   * Build the table header HTML.
   * @returns {string}
   */
  function _buildHeader() {
    var html = '<thead><tr role="row">';
    for (var i = 0; i < _columns.length; i++) {
      var col = _columns[i];
      var mobileClass = col.hideMobile ? " dt-th--hide-mobile" : "";
      var sortAttr = "";
      var sortIndicator = "";

      if (col.sortable) {
        var isSorted = col.key === _sortKey;
        var ariaSortVal = isSorted ? (_sortDir === "asc" ? "ascending" : "descending") : "none";
        sortAttr =
          ' tabindex="0"' +
          ' data-sort="' + _esc(col.key) + '"' +
          ' aria-sort="' + ariaSortVal + '"' +
          ' role="columnheader button"';
        if (isSorted) {
          sortIndicator = _sortDir === "asc" ? " &#x25B2;" : " &#x25BC;";
        } else {
          sortIndicator = ' <span class="dt-sort-icon">&#x21C5;</span>';
        }
      }

      var widthAttr = col.width ? ' style="width:' + _esc(col.width) + '"' : "";

      html +=
        '<th class="dt-th' + mobileClass + '"' +
        widthAttr +
        sortAttr +
        ' scope="col">' +
        _esc(col.label) +
        sortIndicator +
        '</th>';
    }
    html += '</tr></thead>';
    return html;
  }

  /**
   * Build the table body HTML from _visibleRows.
   * @returns {string}
   */
  function _buildBody() {
    if (_visibleRows.length === 0) {
      var colspan = _columns.length;
      return (
        '<tbody>' +
          '<tr class="dt-empty-row"><td colspan="' + colspan + '" class="dt-empty-cell">' +
          _esc(_emptyMsg) +
          '</td></tr>' +
        '</tbody>'
      );
    }

    var html = '<tbody>';
    for (var i = 0; i < _visibleRows.length; i++) {
      var row = _visibleRows[i];
      var rowId = row.id ? ' data-row-id="' + _esc(String(row.id)) + '"' : "";
      var clickable = _onRowClick ? ' class="dt-row dt-row--clickable" tabindex="0"' : ' class="dt-row"';

      html += '<tr' + clickable + rowId + ' role="row">';

      for (var j = 0; j < _columns.length; j++) {
        var col = _columns[j];
        var mobileClass = col.hideMobile ? " dt-td--hide-mobile" : "";
        var val = row[col.key];
        var cellHtml;

        if (col.render) {
          // Custom render function — may return raw HTML.
          cellHtml = col.render(val, row);
        } else if (val === undefined || val === null) {
          cellHtml = '<span class="dt-null">—</span>';
        } else {
          cellHtml = _esc(String(val));
        }

        html += '<td class="dt-td' + mobileClass + '">' + cellHtml + '</td>';
      }

      html += '</tr>';
    }

    html += '</tbody>';
    return html;
  }

  // --------------------------------------------------------------------------
  // Full render
  // --------------------------------------------------------------------------

  /**
   * Re-render the entire DataTable into _container.
   */
  function _render() {
    if (!_container || !_alive) return;

    _recompute();

    var html =
      '<div class="dt-root">' +
        _buildFilterBar() +
        '<div class="dt-table-wrapper">' +
          '<table class="dt-table" role="grid">' +
            _buildHeader() +
            _buildBody() +
          '</table>' +
        '</div>' +
      '</div>';

    _container.innerHTML = html;
    _wireEvents();
  }

  // --------------------------------------------------------------------------
  // Event wiring
  // --------------------------------------------------------------------------

  /**
   * Wire all interactive listeners after render.
   * All listeners are delegated to _container for safe rebinding.
   */
  function _wireEvents() {
    if (!_container) return;

    // Global text filter.
    var searchEl = _container.querySelector("#dt-global-filter");
    if (searchEl) {
      searchEl.addEventListener("input", function (e) {
        _globalFilter = e.target.value;
        _render();
        // Restore focus to the search input after re-render.
        var el = _container.querySelector("#dt-global-filter");
        if (el) { el.focus(); el.setSelectionRange(el.value.length, el.value.length); }
      });
    }

    // Per-column select filters.
    var selects = _container.querySelectorAll(".dt-select");
    for (var i = 0; i < selects.length; i++) {
      selects[i].addEventListener("change", function (e) {
        var colKey = e.target.getAttribute("data-col");
        if (colKey) {
          _selectFilters[colKey] = e.target.value;
          _render();
        }
      });
    }

    // Sortable column headers.
    var headers = _container.querySelectorAll("[data-sort]");
    for (var h = 0; h < headers.length; h++) {
      (function (thEl) {
        function doSort() {
          var key = thEl.getAttribute("data-sort");
          if (_sortKey === key) {
            _sortDir = _sortDir === "asc" ? "desc" : "asc";
          } else {
            _sortKey = key;
            _sortDir = "asc";
          }
          _render();
        }
        thEl.addEventListener("click", doSort);
        thEl.addEventListener("keydown", function (e) {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            doSort();
          }
        });
      })(headers[h]);
    }

    // Row click / keyboard.
    if (_onRowClick) {
      var rows = _container.querySelectorAll(".dt-row--clickable");
      for (var r = 0; r < rows.length; r++) {
        (function (trEl) {
          function doRowClick(e) {
            // Don't fire if the click landed on a link or button inside the cell.
            if (e.target.tagName === "A" || e.target.tagName === "BUTTON") return;
            var rowId = trEl.getAttribute("data-row-id");
            if (!rowId) return;
            // Find the row object.
            for (var i = 0; i < _visibleRows.length; i++) {
              if (String(_visibleRows[i].id) === rowId) {
                _onRowClick(_visibleRows[i]);
                break;
              }
            }
          }
          trEl.addEventListener("click", doRowClick);
          trEl.addEventListener("keydown", function (e) {
            if (e.key === "Enter") { e.preventDefault(); doRowClick(e); }
          });
        })(rows[r]);
      }
    }
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  var _self = {
    /**
     * Replace all rows and re-render.
     * @param {Array} rows — array of plain objects
     */
    setRows: function (rows) {
      _rows = Array.isArray(rows) ? rows : [];
      _render();
    },

    /**
     * Append rows to the existing set and re-render.
     * @param {Array} rows
     */
    appendRows: function (rows) {
      if (Array.isArray(rows)) {
        _rows = _rows.concat(rows);
      }
      _render();
    },

    /**
     * Programmatically set the sort column and direction without re-fetching.
     * Useful for syncing UI state when the parent component controls server-side sorting.
     * @param {string} key
     * @param {string} dir — 'asc' | 'desc'
     */
    setSort: function (key, dir) {
      _sortKey = key;
      _sortDir = dir === "desc" ? "desc" : "asc";
      _render();
    },

    /**
     * Destroy this instance. Clears the container and prevents further updates.
     */
    destroy: function () {
      _alive = false;
      if (_container) {
        _container.innerHTML = "";
      }
    },
  };

  return _self;
};
