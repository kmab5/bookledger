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

ROOT = Path(__file__).parent
STATES = {'unanswered','not_read','want_to_read','reading','finished','abandoned','on_hold','rereading'}

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
    status: str = ''
    category: str = ''
    series: str = ''
    search: str = ''


def create_app(db_path):
    app = FastAPI(title='BookLedger API', version='2.0')
    location = Path(db_path).expanduser()
    location.parent.mkdir(parents=True, exist_ok=True)
    with connect(location): pass
    def db(): return connect(location)
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
    @app.get('/api/health')
    def health(): return {'ok':True,'version':'2.0'}
    @app.get('/api/books')
    def books(q:str='', status:str='', series:str='', category:str='', visibility:str='visible',sort:str='title', page:int=Query(1,ge=1), per_page:int=Query(48,ge=1,le=200)):
        wh=['1=1']; args=[]
        if q:wh.append('(b.title LIKE ? OR b.authors LIKE ? OR COALESCE(b.series,\'\') LIKE ?)');args += [f'%{q}%']*3
        if status:wh.append("COALESCE(r.status,'unanswered')=?");args.append(status)
        if series:wh.append('b.series=?');args.append(series)
        if category:wh.append('EXISTS(SELECT 1 FROM book_categories bc JOIN categories cat ON cat.id=bc.category_id WHERE bc.book_id=b.id AND cat.name=?)');args.append(category)
        if visibility=='visible':wh.append('b.hidden=0')
        elif visibility=='hidden':wh.append('b.hidden=1')
        elif visibility!='all':raise HTTPException(422,'Invalid visibility')
        order={'title':'b.title COLLATE NOCASE','author':'b.authors COLLATE NOCASE','recent':'b.updated_at DESC','series':'b.series COLLATE NOCASE,b.series_index'}.get(sort,'b.title COLLATE NOCASE')
        base=' FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE '+' AND '.join(wh)
        with db() as c:
            total=c.execute('SELECT COUNT(*)'+base,args).fetchone()[0]
            data=c.execute('SELECT b.*,COALESCE(r.status,\'unanswered\') reading_status'+base+f' ORDER BY {order},b.id LIMIT ? OFFSET ?',args+[per_page,(page-1)*per_page]).fetchall()
        return {'items':[row(x) for x in data],'total':total,'page':page,'per_page':per_page}
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
        if action not in STATES and action not in ('hide','unhide','unassign_series'):raise HTTPException(422,'Invalid action')
        with db() as c:
            actual={x[0] for x in c.execute('SELECT id FROM books WHERE id IN ('+','.join('?'*len(ids))+')',ids)}
            for book_id in ids:
                if book_id not in actual:continue
                if action in STATES:status_update(c,book_id,action)
                elif action in ('hide','unhide'):c.execute('UPDATE books SET hidden=? WHERE id=?',(int(action=='hide'),book_id))
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
        return {'statuses':sorted(STATES),'categories':cats,'fields':FIELDS,'templates':list(TEMPLATES)}
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
        with db() as c:data=export_custom(c,payload.fields,payload.status,payload.category,payload.series,payload.search)
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
