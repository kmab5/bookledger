# BookLedger v0.1

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
