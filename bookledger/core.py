"""Metadata-only ingest. Never writes to books or moves them."""
from __future__ import annotations
import hashlib, json, os, re, sqlite3, time, urllib.parse, urllib.request, zipfile, subprocess, shutil
from datetime import datetime, timezone
from pathlib import Path
from difflib import SequenceMatcher
from xml.etree import ElementTree as ET

FORMATS = {'.epub', '.pdf', '.mobi', '.azw', '.azw3', '.fb2', '.cbz', '.cbr', '.djvu', '.djv', '.txt', '.rtf', '.html', '.htm'}
SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS books (
 id INTEGER PRIMARY KEY, title TEXT NOT NULL, subtitle TEXT, authors TEXT NOT NULL DEFAULT '[]',
 isbn10 TEXT, isbn13 TEXT, language TEXT, publisher TEXT, published TEXT,
 description TEXT, subjects TEXT NOT NULL DEFAULT '[]', series TEXT, series_index REAL,
 page_count INTEGER, page_count_kind TEXT, word_count INTEGER, cover_url TEXT,
 metadata_json TEXT NOT NULL DEFAULT '{}', provenance_json TEXT NOT NULL DEFAULT '{}',
 confidence_json TEXT NOT NULL DEFAULT '{}', needs_review INTEGER NOT NULL DEFAULT 1,
 manually_verified INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
 id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id), path TEXT NOT NULL UNIQUE,
 extension TEXT NOT NULL, bytes INTEGER NOT NULL, modified_ns INTEGER NOT NULL, created_ns INTEGER,
 fingerprint TEXT NOT NULL, last_seen TEXT NOT NULL, missing INTEGER NOT NULL DEFAULT 0,
 extract_error TEXT, extra_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_files_book ON files(book_id);
CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, parent_id INTEGER REFERENCES categories(id));
CREATE TABLE IF NOT EXISTS book_categories (
 book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
 category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
 confidence REAL NOT NULL, source TEXT NOT NULL, confirmed INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(book_id, category_id)
);
CREATE TABLE IF NOT EXISTS reading (
 book_id INTEGER PRIMARY KEY REFERENCES books(id) ON DELETE CASCADE,
 status TEXT NOT NULL DEFAULT 'unanswered', started TEXT, finished TEXT,
 minutes_read INTEGER, current_page INTEGER, rating REAL, notes TEXT NOT NULL DEFAULT '',
 read_count INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reading_sessions (
 id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
 started TEXT, finished TEXT, minutes_read INTEGER, pages_read INTEGER, note TEXT
);
CREATE TABLE IF NOT EXISTS review_queue (
 id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
 field TEXT NOT NULL, suggested TEXT, confidence REAL NOT NULL, reason TEXT NOT NULL,
 resolved INTEGER NOT NULL DEFAULT 0, UNIQUE(book_id,field)
);
CREATE TABLE IF NOT EXISTS scan_runs (id INTEGER PRIMARY KEY, root TEXT NOT NULL, started TEXT NOT NULL, ended TEXT, count_new INTEGER NOT NULL DEFAULT 0, count_updated INTEGER NOT NULL DEFAULT 0, count_unchanged INTEGER NOT NULL DEFAULT 0, errors INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS external_cache (key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS series_catalog (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE COLLATE NOCASE, description TEXT, notes TEXT, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS book_links (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE, candidate_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE, kind TEXT NOT NULL, confidence REAL NOT NULL, resolved INTEGER NOT NULL DEFAULT 0, UNIQUE(book_id,candidate_id,kind));
CREATE INDEX IF NOT EXISTS idx_links_candidate ON book_links(candidate_id);

"""

def now(): return datetime.now(timezone.utc).isoformat(timespec='microseconds')
def connect(path: str | Path):
    db = sqlite3.connect(str(Path(path).expanduser())); db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    if 'content_sha256' not in {row[1] for row in db.execute('PRAGMA table_info(files)')}:
        db.execute('ALTER TABLE files ADD COLUMN content_sha256 TEXT')
    db.execute('CREATE INDEX IF NOT EXISTS idx_files_sha256 ON files(content_sha256)')
    db.commit()
    return db

def clean(s): return re.sub(r'\s+', ' ', str(s or '')).strip()
def norm(s): return re.sub(r'[^a-z0-9]+', '', clean(s).casefold())
def jsonarr(x):
    try: return json.loads(x or '[]')
    except (ValueError, TypeError): return []

def parse_name(path: Path):
    stem = re.sub(r'[_]+', ' ', path.stem)
    stem = re.sub(r'\s*\[(?:epub|pdf|retail|ebook|scan|ocr|v\d+|\d{4})\]\s*', ' ', stem, flags=re.I)
    pattern = re.match(r'^(.+?)\s*[-–]\s*(?:#|book\s*)?(\d+(?:\.\d+)?)\s*[-–]\s*(.+)$', stem, re.I)
    series = None; idx = None
    if pattern:
        series, idx, stem = clean(pattern[1]), float(pattern[2]), clean(pattern[3])
    else:
        match = re.search(r'\s*[\[(](.+?)\s*(?:#|book\s+)(\d+(?:\.\d+)?)[\])]\s*$', stem, re.I)
        if match:
            series, idx = clean(match[1]), float(match[2]); stem = stem[:match.start()]
    parts = re.split(r'\s+[-–]\s+', stem)
    title = clean(parts[0]) if parts else clean(stem)
    author = clean(parts[1]) if len(parts)==2 else ''
    return {'title': title or path.stem, 'authors': [author] if author else [], 'series': series, 'series_index': idx}

def epub_meta(path):
    out = {}; raw = {}
    with zipfile.ZipFile(path) as z:
        container = ET.fromstring(z.read('META-INF/container.xml'))
        rootfile = next(x for x in container.iter() if x.tag.endswith('rootfile'))
        opfpath = rootfile.attrib['full-path']; root = ET.fromstring(z.read(opfpath))
        meta = next((x for x in root if x.tag.endswith('metadata')), None)
        if meta is None: return out, raw
        entries = {}
        for x in meta:
            tag=x.tag.rsplit('}', 1)[-1].lower(); value=clean(''.join(x.itertext()))
            if value: entries.setdefault(tag,[]).append(value)
        raw['epub_dc'] = entries
        for src, dst in [('title','title'),('language','language'),('publisher','publisher'),('description','description'),('date','published')]:
            if entries.get(src): out[dst]=entries[src][0]
        if entries.get('creator'): out['authors']=entries['creator']
        if entries.get('subject'): out['subjects']=entries['subject']
        for candidate in entries.get('identifier', []):
            digits=re.sub('[^0-9Xx]', '', candidate)
            if len(digits)==13: out['isbn13']=digits
            elif len(digits)==10: out['isbn10']=digits
        metas=[x for x in meta if x.tag.rsplit('}',1)[-1]=='meta']
        for x in metas:
            name=x.attrib.get('name','').lower(); prop=x.attrib.get('property','').lower()
            if name in ('calibre:series', 'belongs-to-collection') or prop=='belongs-to-collection': out['series']=x.attrib.get('content') or clean(x.text)
            if name=='calibre:series_index':
                try: out['series_index']=float(x.attrib['content'])
                except (KeyError, ValueError): pass
        words=0
        for item in root.iter():
            if item.tag.endswith('item') and item.attrib.get('media-type') in ('application/xhtml+xml','text/html'):
                href=item.attrib.get('href',''); directory=opfpath.rsplit('/',1)[0] if '/' in opfpath else ''
                full=__import__('posixpath').normpath(__import__('posixpath').join(directory,href))
                try:
                    doc=ET.fromstring(z.read(full)); words+=len(re.findall(r'\b\w+\b', ' '.join(doc.itertext())))
                except (KeyError, ET.ParseError): pass
        if words: out['word_count']=words
    return out, raw

def optional_ebook_meta(path):
    """Use Calibre when installed; metadata only, never convert or edit an ebook."""
    exe=shutil.which('ebook-meta')
    if not exe: return {}, {}, 'Install Calibre ebook-meta for deeper format extraction'
    try:
        cp=subprocess.run([exe,str(path)],capture_output=True,text=True,timeout=18,check=True)
        raw={'calibre_output':cp.stdout[:12000]}; entries={}
        for line in cp.stdout.splitlines():
            if ':' in line:
                k,v=line.split(':',1); entries[k.strip().casefold()]=clean(v)
        out={}
        mapping={'title':'title','publisher':'publisher','language':'language','comments':'description','series':'series','published':'published'}
        for src,dst in mapping.items():
            if entries.get(src):out[dst]=entries[src]
        if entries.get('author(s)'):out['authors']=[clean(v) for v in re.split(r'\s*&\s*',entries['author(s)']) if clean(v)]
        if entries.get('tags'):out['subjects']=[clean(v) for v in entries['tags'].split(',') if clean(v)]
        for k in ('isbn','identifiers'):
            val=entries.get(k,''); match=re.search(r'(?<!\d)(97[89]\d{10}|\d{9}[\dXx])(?!\d)',re.sub(r'[- ]','',val))
            if match:out['isbn13' if len(match[1])==13 else 'isbn10']=match[1]
        if entries.get('series index'):
            try:out['series_index']=float(entries['series index'])
            except ValueError:pass
        return out,raw,None
    except (subprocess.TimeoutExpired,subprocess.CalledProcessError,OSError) as exc:
        return {},{},f'Calibre extraction failed: {str(exc)[:180]}'

def cbz_meta(path):
    """CBZ pages are image entries; optional ComicInfo.xml supplies comic metadata."""
    with zipfile.ZipFile(path) as z:
        imgs=[n for n in z.namelist() if n.lower().endswith(('.png','.jpg','.jpeg','.webp','.gif','.avif')) and not n.endswith('/')]
        out={'page_count':len(imgs),'page_count_kind':'image_count'} if imgs else {}
        raw={'image_entries':len(imgs)}
        info=next((n for n in z.namelist() if n.lower().endswith('comicinfo.xml')),None)
        if info:
            root=ET.fromstring(z.read(info)); vals={x.tag.rsplit('}',1)[-1]:clean(x.text) for x in root if x.text}
            raw['comicinfo']=vals
            for src,dst in [('Title','title'),('Series','series'),('Writer','authors'),('LanguageISO','language'),('Summary','description'),('Publisher','publisher')]:
                if vals.get(src):out[dst]=[clean(x) for x in vals[src].split(',')] if dst=='authors' else vals[src]
            if vals.get('Number'):
                try:out['series_index']=float(vals['Number'])
                except ValueError:pass
        return out,raw

def pdf_meta(path):
    import fitz
    with fitz.open(path) as doc:
        raw=dict(doc.metadata or {}); out={'page_count':len(doc),'page_count_kind':'exact'}
        for key in ('title','author','subject','keywords','creationDate'):
            val=clean(raw.get(key))
            if not val: continue
            if key=='author': out['authors']=[clean(x) for x in re.split(r';|\s+and\s+',val) if clean(x)]
            elif key=='subject': out['subjects']=[val]
            elif key=='keywords': out['subjects']=out.get('subjects',[])+[clean(x) for x in val.split(',') if clean(x)]
            elif key=='title': out['title']=val
        return out, {'pdf_info':raw}

def fb2_meta(path):
    tree=ET.parse(path); root=tree.getroot()
    def find(tag):
        for e in root.iter():
            if e.tag.rsplit('}',1)[-1]==tag: return e
    title=find('book-title'); out={}
    if title is not None: out['title']=clean(''.join(title.itertext()))
    authors=[]
    for e in root.iter():
        if e.tag.rsplit('}',1)[-1]=='author':
            name=' '.join(clean(''.join(x.itertext())) for x in e if x.tag.rsplit('}',1)[-1] in ('first-name','middle-name','last-name'))
            if clean(name): authors.append(clean(name))
    if authors: out['authors']=authors
    return out, {}

def extract(path):
    ext=path.suffix.lower()
    try:
        if ext=='.epub': return (*epub_meta(path), None)
        if ext=='.pdf': return (*pdf_meta(path), None)
        if ext=='.fb2': return (*fb2_meta(path), None)
        if ext=='.cbz': return (*cbz_meta(path), None)
        if ext in ('.mobi','.azw','.azw3','.cbr','.djvu','.djv','.rtf','.txt','.html','.htm'):
            return optional_ebook_meta(path)
        return ({}, {}, f'No embedded extractor for {ext}; filename metadata retained')
    except Exception as exc:
        return ({}, {}, f'{type(exc).__name__}: {exc}'[:500])

def enrich(db, data, allow_online=True):
    """Only enrich when title+author or ISBN exist, with cautious matching."""
    if not allow_online or not (data.get('isbn13') or data.get('isbn10') or data.get('title')): return {}, {}
    key=data.get('isbn13') or data.get('isbn10') or f"{data['title']}|{','.join(data.get('authors',[]))}"
    cached=db.execute('SELECT payload FROM external_cache WHERE key=?',(key,)).fetchone()
    if cached: return json.loads(cached[0]), {'source':'openlibrary_cached'}
    query={'isbn':key} if (data.get('isbn13') or data.get('isbn10')) else {'title':data['title']}
    if 'title' in query and data.get('authors'): query['author']=data['authors'][0]
    url='https://openlibrary.org/search.json?'+urllib.parse.urlencode({**query,'limit':3,'fields':'key,title,author_name,first_publish_year,isbn,number_of_pages_median,language,publisher,cover_i,subject'})
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'BookLedger/0.1 (personal library catalog; local metadata manager)'})
        with urllib.request.urlopen(req,timeout=5) as resp: payload=json.load(resp)
        docs=payload.get('docs',[])
        best=None
        exact_title_matches=[item for item in docs if norm(item.get('title'))==norm(data.get('title'))]
        for item in docs:
            title_score=SequenceMatcher(None,norm(data.get('title')),norm(item.get('title'))).ratio()
            authors=data.get('authors',[])
            author_score=max((SequenceMatcher(None,norm(a),norm(b)).ratio() for a in authors for b in item.get('author_name',[])),default=0)
            isbn_match=bool(set([data.get('isbn13'),data.get('isbn10')]) & set(item.get('isbn',[])))
            if isbn_match or (title_score>=.9 and (author_score>=.78 if authors else len(exact_title_matches)==1 and title_score==1)):
                best=item; break
        result={}
        if best:
            if not data.get('authors') and best.get('author_name'): result['authors']=best['author_name'][:5]
            fields={'first_publish_year':'published','number_of_pages_median':'page_count'}
            for src,dst in fields.items():
                if best.get(src): result[dst]=str(best[src]) if dst=='published' else int(best[src])
            if best.get('publisher'): result['publisher']=best['publisher'][0]
            if best.get('language'): result['language']=best['language'][0]
            if best.get('subject'): result['subjects']=best['subject'][:20]
            if best.get('cover_i'): result['cover_url']=f"https://covers.openlibrary.org/b/id/{int(best['cover_i'])}-M.jpg"
            if result.get('page_count'): result['page_count_kind']='catalog_estimate'
        db.execute('INSERT OR REPLACE INTO external_cache VALUES (?,?,?)',(key,json.dumps(result),now()))
        return result, {'source':'openlibrary','matched':bool(best)}
    except (OSError, ValueError, KeyError): return {}, {'source':'openlibrary','error':'lookup unavailable'}

GENRES = {
 'Fantasy':['fantasy','magic','dragons','epic fantasy'], 'Science Fiction':['science fiction','sci-fi','space opera','cyberpunk'],
 'Mystery':['mystery','detective','whodunit'], 'Romance':['romance','love story'], 'History':['history','historical'],
 'Biography':['biography','memoir','autobiography'], 'Technology':['programming','computer science','software','technology'],
 'Science':['physics','chemistry','biology','mathematics','science'], 'Horror':['horror','ghost','supernatural'],
 'Thriller':['thriller','suspense'], 'Nonfiction':['nonfiction','non-fiction'], 'Philosophy':['philosophy'],
 'Business':['business','management','economics'], 'Self-help':['self-help','personal development'],
}
def classify(data):
    text=' '.join(data.get('subjects',[])).lower(); desc=(data.get('description') or '').lower()
    result=[]
    for genre, keywords in GENRES.items():
        if any(re.search(r'\b'+re.escape(k)+r'\b',text) for k in keywords): result.append((genre,.90,'catalog subject'))
        elif any(re.search(r'\b'+re.escape(k)+r'\b',desc) for k in keywords): result.append((genre,.63,'description keyword'))
    return result

def file_fingerprint(path, stat):
    # Cheap fingerprint avoids reading large files on repeat scans.
    return f'{stat.st_size}:{stat.st_mtime_ns}'

def file_sha256(path):
    digest=hashlib.sha256()
    with open(path,'rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def potential_related(db, book_id, data):
    """Never auto-merge title-only similarities. Flag likely alternate editions."""
    if not data.get('authors'):return
    candidates=db.execute('SELECT id,title,authors,isbn10,isbn13 FROM books WHERE id<>?',(book_id,)).fetchall()
    for candidate in candidates:
        title_sim=SequenceMatcher(None,norm(candidate['title']),norm(data.get('title'))).ratio()
        author_overlap=any(norm(a)==norm(b) for a in data['authors'] for b in jsonarr(candidate['authors']))
        if title_sim>=.91 and author_overlap:
            a,b=sorted((book_id,candidate['id']))
            db.execute('INSERT OR IGNORE INTO book_links(book_id,candidate_id,kind,confidence) VALUES(?,?,?,?)',(a,b,'possible_edition',min(.99,round(title_sim*.96,3))))

def scan(db, root, online=True):
    root=Path(root).expanduser().resolve()
    if not root.is_dir(): raise ValueError(f'Not a folder: {root}')
    started=now(); run=db.execute('INSERT INTO scan_runs(root,started) VALUES(?,?)',(str(root),started)).lastrowid
    totals={'new':0,'updated':0,'unchanged':0,'errors':0}
    for directory, dirs, names in os.walk(root):
        dirs[:]=[d for d in dirs if not d.startswith('.')]
        for filename in names:
            path=Path(directory)/filename
            if path.suffix.lower() not in FORMATS: continue
            try:
                st=path.stat(); fingerprint=file_fingerprint(path,st)
                old=db.execute('SELECT * FROM files WHERE path=?',(str(path),)).fetchone()
                if old and old['fingerprint']==fingerprint:
                    db.execute('UPDATE files SET last_seen=?,missing=0 WHERE id=?',(started,old['id'])); totals['unchanged']+=1; continue
                guessed=parse_name(path); embedded, raw, err=extract(path)
                digest=file_sha256(path)
                data={**guessed}; sources={k:'filename' for k,v in guessed.items() if v}; scores={k:.55 for k in sources}
                for k,v in embedded.items():
                    if v not in (None,'',[]): data[k]=v; sources[k]='embedded'; scores[k]=.95 if k!='series_index' else .92
                external, enrichment=enrich(db,data,online)
                for k,v in external.items():
                    if data.get(k) in (None,'',[]): data[k]=v; sources[k]='openlibrary'; scores[k]=.65 if k=='authors' and not guessed.get('authors') else .82
                # Existing manually verified records are never overwritten.
                book=None
                if old: book=db.execute('SELECT * FROM books WHERE id=?',(old['book_id'],)).fetchone()
                if book is None:
                    isbn=data.get('isbn13') or data.get('isbn10')
                    if isbn: book=db.execute('SELECT * FROM books WHERE isbn13=? OR isbn10=? LIMIT 1',(isbn,isbn)).fetchone()
                if book is None:
                    # Identical bytes are the same manifestation, regardless of filename.
                    same=db.execute('SELECT book_id FROM files WHERE content_sha256=? LIMIT 1',(digest,)).fetchone()
                    if same:book=db.execute('SELECT * FROM books WHERE id=?',(same['book_id'],)).fetchone()
                # Deliberately DO NOT merge by title+author alone: different editions
                # and translations can have matching bibliographic names.
                raw['enrichment']=enrichment
                if data.get('series'):
                    db.execute('INSERT OR IGNORE INTO series_catalog(name,updated_at) VALUES(?,?)',(data['series'],now()))
                if book and (book['manually_verified'] or (not old and db.execute('SELECT 1 FROM files WHERE book_id=? AND content_sha256=?',(book['id'],digest)).fetchone())):
                    # A byte-identical additional path must not overwrite catalog fields.
                    book_id=book['id']
                else:
                    fields=['title','subtitle','authors','isbn10','isbn13','language','publisher','published','description','subjects','series','series_index','page_count','page_count_kind','word_count','cover_url']
                    values={k:data.get(k) for k in fields}
                    values['authors']=json.dumps(values['authors'] or []); values['subjects']=json.dumps(values['subjects'] or [])
                    values.update(metadata_json=json.dumps(raw),provenance_json=json.dumps(sources),confidence_json=json.dumps(scores),needs_review=int(any(scores.get(x,0)<.8 for x in ('title','authors') if data.get(x)) or bool(data.get('series') and scores.get('series',0)<.8)),updated_at=now())
                    if book:
                        # Preserve existing values when a new edition lacks metadata.
                        for field in fields:
                            if field not in data or data[field] in (None,'',[]): values[field]=book[field]
                        db.execute('UPDATE books SET '+','.join(f'{k}=?' for k in values)+' WHERE id=?',(*values.values(),book['id'])); book_id=book['id']
                    else:
                        values['created_at']=now()
                        book_id=db.execute('INSERT INTO books('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values())).lastrowid
                        db.execute('INSERT INTO reading(book_id,updated_at) VALUES (?,?)',(book_id,now()))
                    db.execute('DELETE FROM review_queue WHERE book_id=? AND resolved=0',(book_id,))
                    if not book:potential_related(db,book_id,data)
                    for field in ('title','authors','series','series_index'):
                        if data.get(field) and scores.get(field,0)<.8:
                            db.execute('INSERT OR REPLACE INTO review_queue(book_id,field,suggested,confidence,reason) VALUES(?,?,?,?,?)',(book_id,field,json.dumps(data[field]),scores[field],f'Inferred from {sources[field]}; verify before accepting'))
                    for genre,score,source in classify(data):
                        db.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(genre,))
                        category=db.execute('SELECT id FROM categories WHERE name=?',(genre,)).fetchone()['id']
                        db.execute('INSERT INTO book_categories(book_id,category_id,confidence,source) VALUES(?,?,?,?) ON CONFLICT(book_id,category_id) DO UPDATE SET confidence=excluded.confidence,source=excluded.source WHERE confirmed=0',(book_id,category,score,source))
                if old:
                    db.execute('UPDATE files SET book_id=?,extension=?,bytes=?,modified_ns=?,created_ns=?,fingerprint=?,last_seen=?,missing=0,extract_error=?,extra_json=?,content_sha256=? WHERE id=?',(book_id,path.suffix.lower(),st.st_size,st.st_mtime_ns,getattr(st,'st_birthtime_ns',None) or st.st_ctime_ns,fingerprint,started,err,json.dumps(raw),digest,old['id']))
                    totals['updated']+=1
                else:
                    db.execute('INSERT INTO files(book_id,path,extension,bytes,modified_ns,created_ns,fingerprint,last_seen,extract_error,extra_json,content_sha256) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(book_id,str(path),path.suffix.lower(),st.st_size,st.st_mtime_ns,getattr(st,'st_birthtime_ns',None) or st.st_ctime_ns,fingerprint,started,err,json.dumps(raw),digest))
                    totals['new']+=1
                if err: totals['errors']+=1
                db.commit()
            except (OSError,sqlite3.DatabaseError,ValueError) as exc:
                totals['errors']+=1
                print(f'Could not index {path}: {exc}')
    # Do not mark files absent unless inside the scanned tree; missing is reversible.
    prefix=str(root)+os.sep
    db.execute('UPDATE files SET missing=1 WHERE (path LIKE ? ESCAPE "\\" OR path=?) AND last_seen<>?',(prefix.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',str(root),started))
    db.execute('UPDATE scan_runs SET ended=?,count_new=?,count_updated=?,count_unchanged=?,errors=? WHERE id=?',(now(),totals['new'],totals['updated'],totals['unchanged'],totals['errors'],run));db.commit()
    return totals
