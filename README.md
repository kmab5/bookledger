# bookledger v2.0

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

**Known limitations:** No full multi-device browser visual audit has been run yet. Long-running job state is in server memory, while metadata results persist in SQLite. Only records currently loaded on-screen can be selected with the bulk bar. Series matching and ebook extraction logic were not rewritten in this frontend migration.

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
