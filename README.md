# bookledger v2.5

Local-first ebook metadata catalog. **Does not alter ebook files. No AI or login.**

## Installation

```bash
python -m pip install -e .
bookledger serve
```

Open http://127.0.0.1:8787. The prebuilt vanilla frontend is bundled, so **Node.js is not needed to install or run BookLedger**. Existing SQLite catalogs are supported; please make a backup before upgrading.

```bash
bookledger scan-folder "D:/eBooks" --offline
bookledger serve --host 0.0.0.0 # private LAN only; no authentication
```

### Frontend development

The actual application source is `frontend/src/main.js`, `frontend/src/style.css` and `frontend/index.html`; the backend source is `bookledger/webapp.py`. No Python-generated HTML is used in the new frontend.

For development with Vite (optional; requires Node and npm access):

```bash
cd frontend
npm install
npm run dev
```

Run `bookledger serve` in another terminal for the API on port 8787. Vite uses port 5173 and proxies `/api` requests to FastAPI. To make a production bundle: `npm run build`.

**Without npm:** after editing source files, run `python build_frontend.py`. This copies the vanilla assets directly into `bookledger/frontend_dist`. It produces a complete production-usable frontend with no bundler. The included release already contains these assets.

### Structure

- `bookledger/core.py`: scanning, extraction, enrichment, SQLite schema/migrations
- `bookledger/webapp.py`: JSON API, background scan/enrichment jobs and static SPA serving
- `bookledger/legacy_webapp.py`: previous HTML renderer (transitional fallback)
- `bookledger/custom_export.py`: column-selectable CSV exports
- `frontend/`: standalone vanilla ES module UI and CSS
- `bookledger/frontend_dist/`: included production UI assets
- `tests/test_v2_api.py`: new API compatibility and workflow tests

### Scope of the v2 migration

Working v2 pages: library with search, sort, status and visibility filters; book detail and reading-record editor; one-click reading review; Quick Sort with swipes/arrows; series catalog and membership/volume editor; statistics; metadata review; scan status and launch; enrichment status and launch/cancel; presets and custom exports. Book and series cards include right-click context menus, Shift+F10 support, and long-press; selection mode starts from the context menu with a compact bottom toolbar.

Existing routes under `/api` use JSON and can be used by a desktop or phone web client. The legacy renderer remains separately available at `/legacy/` for comparison. Some links inside the legacy HTML use root-relative paths and will navigate to v2; treat it as a transitional fallback rather than the primary interface.

### Export formats

`/api/exports/preset/goodreads` and `/api/exports/preset/storygraph` provide a Goodreads-shaped CSV; `/api/exports/preset/json` provides a full JSON backup. The custom export builder lets you select columns; it does not claim verified native Bookmory/Hardcover import compatibility.

### Security

This is a **personal-use application without authentication**. The server can scan absolute directories accessible to the host and modify your SQLite metadata. Do not expose it to the public internet. Keep it bound to `127.0.0.1` unless you knowingly use a trusted LAN.

### Tests

Run the new v2 API tests:

```bash
python -m pytest tests/test_v2_api.py -q
```

For backward-compatibility tests of the old renderer, import `create_app` from `bookledger.legacy_webapp` rather than the new `bookledger.webapp`. Old tests assert server-rendered HTML on `/`; those are intentionally different in v2 and are not valid assertions against the new SPA shell. The old Python scanning and export core remains unchanged.

**Known limitations:** The interface was rendered with synthetic catalog data at desktop and phone viewport sizes in isolated Chromium and checked for runtime errors and horizontal overflow. A full end-to-end test against a browser accessing your actual local server has not been completed. Long-running job state is in server memory, while metadata results persist in SQLite. Only records currently loaded on-screen can be selected with the bulk bar. Series matching and ebook extraction logic were not rewritten in this frontend migration.

## v2.2: source locations and folder filtering

Book details and Quick Sort now show all indexed source file paths (read-only, including missing-file warnings). The Library's **source folder** filter lists directories from indexed paths and also matches nested subfolders. This is based on metadata already stored in SQLite and requires no rescan or migration. Run `python build_frontend.py` after editing the frontend; the packaged `frontend_dist` is already synced.

## Settings (v2.3)

Open **`/settings`** from the sidebar to manage persisted application preferences. Settings live in the same SQLite database (`app_settings`) and are shared by browsers using that server. The migration is automatic; existing books, reading history, and folder records are preserved.

- **Library:** nested-folder inclusion (on/off), default visibility, sort, page size, card density, cover visibility, status badges.
- **Reading & Quick Sort:** review queue scope, thumbnail visibility, include previously classified books in Quick Sort, show/hide the Quick Sort metadata editor.
- **Scanning & enrichment:** default online lookup, enrichment mode, batch size. These configure future jobs only, never trigger jobs automatically.
- **Exports:** preferred ready-made export preset.

The library filter offers an explicit **nested folders** override. When unchecked, `D:/eBooks/Fantasy` returns only files directly inside that directory; when checked, nested series folders are included. Settings can also be read/updated via `GET /api/settings`, `PATCH /api/settings`, and reset via `POST /api/settings/reset`. Unknown preferences or invalid values return HTTP 422; reset does not delete books.

For developers: frontend source is under `frontend/src`, run `python build_frontend.py` to regenerate `bookledger/frontend_dist` without Node. The original v1 server-rendered HTML tests no longer target the v2 SPA; see `tests/test_settings.py` and the v2 API tests for the new behavior.

## v2.4 additions (2026-10-29)

- Library: activate selection through an item's context menu, choose **assign series** from the bulk bar, and enter an existing or new series name. Existing per-book series indices are cleared for reassignment. No source files change.
- Quick Sort: dedicated batch builder for all books, one series, one folder, or one author; selectable sorting (A–Z, Z–A, random, series volume, author), batch size 1–1000, offset, classified inclusion, and nested-folder inclusion.
- Within a group queue, **sort entire group** can mark all matching books read, not read, or hidden, after confirmation. It uses batches of at most 1000 database updates. Group operations include already-classified visible books and all nested files if selected. Be careful: these actions overwrite existing reading statuses.
- `/api/quick-sort/queue` and `/api/quick-sort/authors` expose the filtered queue and author selections. `/api/books/bulk` now supports `action: assign_series` and `series_name`.

The v2.4 note above is retained for historical context. **v2.5 is built from the latest source archive you uploaded**, not the earlier v2.3 archive.

## v2.5 — full frontend design overhaul (2026-10-30)

A comprehensive visual and interaction redesign built **directly from the source archive supplied by the user**. No Python database migrations or ebook-file modifications were introduced.

- Shared kmab-aligned design tokens, dark surfaces, restrained purple accents, green/amber status semantics, Space Grotesk and Space Mono typography.
- Navigation organized into collection, reading, insights, tools, and system sections; compact icon rail on medium screens and an accessible drawer on phones.
- Cover-led book cards with status indicators, series labels, grid/list switching, expandable library filters, stronger empty states, and contextual actions.
- Rebuilt series overview with search, sort by size/progress/ordering needs, progress cards, and discoverable per-series menus.
- Reading review now has status tabs and pagination (no longer limited to a single fixed first 100 results); covers and one-click classifications remain available.
- Quick Sort retains editable metadata and swipes, with an explicit progress indicator, responsive split layout, and keyboard controls.
- Unified styling for book detail, stats, metadata review, scanning, enrichment, export templates and custom field selection, and settings.
- Improved keyboard context-menu navigation, mobile drawer Escape behavior, visible focus rings, reduced-motion support, more resilient narrow layouts, and screen-reader labels on icon-only navigation.
- The legacy HTML tests now explicitly target the retained `bookledger.legacy_webapp`; new SPA and API tests stay on `bookledger.webapp`.

### Test and preview details

Run `python -m pytest -q` for the complete Python test suite. All 32 tests passed for this release. `node --check frontend/src/main.js` passed. Isolated Chromium rendered the library, series, reading, statistics, settings, book details, and Quick Sort at 1440px and 390px widths with sample data; none showed JavaScript exceptions or horizontal overflow. Context-menu selection, exiting selection, filter expansion, and mobile drawer close were also interactively checked. This is not a guarantee that every device or browser is flawless: verify with your real library and local server.

To rebuild without npm, run `python build_frontend.py`. The packaged `bookledger/frontend_dist` already contains the updated frontend.

## v2.6 — advanced filtering and multi-sort

The filter engine is now **shared** by the Library, Reading Review, Series catalog and membership editor, Quick Sort, Metadata Review, and custom exports. It runs against SQLite; filtering isn't limited to whatever books happen to be visible on-screen.

Open **advanced filters** on any of these pages to:

- Match **all (AND)** or **any (OR)** conditions; nest condition groups up to three levels deep, with up to 30 total rules.
- Filter by titles, authors, reading status, series, category, original source folder (with optional nested-subfolder inclusion), format, publisher, language, ISBN, page/word counts, reading time, rating, start/finish dates, cover presence, metadata review status, visibility, possible duplicates, file sizes, missing files, and other indexed fields.
- Use relevant comparisons: equals/does not equal, contains/excludes, begins/ends with, number/date ranges, empty/not empty, boolean state, and value lists.
- Define **up to four ordered sort levels**, ascending or descending. Results use a consistent book-ID tie-breaker, with missing values last.
- Save named filter+sort views in SQLite for reuse. Saved views survive browser restarts and can be deleted without altering books.
- Search with a free-text input, clear the active query, and filter all results with server-side pagination.

**Library:** advanced filters, hidden/all visibility, adjustable page size, and grid/list display. **Reading Review:** advanced conditions combine with the active reading-status tab. **Series:** filters on number of books, progress percentage, read/unread totals, missing volume numbers, descriptions, and cover availability. **Quick Sort:** advanced conditions refine the chosen group (series, folder, author, or all) and can override the default order; random order remains available when no explicit multi-sort is set. **Metadata Review:** filter individual suggestions by confidence, field, author, title, series, and explanatory reason. **Individual series:** filter and reorder the member list without changing series assignments. **Custom exports:** reuse the same advanced rules and sorting to export matching records (including an empty CSV with headers when no books match).

The new JSON APIs are:

- `GET /api/query/metadata` — fields, valid operators, sorting support, and catalog-derived suggestions.
- `POST /api/query/books` — filtered, sorted, paginated books (1–200 per page).
- `POST /api/query/series` — aggregate series filtering/sorting.
- `POST /api/query/reviews` — pending metadata suggestions.
- `POST /api/query/quick-sort` — advanced Quick Sort batches (1–1000 at once).
- `GET/POST /api/query/views`, `DELETE /api/query/views/{id}` — saved views.

Example book query:

```json
{
  "filters": {
    "match": "all",
    "rules": [
      {"field": "folder", "op": "eq", "value": "D:/eBooks/Fantasy", "subfolders": true},
      {"match": "any", "rules": [
        {"field": "reading_status", "op": "eq", "value": "unanswered"},
        {"field": "reading_status", "op": "eq", "value": "want_to_read"}
      ]},
      {"field": "pages", "op": "gte", "value": 250}
    ]
  },
  "sort": [
    {"field": "series", "direction": "asc"},
    {"field": "series_index", "direction": "asc"},
    {"field": "title", "direction": "asc"}
  ],
  "visibility": "visible",
  "page": 1,
  "per_page": 48
}
```

All field names/operators are allowlisted, and values are bound as SQL parameters. The migration only adds a `saved_views` table and does not modify ebook files, titles, series, or reading records. Browsers remember **active unsaved queries** for their current tab session; named saved views persist in SQLite. Back up your SQLite database before upgrading.

Rebuild the static site after changing `frontend/src/main.js`, `frontend/src/advanced.js`, or the CSS with `python build_frontend.py`. The included production bundle ships both JavaScript modules; Node.js is not required.

Validation: `python -m pytest -q` (38 tests passing), `node --check` for both JavaScript modules, and Python syntax compilation. Automated full-browser validation was not possible in this runtime because Chromium navigation and even local style injection were blocked by the execution environment; visual/touch behavior should be verified on your own installation.
