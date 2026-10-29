"""BookLedger v2 JSON API and static SPA host. Original renderer is retained at /legacy."""
from __future__ import annotations
import json, threading, tempfile, secrets
from pathlib import Path
from datetime import date
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .core import connect, now, jsonarr, scan, enrich_existing
from .export import export_json, export_csv
from .custom_export import export_custom, FIELDS, TEMPLATES
from .legacy_webapp import create_app as legacy_app
from .advanced_query import query_books, query_series, metadata as query_metadata, compile_group, BOOK_FIELDS, BOOK_SORT_FIELDS, query_reviews

ROOT = Path(__file__).parent
STATES = {'unanswered','not_read','want_to_read','reading','finished','abandoned','on_hold','rereading'}

# Database-backed, validated preferences; unknown keys are rejected.
SETTING_SCHEMA = {
    'library.include_subfolders': ('bool', True),
    'library.default_visibility': ('choice', 'visible', ['visible','hidden','all']),
    'library.default_sort': ('choice', 'title', ['title','author','recent','series']),
    'library.page_size': ('int', 48, 12, 200),
    'library.show_covers': ('bool', True),
    'library.show_status_badges': ('bool', True),
    'library.card_density': ('choice', 'comfortable', ['compact','comfortable','spacious']),
    'reading.default_queue': ('choice','unanswered',['unanswered','all']),
    'reading.show_covers': ('bool', True),
    'quick_sort.include_classified': ('bool', False),
    'quick_sort.show_metadata': ('bool', True),
    'scan.online_by_default': ('bool', True),
    'enrich.default_mode': ('choice','missing',['missing','covers','all']),
    'enrich.batch_size': ('int', 100, 1, 10000),
    'exports.default_format': ('choice','json',['json','goodreads','storygraph']),
}
def setting_defaults(): return {key: spec[1] for key,spec in SETTING_SCHEMA.items()}
def validate_setting(key, value):
    spec=SETTING_SCHEMA.get(key)
    if spec is None: raise HTTPException(422, f'Unknown setting: {key}')
    if spec[0]=='bool':
        if type(value) is not bool: raise HTTPException(422, f'{key} must be boolean')
    elif spec[0]=='int':
        if type(value) is not int or not spec[2]<=value<=spec[3]: raise HTTPException(422, f'{key} out of range')
    elif spec[0]=='choice' and value not in spec[2]: raise HTTPException(422, f'Invalid choice for {key}')
    return value

class BookUpdate(BaseModel):
    status: str | None = None
    hidden: bool | None = None
    started: date | None = None
    finished: date | None = None
    minutes_read: int | None = Field(default=None, ge=0)
    current_page: int | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    notes: str | None = None
    series: str | None = None
    series_index: float | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    subtitle: str | None = None
    authors: list[str] | None = None
    isbn10: str | None = None
    isbn13: str | None = None
    language: str | None = None
    publisher: str | None = None
    published: str | None = None
    description: str | None = None
    page_count: int | None = Field(default=None, ge=0)
    word_count: int | None = Field(default=None, ge=0)
    cover_url: str | None = None

class BulkRequest(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=10000)
    action: str
    series_name: str | None = None

class ReadingSession(BaseModel):
    started: date | None = None
    finished: date | None = None
    minutes_read: int | None = Field(default=None, ge=0)
    pages_read: int | None = Field(default=None, ge=0)
    note: str = ""

class SeriesUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    notes: str | None = None

class SeriesMember(BaseModel):
    book_id: int
    index: float | None = None

class JobRequest(BaseModel):
    folder: str = ''
    online: bool = True
    mode: str = 'missing'
    limit: int = Field(default=100, ge=1, le=10000)
    start_after: int = Field(default=0, ge=0)

class ExportRequest(BaseModel):
    fields: list[str]
    advanced_query: dict | None = None
    status: str = ''
    category: str = ''
    series: str = ''
    search: str = ''


def create_app(db_path):
    app = FastAPI(title='BookLedger API', version='2.0')
    location = Path(db_path).expanduser()
    location.parent.mkdir(parents=True, exist_ok=True)
    with connect(location) as con:
        con.execute("CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL)")
        con.execute("CREATE TABLE IF NOT EXISTS saved_views (id INTEGER PRIMARY KEY, scope TEXT NOT NULL CHECK(scope IN ('books','series','reading','quick','review','exports','series_members')), name TEXT NOT NULL, definition TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(scope,name))")
        con.commit()
    def db(): return connect(location)
    def read_settings(c):
        result=setting_defaults()
        for r in c.execute('SELECT key,value_json FROM app_settings'):
            try:
                result[r['key']]=validate_setting(r['key'], json.loads(r['value_json']))
            except (HTTPException,ValueError,TypeError): pass
        return result
    @app.get('/api/settings')
    def get_settings():
        with db() as c: return {'values':read_settings(c), 'defaults':setting_defaults()}
    @app.patch('/api/settings')
    def patch_settings(values:dict[str,object]):
        if not isinstance(values,dict): raise HTTPException(422,'Expected object')
        validated={k:validate_setting(k,v) for k,v in values.items()}
        with db() as c:
            for key,value in validated.items():
                c.execute('INSERT INTO app_settings(key,value_json) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json',(key,json.dumps(value)))
            c.commit()
            return {'values':read_settings(c)}
    @app.post('/api/settings/reset')
    def reset_settings():
        with db() as c:
            c.execute('DELETE FROM app_settings');c.commit()
        return {'values':setting_defaults()}
    def row(r):
        if r is None: return None
        d=dict(r)
        for k in ('authors','subjects'):
            if k in d:d[k]=jsonarr(d[k])
        return d
    def exists(c, book_id):
        if not c.execute('SELECT 1 FROM books WHERE id=?',(book_id,)).fetchone(): raise HTTPException(404,'Book not found')
    def status_update(c, book_id, state):
        if state not in STATES: raise HTTPException(422,'Unknown reading status')
        exists(c,book_id)
        c.execute('INSERT INTO reading(book_id,status,updated_at) VALUES(?,?,?) ON CONFLICT(book_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at',(book_id,state,now()))
    @app.get('/api/query/metadata')
    def advanced_metadata():
        data=query_metadata()
        with db() as c:
            paths=[x[0].replace(chr(92),'/') for x in c.execute('SELECT DISTINCT path FROM files WHERE path IS NOT NULL')]
            folders=set()
            for path in paths:
                parts=path.split('/')
                for k in range(1,len(parts)):
                    candidate='/'.join(parts[:k])
                    if candidate:folders.add(candidate)
            data['choices']={
                'folder':sorted(folders,key=str.casefold)[:1500],
                'category':[r[0] for r in c.execute('SELECT name FROM categories ORDER BY name LIMIT 1500')],
                'format':[r[0] for r in c.execute('SELECT DISTINCT extension FROM files ORDER BY extension LIMIT 150') if r[0]],
                'series':[r[0] for r in c.execute('SELECT DISTINCT name FROM series_catalog ORDER BY name LIMIT 1500')],
                'language':[r[0] for r in c.execute('SELECT DISTINCT language FROM books WHERE language IS NOT NULL ORDER BY language LIMIT 150')],
                'publisher':[r[0] for r in c.execute('SELECT DISTINCT publisher FROM books WHERE publisher IS NOT NULL ORDER BY publisher LIMIT 500')],
            }
        return data

    @app.post('/api/query/books')
    def advanced_books(payload:dict):
        with db() as c: result=query_books(c,payload)
        result['items']=[row(x) for x in result['items']]
        return result

    @app.post('/api/query/series')
    def advanced_series(payload:dict):
        with db() as c:return query_series(c,payload)

    @app.post('/api/query/quick-sort')
    def advanced_quick_sort(payload:dict):
        # A single SQL query makes randomized order stable within one batch.
        size=payload.get('per_page',50)
        if type(size)!=int or not 1<=size<=1000:raise HTTPException(422,'Batch must contain 1–1000 books')
        page=payload.get('page',1)
        if type(page)!=int or not 1<=page<=100000:raise HTTPException(422,'Invalid page')
        sort=payload.get('sort',[])
        randomize=bool(payload.get('random',False))
        if randomize and sort:raise HTTPException(422,'Cannot combine random order with multiple sorts')
        with db() as c:
            if not randomize:
                from .advanced_query import query_books
                result=query_books(c,payload,max_per_page=1000)
            else:
                result=query_books(c,{**payload,'sort':[]},max_per_page=1000,randomize=True)
        result['items']=[row(x) for x in result['items']]
        return result

    @app.post('/api/query/reviews')
    def advanced_reviews(payload:dict):
        with db() as c:return query_reviews(c,payload)

    @app.get('/api/query/views')
    def list_saved_views(scope:str='books'):
        if scope not in ('books','series','reading','quick','review','exports','series_members'):raise HTTPException(422,'Invalid view scope')
        with db() as c:
            rows=c.execute('SELECT id,scope,name,definition,created_at,updated_at FROM saved_views WHERE scope=? ORDER BY name COLLATE NOCASE',(scope,)).fetchall()
        return {'items':[{'id':r['id'],'scope':r['scope'],'name':r['name'],'query':json.loads(r['definition']),'created_at':r['created_at'],'updated_at':r['updated_at']} for r in rows]}

    @app.post('/api/query/views')
    def save_view(payload:dict):
        scope=payload.get('scope');name=payload.get('name');definition=payload.get('query')
        if scope not in ('books','series','reading','quick','review','exports','series_members'):raise HTTPException(422,'Invalid scope')
        if not isinstance(name,str) or not 1<=len(name.strip())<=80:raise HTTPException(422,'Name must be 1–80 characters')
        if not isinstance(definition,dict):raise HTTPException(422,'Invalid query')
        # Validate before writing, even when no book matches.
        with db() as c:
            if scope=='series':query_series(c,{**definition,'per_page':1})
            elif scope=='review':query_reviews(c,{**definition,'per_page':1})
            else:query_books(c,{**definition,'per_page':1})
            try:
                c.execute('INSERT INTO saved_views(scope,name,definition,created_at,updated_at) VALUES(?,?,?,?,?)',(scope,name.strip(),json.dumps(definition,ensure_ascii=False),now(),now()))
                ident=c.execute('SELECT last_insert_rowid()').fetchone()[0];c.commit()
            except Exception as exc:raise HTTPException(409,'A saved view with that name already exists') from exc
        return {'id':ident,'ok':True}

    @app.delete('/api/query/views/{view_id}')
    def delete_view(view_id:int):
        with db() as c:
            changed=c.execute('DELETE FROM saved_views WHERE id=?',(view_id,)).rowcount;c.commit()
        if not changed:raise HTTPException(404,'View not found')
        return {'ok':True}

    @app.get('/api/health')
    def health(): return {'ok':True,'version':'2.0'}
    @app.get('/api/books')
    def books(q:str='', status:str='', series:str='', category:str='', folder:str='', visibility:str='',sort:str='', include_subfolders:bool|None=None, page:int=Query(1,ge=1), per_page:int|None=Query(None,ge=1,le=200)):
        with db() as c: prefs=read_settings(c)
        if include_subfolders is None: include_subfolders=prefs['library.include_subfolders']
        visibility=visibility or prefs['library.default_visibility']
        sort=sort or prefs['library.default_sort']
        per_page=per_page or prefs['library.page_size']
        wh=['1=1']; args=[]
        if q:wh.append('(b.title LIKE ? OR b.authors LIKE ? OR COALESCE(b.series,\'\') LIKE ?)');args += [f'%{q}%']*3
        if status:wh.append("COALESCE(r.status,'unanswered')=?");args.append(status)
        if series:wh.append('b.series=?');args.append(series)
        if category:wh.append('EXISTS(SELECT 1 FROM book_categories bc JOIN categories cat ON cat.id=bc.category_id WHERE bc.book_id=b.id AND cat.name=?)');args.append(category)
        if folder:
            normalized=folder.rstrip('/\\').replace('\\','/')
            if include_subfolders:
                wh.append("EXISTS (SELECT 1 FROM files f WHERE f.book_id=b.id AND SUBSTR(REPLACE(f.path, CHAR(92), '/'), 1, LENGTH(?)+1) = ?)")
                args += [normalized, normalized+'/']
            else:
                wh.append("EXISTS (SELECT 1 FROM files f WHERE f.book_id=b.id AND SUBSTR(REPLACE(f.path, CHAR(92), '/'), 1, LENGTH(?)+1) = ? AND INSTR(SUBSTR(REPLACE(f.path, CHAR(92), '/'), LENGTH(?)+2), '/') = 0)")
                args += [normalized,normalized+'/',normalized]
        if visibility=='visible':wh.append('b.hidden=0')
        elif visibility=='hidden':wh.append('b.hidden=1')
        elif visibility!='all':raise HTTPException(422,'Invalid visibility')
        order={'title':'b.title COLLATE NOCASE','author':'b.authors COLLATE NOCASE','recent':'b.updated_at DESC','series':'b.series COLLATE NOCASE,b.series_index'}.get(sort,'b.title COLLATE NOCASE')
        base=' FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE '+' AND '.join(wh)
        with db() as c:
            total=c.execute('SELECT COUNT(*)'+base,args).fetchone()[0]
            data=c.execute('SELECT b.*,COALESCE(r.status,\'unanswered\') reading_status'+base+f' ORDER BY {order},b.id LIMIT ? OFFSET ?',args+[per_page,(page-1)*per_page]).fetchall()
        return {'items':[row(x) for x in data],'total':total,'page':page,'per_page':per_page}
    @app.get('/api/quick-sort/authors')
    def quick_authors():
        with db() as c:
            values=c.execute('SELECT authors FROM books').fetchall()
        names=set()
        for r in values:
            for name in jsonarr(r['authors']):
                if isinstance(name,str) and name.strip():names.add(name.strip())
        return {'items':sorted(names,key=str.casefold)}

    @app.get('/api/quick-sort/queue')
    def quick_queue(scope:str='all',value:str='',order:str='title',size:int=Query(50,ge=1,le=1000),
                    offset:int=Query(0,ge=0),include_classified:bool=False,include_subfolders:bool=True):
        if scope not in ('all','series','folder','author'):raise HTTPException(422,'Invalid scope')
        if order not in ('title','reverse','random','series','author'):raise HTTPException(422,'Invalid order')
        wh=['b.hidden=0'];args=[]
        if not include_classified:wh.append("COALESCE(r.status,'unanswered')='unanswered'")
        if scope!='all':
            if not value.strip():raise HTTPException(422,'A scope value is required')
            if scope=='series':wh.append('b.series=?');args.append(value)
            elif scope=='author':wh.append('EXISTS (SELECT 1 FROM json_each(b.authors) WHERE LOWER(value)=LOWER(?))');args.append(value)
            else:
                folder=value.rstrip('/\\').replace('\\','/')
                if include_subfolders:
                    wh.append("EXISTS(SELECT 1 FROM files f WHERE f.book_id=b.id AND SUBSTR(REPLACE(f.path,CHAR(92),'/'),1,LENGTH(?)+1)=?)")
                    args.extend([folder,folder+'/'])
                else:
                    wh.append("EXISTS(SELECT 1 FROM files f WHERE f.book_id=b.id AND SUBSTR(REPLACE(f.path,CHAR(92),'/'),1,LENGTH(?)+1)=? AND INSTR(SUBSTR(REPLACE(f.path,CHAR(92),'/'),LENGTH(?)+2),'/')=0)")
                    args.extend([folder,folder+'/',folder])
        orders={'title':'b.title COLLATE NOCASE,b.id','reverse':'b.title COLLATE NOCASE DESC,b.id DESC','random':'RANDOM()','series':'b.series_index IS NULL,b.series_index,b.title COLLATE NOCASE,b.id','author':'b.authors COLLATE NOCASE,b.title COLLATE NOCASE,b.id'}
        base=' FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE '+' AND '.join(wh)
        with db() as c:
            total=c.execute('SELECT COUNT(*)'+base,args).fetchone()[0]
            results=c.execute("SELECT b.*,COALESCE(r.status,'unanswered') reading_status"+base+' ORDER BY '+orders[order]+' LIMIT ? OFFSET ?',args+[size,offset]).fetchall()
        return {'items':[row(x) for x in results],'total':total,'offset':offset,'size':size}

    @app.get('/api/books/{book_id}')
    def book(book_id:int):
        with db() as c:
            b=c.execute('SELECT * FROM books WHERE id=?',(book_id,)).fetchone()
            if not b:raise HTTPException(404)
            r=c.execute('SELECT * FROM reading WHERE book_id=?',(book_id,)).fetchone()
            files=c.execute('SELECT * FROM files WHERE book_id=?',(book_id,)).fetchall()
            tags=c.execute('SELECT cat.name,bc.confidence,bc.confirmed FROM book_categories bc JOIN categories cat ON cat.id=bc.category_id WHERE bc.book_id=?',(book_id,)).fetchall()
            folders=c.execute('SELECT fc.folder_path,fc.category FROM folder_categories fc JOIN files f ON f.id=fc.file_id WHERE f.book_id=?',(book_id,)).fetchall()
            sessions=c.execute('SELECT * FROM reading_sessions WHERE book_id=? ORDER BY id DESC',(book_id,)).fetchall()
            reviews=c.execute('SELECT * FROM review_queue WHERE book_id=? AND resolved=0',(book_id,)).fetchall()
            links=c.execute('SELECT l.*,other.title candidate_title FROM book_links l JOIN books other ON other.id=CASE WHEN l.book_id=? THEN l.candidate_id ELSE l.book_id END WHERE l.book_id=? OR l.candidate_id=?',(book_id,book_id,book_id)).fetchall()
        return {'book':row(b),'reading':row(r),'files':[dict(x) for x in files],'categories':[dict(x) for x in tags],'folders':[dict(x) for x in folders],'sessions':[dict(x) for x in sessions],'reviews':[dict(x) for x in reviews],'links':[dict(x) for x in links]}
    @app.patch('/api/books/{book_id}')
    def update_book(book_id:int, payload:BookUpdate):
        values=payload.model_dump(exclude_unset=True)
        with db() as c:
            exists(c,book_id)
            if 'status' in values: status_update(c,book_id,values.pop('status'))
            bk={k:values.pop(k) for k in list(values) if k in (
                'hidden','series','series_index','title','subtitle','authors','isbn10','isbn13',
                'language','publisher','published','description','page_count','word_count','cover_url')}
            if 'title' in bk: bk['title']=bk['title'].strip()
            if 'title' in bk and not bk['title']: raise HTTPException(422,'Title cannot be empty')
            if 'authors' in bk: bk['authors']=json.dumps([a.strip() for a in bk['authors'] if a.strip()],ensure_ascii=False) if bk['authors'] is not None else '[]'
            if bk:
                c.execute('UPDATE books SET '+','.join(f'{k}=?' for k in bk)+',updated_at=? WHERE id=?',[*bk.values(),now(),book_id])
                if bk.get('series'):
                    c.execute('INSERT OR IGNORE INTO series_catalog(name,updated_at) VALUES(?,?)',(bk['series'],now()))
            if values:
                allowed={'started','finished','minutes_read','current_page','rating','notes'}
                values={k:(str(v) if isinstance(v,date) else v) for k,v in values.items() if k in allowed}
                if values:
                    c.execute('INSERT OR IGNORE INTO reading(book_id,updated_at) VALUES(?,?)',(book_id,now()))
                    c.execute('UPDATE reading SET '+','.join(f'{k}=?' for k in values)+',updated_at=? WHERE book_id=?',[*values.values(),now(),book_id])
            c.commit()
        return {'ok':True}
    @app.post('/api/books/{book_id}/sessions')
    def add_reading_session(book_id:int,payload:ReadingSession):
        if payload.started and payload.finished and payload.finished<payload.started:raise HTTPException(422,'Finish before start')
        with db() as c:
            exists(c,book_id)
            c.execute('INSERT INTO reading_sessions(book_id,started,finished,minutes_read,pages_read,note) VALUES(?,?,?,?,?,?)',
                (book_id,str(payload.started) if payload.started else None,str(payload.finished) if payload.finished else None,payload.minutes_read,payload.pages_read,payload.note))
            c.execute('INSERT OR IGNORE INTO reading(book_id,updated_at) VALUES(?,?)',(book_id,now()))
            c.execute('UPDATE reading SET minutes_read=COALESCE(minutes_read,0)+?,updated_at=? WHERE book_id=?',(payload.minutes_read or 0,now(),book_id))
            c.commit()
        return {'ok':True}
    @app.post('/api/books/{book_id}/categories')
    def add_category(book_id:int,name:str):
        name=name.strip()
        if not 1<=len(name)<=80:raise HTTPException(422,'Invalid category')
        with db() as c:
            exists(c,book_id)
            c.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(name,))
            category_id=c.execute('SELECT id FROM categories WHERE name=? COLLATE NOCASE',(name,)).fetchone()[0]
            c.execute('INSERT INTO book_categories(book_id,category_id,confidence,source,confirmed) VALUES(?,?,1,?,1) ON CONFLICT(book_id,category_id) DO UPDATE SET confidence=1,source=excluded.source,confirmed=1',(book_id,category_id,'manual'))
            c.commit()
        return {'ok':True}
    @app.post('/api/books/bulk')
    def bulk(payload:BulkRequest):
        ids=list(dict.fromkeys(payload.ids)); action=payload.action
        if action not in STATES and action not in ('hide','unhide','unassign_series','assign_series'):raise HTTPException(422,'Invalid action')
        if action=='assign_series' and (not payload.series_name or not payload.series_name.strip() or len(payload.series_name)>250):raise HTTPException(422,'A valid series name is required')
        with db() as c:
            if action=='assign_series':c.execute('INSERT OR IGNORE INTO series_catalog(name,updated_at) VALUES(?,?)',(payload.series_name.strip(),now()))
            actual={x[0] for x in c.execute('SELECT id FROM books WHERE id IN ('+','.join('?'*len(ids))+')',ids)}
            for book_id in ids:
                if book_id not in actual:continue
                if action in STATES:status_update(c,book_id,action)
                elif action in ('hide','unhide'):c.execute('UPDATE books SET hidden=? WHERE id=?',(int(action=='hide'),book_id))
                elif action=='assign_series':c.execute('UPDATE books SET series=?,series_index=NULL,updated_at=? WHERE id=?',(payload.series_name.strip(),now(),book_id))
                else:c.execute('UPDATE books SET series=NULL,series_index=NULL WHERE id=?',(book_id,))
            c.commit()
        return {'ok':True,'changed':len(actual)}
    @app.get('/api/series')
    def series(q:str=''):
        with db() as c:
            rows=c.execute('''SELECT s.*,COUNT(b.id) book_count,SUM(CASE WHEN r.status='finished' THEN 1 ELSE 0 END) finished_count,
            SUM(CASE WHEN b.series_index IS NULL THEN 1 ELSE 0 END) unordered_count,
            (SELECT id FROM books WHERE series=s.name AND cover_path IS NOT NULL ORDER BY series_index LIMIT 1) cover_id
            FROM series_catalog s LEFT JOIN books b ON b.series=s.name LEFT JOIN reading r ON r.book_id=b.id
            WHERE s.name LIKE ? GROUP BY s.id ORDER BY s.name COLLATE NOCASE''',(f'%{q}%',)).fetchall()
        return {'items':[dict(x) for x in rows]}
    @app.get('/api/series/{series_id}')
    def series_detail(series_id:int):
        with db() as c:
            s=c.execute('SELECT * FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not s:raise HTTPException(404)
            members=c.execute('SELECT b.*,COALESCE(r.status,\'unanswered\') reading_status FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE b.series=? ORDER BY b.series_index IS NULL,b.series_index,b.title',(s['name'],)).fetchall()
        return {'series':dict(s),'members':[row(m) for m in members]}
    @app.post('/api/series')
    def new_series(payload:SeriesUpdate):
        name=(payload.name or '').strip()
        if not name:raise HTTPException(422,'Series name required')
        with db() as c:
            try:c.execute('INSERT INTO series_catalog(name,description,notes,updated_at) VALUES(?,?,?,?)',(name,payload.description,payload.notes,now()));ident=c.execute('SELECT last_insert_rowid()').fetchone()[0];c.commit()
            except Exception as ex:raise HTTPException(409,'Series name already exists') from ex
        return {'id':ident}
    @app.patch('/api/series/{series_id}')
    def update_series(series_id:int,payload:SeriesUpdate):
        fields=payload.model_dump(exclude_unset=True)
        if not fields:return {'ok':True}
        if 'name' in fields and not (fields['name'] or '').strip():raise HTTPException(422,'Empty series name')
        with db() as c:
            old=c.execute('SELECT name FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not old:raise HTTPException(404)
            if 'name' in fields:c.execute('UPDATE books SET series=? WHERE series=?',(fields['name'],old['name']))
            try:c.execute('UPDATE series_catalog SET '+','.join(f'{k}=?' for k in fields)+',updated_at=? WHERE id=?',[*fields.values(),now(),series_id]);c.commit()
            except Exception as ex:raise HTTPException(409,'Series name conflict') from ex
        return {'ok':True}
    @app.put('/api/series/{series_id}/members')
    def add_member(series_id:int,payload:SeriesMember):
        with db() as c:
            s=c.execute('SELECT name FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not s:raise HTTPException(404)
            exists(c,payload.book_id)
            c.execute('UPDATE books SET series=?,series_index=?,updated_at=? WHERE id=?',(s['name'],payload.index,now(),payload.book_id));c.commit()
        return {'ok':True}
    @app.delete('/api/series/{series_id}/members/{book_id}')
    def remove_member(series_id:int,book_id:int):
        with db() as c:
            s=c.execute('SELECT name FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not s:raise HTTPException(404)
            c.execute('UPDATE books SET series=NULL,series_index=NULL WHERE id=? AND series=?',(book_id,s['name']));c.commit()
        return {'ok':True}
    @app.delete('/api/series/{series_id}')
    def delete_series(series_id:int):
        with db() as c:
            s=c.execute('SELECT name FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not s:raise HTTPException(404)
            c.execute('UPDATE books SET series=NULL,series_index=NULL WHERE series=?',(s['name'],))
            c.execute('DELETE FROM series_catalog WHERE id=?',(series_id,));c.commit()
        return {'ok':True}
    @app.get('/api/reviews')
    def reviews(limit:int=Query(100,ge=1,le=500)):
        with db() as c:
            rr=c.execute('SELECT r.*,b.title,b.authors FROM review_queue r JOIN books b ON b.id=r.book_id WHERE r.resolved=0 ORDER BY r.confidence LIMIT ?', (limit,)).fetchall()
        return {'items':[dict(x) for x in rr]}
    @app.post('/api/reviews/{review_id}')
    def resolve(review_id:int,accept:bool=True):
        with db() as c:
            item=c.execute('SELECT * FROM review_queue WHERE id=?',(review_id,)).fetchone()
            if not item:raise HTTPException(404)
            if accept and item['field'] in ('title','series','series_index','language','publisher','published','isbn13','isbn10'):
                c.execute('UPDATE books SET '+item['field']+'=?,updated_at=? WHERE id=?',(item['suggested'],now(),item['book_id']))
            c.execute('UPDATE review_queue SET resolved=1 WHERE id=?',(review_id,));c.commit()
        return {'ok':True}
    @app.get('/api/stats')
    def stats():
        with db() as c:
            counts={k:c.execute(f'SELECT COUNT(*) FROM {v}').fetchone()[0] for k,v in [('books','books'),('files','files'),('series','series_catalog'),('reviews','review_queue WHERE resolved=0'),('sessions','reading_sessions')]}
            counts['hidden']=c.execute('SELECT COUNT(*) FROM books WHERE hidden=1').fetchone()[0]
            counts['covers']=c.execute('SELECT COUNT(*) FROM books WHERE cover_path IS NOT NULL').fetchone()[0]
            counts['minutes_read']=c.execute('SELECT COALESCE(SUM(minutes_read),0) FROM reading').fetchone()[0]
            status=[dict(x) for x in c.execute("SELECT COALESCE(r.status,'unanswered') name,COUNT(*) count FROM books b LEFT JOIN reading r ON r.book_id=b.id GROUP BY 1 ORDER BY count DESC")]
            formats=[dict(x) for x in c.execute('SELECT extension name,COUNT(*) count FROM files GROUP BY extension ORDER BY count DESC')]
            months=[dict(x) for x in c.execute("SELECT SUBSTR(finished,1,7) month,COUNT(*) count FROM reading WHERE finished IS NOT NULL GROUP BY 1 ORDER BY 1 DESC LIMIT 12")]
        return {'counts':counts,'statuses':status,'formats':formats,'months':months}
    @app.get('/api/options')
    def options():
        with db() as c:
            cats=[x[0] for x in c.execute('SELECT name FROM categories ORDER BY name')]
            file_paths=[x[0] for x in c.execute('SELECT DISTINCT path FROM files WHERE path IS NOT NULL')]
            folders=sorted({str(Path(path.replace(chr(92), '/')).parent) for path in file_paths if '/' in path.replace(chr(92), '/')},key=str.casefold)
        return {'statuses':sorted(STATES),'categories':cats,'folders':folders,'fields':FIELDS,'templates':list(TEMPLATES)}
    @app.get('/api/cover/{book_id}')
    def cover(book_id:int):
        with db() as c:b=c.execute('SELECT cover_path FROM books WHERE id=?',(book_id,)).fetchone()
        if not b or not b['cover_path']:raise HTTPException(404)
        p=Path(b['cover_path']);base=location.resolve().parent/'covers'
        if not p.is_file() or not p.resolve().is_relative_to(base.resolve()):raise HTTPException(404)
        return FileResponse(p,media_type='image/jpeg')
    lock=threading.Lock(); jobs={'scan':{'status':'idle'},'enrich':{'status':'idle'}};cancel=threading.Event()
    @app.get('/api/jobs/{kind}')
    def job_status(kind:str):
        if kind not in jobs:raise HTTPException(404)
        with lock:return JSONResponse(dict(jobs[kind]),headers={'Cache-Control':'no-store'})
    @app.post('/api/jobs/{kind}')
    def start_job(kind:str,payload:JobRequest):
        if kind not in jobs:raise HTTPException(404)
        if kind=='enrich' and payload.mode not in ('all','missing','covers'):raise HTTPException(422,'Invalid enrichment mode')
        folder=Path(payload.folder).expanduser().resolve() if kind=='scan' else None
        if folder is not None and not folder.is_dir():raise HTTPException(422,'Folder is not accessible to the server')
        with lock:
            if any(v.get('status')=='running' for v in jobs.values()):raise HTTPException(409,'Another job is running')
            jobs[kind]={'status':'running','processed':0,'events':[],'last_id':payload.start_after,'result':{},'current':'','folder':str(folder) if folder else ''}
            cancel.clear()
        def update(event):
            with lock:
                j=jobs[kind];j['processed']=event.get('processed',j['processed']);j['current']=event.get('title') or event.get('path') or j['current'];j['stage']=event.get('stage',event.get('event',''))
                if 'total' in event:j['total']=event['total']
                if 'last_id' in event:j['last_id']=event['last_id']
                if 'result' in event:j['result']=event['result']
                if len(j['events'])<1000:j['events'].append(f"{j['stage']}: {j['current']}")
                else:j['events']=j['events'][-499:]+[f"{j['stage']}: {j['current']}"]
        def work():
            try:
                with db() as c:
                    result=scan(c,folder,online=payload.online,progress=update) if kind=='scan' else enrich_existing(c,update,start_after=payload.start_after,limit=payload.limit,mode=payload.mode,stop=cancel.is_set)
                with lock:jobs[kind].update(status='cancelled' if result.get('cancelled') else 'completed',result=result,last_id=result.get('last_id',jobs[kind].get('last_id',0)))
            except Exception as exc:
                with lock:jobs[kind].update(status='failed',error=f'{type(exc).__name__}: {exc}')
        threading.Thread(target=work,daemon=True,name=f'bookledger-{kind}').start()
        return {'status':'running'}
    @app.post('/api/jobs/enrich/cancel')
    def cancel_job():cancel.set();return {'ok':True}
    @app.get('/api/exports/preset/{kind}')
    def preset(kind:str):
        if kind not in ('goodreads','storygraph','json'):raise HTTPException(404)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/('books.json' if kind=='json' else 'books.csv')
            with db() as c:
                if kind=='json':export_json(c,p)
                else:export_csv(c,p)
            data=p.read_bytes()
        ext='json' if kind=='json' else 'csv'
        return Response(data,media_type='application/json' if ext=='json' else 'text/csv',headers={'Content-Disposition':f'attachment; filename="bookledger-{kind}.{ext}"'})
    @app.post('/api/exports/custom')
    def custom_export(payload:ExportRequest):
        if not payload.fields or any(f not in FIELDS for f in payload.fields):raise HTTPException(422,'Unknown fields')
        with db() as c:
            ids=None
            if payload.advanced_query is not None:
                ids=[]
                q={**payload.advanced_query,'per_page':200}
                q.pop('offset',None)
                offset=0
                while True:
                    batch=query_books(c,{**q,'page':offset//200+1})
                    ids.extend(item['id'] for item in batch['items'])
                    offset+=len(batch['items'])
                    if not batch['items'] or offset>=batch['total']:break
            data=export_custom(c,payload.fields,payload.status,payload.category,payload.series,payload.search,book_ids=ids)
        return Response(data,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="bookledger-custom.csv"'})
    # Fallback old UI at /legacy; no ebook files are edited by either UI.
    app.mount('/legacy',legacy_app(location))
    dist=ROOT/'frontend_dist'
    if (dist/'assets').exists():app.mount('/assets',StaticFiles(directory=dist/'assets'),name='assets')
    @app.get('/favicon.svg')
    def favicon():return FileResponse(ROOT/'favicon.svg',media_type='image/svg+xml')
    @app.get('/{path:path}',include_in_schema=False)
    def spa(path:str=''):
        file=dist/path
        if path and file.is_file() and file.resolve().is_relative_to(dist.resolve()):return FileResponse(file)
        if (dist/'index.html').exists():return FileResponse(dist/'index.html')
        return Response('Frontend build missing. Run npm install && npm run build inside frontend/',status_code=503)
    return app
