# BookLedger v0.4

A self-hosted, **metadata-only** ebook catalog and reading tracker. It does not rename, copy, delete or move books. It opens supported files **read-only** to extract metadata. Python 3.11+.

## Installation

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -e .
```

## Commands

```bash
bookledger scan-folder "/path/to/books"               # online enrichment enabled by default
bookledger scan-folder "/path/to/books" --offline      # no external network
bookledger stats
bookledger serve                                      # browse http://127.0.0.1:8787
bookledger export json backup.json                    # full fidelity: dates, sessions, sources, files, confidence
bookledger export storygraph storygraph.csv           # Goodreads-shaped CSV compatible with StoryGraph
bookledger export goodreads goodreads.csv
```

Use `--db /path/to/catalog.sqlite3` on commands to use another database. Scans can be repeated; unchanged files are skipped. Catalogs remember files missing from later scans, rather than deleting records.

## Website

Library search/filter, metadata-source inspection, review queue with confidence, custom category addition, reading-status questionnaire (all/series/category), detailed reading record with start/finish dates, minutes read, page progress, rating, notes and session history, and statistics.

Reading statuses: unanswered, not read, want to read, currently reading, finished, started and abandoned, on hold, rereading.

## Export notes

`storygraph` and `goodreads` output the Goodreads CSV columns; StoryGraph documents this as its bulk import format. StoryGraph accepts `did-not-finish` for abandoned titles. Only a subset of local data fits those columns: **use JSON as your canonical backup**. CSV fields lack multiple reading sessions, precise confidence/provenance and exact started dates. `Private Notes` includes simple start/time information as text. Always verify the imported results in the destination service; catalog matching there is outside this app's control.

## Metadata behavior / limitations

- EPUB: Dublin Core OPF, Calibre series tags, approximate word count (when XHTML is parseable).
- PDF: PyMuPDF info dictionary and exact document page count; **no OCR** or scanning document content.
- FB2: title and author via XML.
- MOBI/AZW/AZW3/CBZ/CBR/DJVU/TXT/RTF/HTML: indexed, filename inference and online enrichment; embedded metadata extraction not implemented for these formats yet. Extraction limitations are visible per file.
- Uses Open Library search and cover URLs for online enrichment, with a 5-second timeout per new lookup. Online data is cached. External candidates must satisfy strong title/author or ISBN matches. No AI model or API key.
- Filename parsing recognizes `Series - 02 - Title.epub`, `Title - Author.epub` and `Title (Series Book 2).epub` patterns, not every naming convention.
- Field-level provenance and confidence values are heuristic scores, not calibrated statistical probabilities. Review queue covers uncertain title/author/series assignments. Subject-based classification uses keyword rules, with explicit category confidence.
- ISBN and matching title+author enable deduplication across formats. Identically named unrelated books may require manual reconciliation. The app does not automatically merge already imported duplicates.
- EPUB page counts are not equivalent to PDF page counts; external page counts are catalog estimates.
- Filesystem creation time is OS-dependent: on Unix it may be inode change time, not creation time.
- A verified metadata record is protected against further scan updates, including otherwise useful enrichments; edit the catalog as needed.

## Security and Android

Runs at `127.0.0.1` by default. For access from your phone **on a trusted private Wi-Fi**, start `bookledger serve --host 0.0.0.0`, then visit `http://YOUR-PC-LAN-IP:8787` from Android. The server does not implement user login, so **never expose it to the public Internet or untrusted networks**. All write forms have CSRF tokens, but those are not substitutes for authentication. Run the server from a single process because the CSRF token is process-local.

Termux-native support is a future target. PyMuPDF wheels might not be available there; for now run scanning on the PC and access the website on your phone. The SQLite data model and pure-Python EPUB parser are portable.

## Test

```bash
python -m pip install -e '.[test]'
pytest -q
```


## Version 0.2 upgrades

- **Edition-safe matching:** different files with matching title/author no longer automatically collapse into one bibliographic record. File-identical copies are linked through streaming SHA-256 hashes; matching ISBN records are also associated. Possible alternate editions appear under **Possible editions** for review; resolution never modifies book files.
- **Series catalog:** every detected series is registered automatically. The **Series** page lists titles and completed counts and supports renaming a series, descriptions, and personal notes. Renaming updates the database references only.
- **More extraction:** CBZ ComicInfo.xml, page/image count; optional Calibre `ebook-meta` for MOBI, AZW, AZW3, CBR, DJVU, RTF, TXT, and HTML. Calibre is *not* required to run BookLedger.
- **Existing databases:** opening an existing v0.1 database applies the additive SHA-256 column and creates the new tables automatically. Back up the SQLite database before upgrading; previously scanned files acquire hashes when they are reprocessed (a changed file or new file).

**No login or authentication was added.** Keep `bookledger serve` on localhost by default, and use `--host 0.0.0.0` only on a trusted Wi-Fi network. Without authentication, anyone who can reach the server can change its data.

**Important limitations:** filenames alone cannot reliably identify editions or series; online catalog lookups may suggest work-level metadata rather than edition-specific data. EPUB page count is not a fixed number. Some formats rely on an optional installed Calibre executable. The current edition-suggestion workflow labels relationships; it intentionally does not auto-merge records or their reading histories.

### Scanning from the website (v0.3)

Open `/scan` from the website navigation, enter an absolute folder path on the
**computer running the server**, and start indexing. The page polls live status,
showing the current file, stage, results and errors. It works from a phone browser
on the same trusted local network, but cannot access phone-only files directly.
Only one web scan runs at a time; a server restart interrupts the current scan.

The CLI now prints each scanned directory, file and processing stage, plus a
summary. This makes slow PDF parsing or large-file hashing visible. No ebook
files are modified. Web scans accept paths reachable by the server process;
this interface intentionally has no file upload or arbitrary file manipulation.

## v0.4: kmab design, covers, enrichment, exports

- Web app uses kmab's dark palette, Space Grotesk / Space Mono, responsive book cover cards, updated forms, and an SVG favicon.
- Cover images embedded in EPUB and CBZ are extracted read-only and cached as resized JPEG thumbnails next to the SQLite database (`covers/<book_id>.jpg`). Online Open Library cover thumbnails can also be downloaded while online. Requires Pillow.
- `GET /cover/<id>` serves only files from the catalog cover cache. Previously indexed books can obtain covers using the new `/enrich` page, which also fills missing metadata from Open Library. Enrichment never overwrites existing non-empty catalog fields.
- Parent folder names provide extra low-confidence category suggestions; directories whose names suggest series/sagas can propose series names. They are never silently trusted as authoritative.
- `/exports` offers multi-column custom CSV downloads with search, reading status, category and series filters. Editable reference layouts include Bookmory and Hardcover; **these are not verified native import schemas**. Preset buttons produce Goodreads/StoryGraph-shaped CSV and the full-fidelity JSON backup.
- `bookledger review` currently opens the same web server as `bookledger serve`, with no specialized initial page. Prefer `bookledger serve`.
- Covers are stored as derived metadata assets, not copies of the books. Deleting a library database does not delete the original ebook files.
- No authentication, no AI and no ebook moving/renaming/deletion.

The GitHub Pages landing page is separate from the local FastAPI app. GitHub Pages cannot host the scanner/database server.


## v0.5 maintenance and reading workflow

- Enrichment no longer stops on missing SQLite columns (the cause of `No item with that key`). Each book failure is recorded and the batch continues.
- Scan records extractor versions and automatically refreshes unchanged files once after an extraction upgrade. No original files are modified.
- Folder hierarchy is persisted in `folder_categories`, separately from the inferred genres and series.
- Book detail pages now show source folders, possible editions, series siblings, and outstanding review evidence.
- One-click reading status selection is available on book pages and `/reading`, with a compact queue.
- Series detail `/series/<id>` supports editing volume order and suggests unassigned titles, while `/book/<id>/series` allows manually assigning/removing memberships.
- Enhanced dark responsive styles, focus indicators, reduced-motion support and a skip-to-content link.
- `bookledger review` still starts the same server as `serve`; use the website navigation to review reading or metadata.

Back up the SQLite database before upgrading. The migration adds `files.extractor_version` and a new `folder_categories` table. Existing reading records remain intact.

The series algorithm is still deterministic and intentionally conservative: filename/embedded volume numbers and explicitly named series folders are evidence, not guarantees. Ambiguous cases should be confirmed manually.

## v0.6 notes

- A malformed or corrupt EPUB cover entry no longer interrupts a whole-library scan. Cover failures are best-effort; unreadable covers may remain blank.
- The scan activity log stays scrolled to the latest event during automatic refresh.
- Books can be hidden from the default catalog using the book-detail action, then found through Library → visibility → Hidden books only (or All books). Hidden books are retained in SQLite and available to exports, reviews and direct links.
- Shared UI spacing, responsive filters, navigation and focus styles have been revised.
- Existing SQLite databases migrate automatically with a new `books.hidden` field. Back up your database before upgrading.
