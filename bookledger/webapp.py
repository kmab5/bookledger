from __future__ import annotations
import html, json, os, secrets, sqlite3
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from .core import connect, jsonarr, now

STATES=['unanswered','not_read','want_to_read','reading','finished','abandoned','on_hold','rereading']
LABELS={'unanswered':'Not answered','not_read':'Not read','want_to_read':'Want to read','reading':'Currently reading','finished':'Finished','abandoned':'Started & abandoned','on_hold':'On hold','rereading':'Rereading'}
CSS='''*{box-sizing:border-box}body{font-family:system-ui,Segoe UI,sans-serif;margin:0;background:#f6f7f9;color:#1c2633}header{background:#16283f;color:white;padding:20px}header a{color:white;margin-right:22px;text-decoration:none}main{max-width:1150px;margin:24px auto;padding:0 16px}.panel{background:white;border:1px solid #e0e6ec;border-radius:14px;padding:20px;margin-bottom:16px;box-shadow:0 3px 14px #172b4410}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:12px}.muted{color:#637084;font-size:.91rem}.tag{background:#e7eef7;border-radius:6px;padding:3px 7px;font-size:.8rem;display:inline-block;margin:2px}a{color:#1764ac}label{display:block;font-size:.9rem;margin-top:12px}input,select,textarea{font:inherit;width:100%;padding:9px;border:1px solid #b9c5d0;border-radius:8px;background:white}button{background:#1764ac;color:white;padding:10px 15px;border:0;border-radius:8px;cursor:pointer;margin-top:12px}button.ghost{background:#53647a}.toolbar{display:flex;gap:10px;flex-wrap:wrap}.toolbar>*{flex:1;min-width:150px}.badge{font-size:.78rem;padding:4px 7px;border-radius:8px;background:#f5e8c8}.good{background:#d8f2df}.split{display:grid;grid-template-columns:2fr 1fr;gap:18px}pre{white-space:pre-wrap;word-break:break-all}details{margin-top:12px}@media(max-width:700px){.split{grid-template-columns:1fr}header a{display:inline-block;margin-bottom:10px}}'''
CSS += "/* BOOKLEDGER KMAB BRAND THEME */\n/* BookLedger product UI. Inject after the original inline CSS in webapp.py. */\n\n:root{color-scheme:dark;--bg:#0e0e11;--surface:#17171b;--surface2:#1e1e24;--line:#2a2a31;--text:#edebe4;--muted:#9a9aa6;--purple:#b24bff;--green:#3de08a;--amber:#f5c451}\nbody{background:var(--bg)!important;color:var(--text)!important;font-family:'Space Grotesk',system-ui,sans-serif!important;line-height:1.6}\nheader{background:#15151a!important;border-bottom:1px solid var(--line)!important;padding:19px max(20px,calc((100vw - 1150px)/2))!important;display:flex;align-items:center;gap:32px;flex-wrap:wrap}\nheader strong{font-size:22px;letter-spacing:-1px;font-weight:700}header strong::after{content:'.';color:var(--purple)}header nav{display:flex;gap:17px;flex-wrap:wrap}header a{color:var(--muted)!important;margin:0!important;font-size:12px;transition:color .2s}header a:hover{color:var(--text)!important}\nmain{max-width:1150px!important;margin:35px auto!important;padding:0 20px!important}h1,h2,h3{letter-spacing:-.04em;font-weight:600;line-height:1.2}h1{font-size:clamp(32px,4vw,48px)}h2{font-size:24px}h3{font-size:20px}main>p{color:var(--muted)}\n.panel{background:var(--surface)!important;border:1px solid var(--line)!important;box-shadow:none!important;border-radius:12px!important;padding:23px!important;margin-bottom:14px!important}.panel:hover{border-color:#38313f!important}.muted{color:var(--muted)!important}.grid{gap:13px!important}\na{color:#d49aff}a:hover{color:#e3beff}label{color:var(--muted);font-size:12px!important;font-weight:500}\ninput,select,textarea{background:#101014!important;color:var(--text)!important;border:1px solid #3a3a44!important;border-radius:7px!important;padding:11px 12px!important;font-family:inherit!important;accent-color:var(--purple)}input:focus,select:focus,textarea:focus{outline:2px solid #b24bff66;outline-offset:1px;border-color:var(--purple)!important}input::placeholder{color:#777781}input[type=checkbox]{width:auto}\nbutton{background:var(--purple)!important;color:#100b17!important;font-weight:700!important;border-radius:7px!important;padding:11px 16px!important}button:hover{background:#c373ff!important}button.ghost{background:#27232e!important;color:var(--text)!important;border:1px solid #4a3b55!important}\n.tag{background:#2d2239!important;color:#d49aff!important;border:1px solid #4d3560;border-radius:5px!important}.badge{background:#3d321d!important;color:var(--amber)!important}.good{background:#183b28!important;color:var(--green)!important}.toolbar{align-items:end}.toolbar>button{flex:0 0 auto!important;min-width:90px!important}.toolbar>*{min-width:130px!important}pre,code{font-family:'Space Mono',monospace;background:#101014;border:1px solid var(--line);padding:12px;border-radius:7px;color:#b9f4d5;font-size:12px}summary{cursor:pointer;color:#d49aff}a:focus-visible,button:focus-visible{outline:2px solid var(--purple);outline-offset:3px}\n@media(max-width:700px){header{gap:14px}header nav{gap:12px}.split{grid-template-columns:1fr}.toolbar>button{width:100%;flex:1 1 100%!important}}\n"
def h(s):return html.escape(str(s if s is not None else ''),quote=True)
def layout(title,body):
    return HTMLResponse(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(title)} - BookLedger</title><link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin><link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet"><style>{CSS}</style></head><body><header><strong>BookLedger</strong><nav><a href="/">Library</a><a href="/review">Metadata review</a><a href="/reading">Have you read it?</a><a href="/stats">Statistics</a><a href="/series">Series</a><a href="/duplicates">Possible editions</a></nav></header><main>{body}</main></body></html>')
def safe_date(v):
    if not v: return None
    from datetime import date
    try: return date.fromisoformat(v).isoformat()
    except ValueError: raise HTTPException(422,'Invalid date')
def create_app(db_path):
    app=FastAPI(title='BookLedger',docs_url=None,redoc_url=None)
    app.state.db_path=str(Path(db_path).expanduser());app.state.csrf=secrets.token_urlsafe(32)
    def db():return connect(app.state.db_path)
    def token():return f'<input type="hidden" name="csrf" value="{h(app.state.csrf)}">'
    def guard(csrf):
        if not secrets.compare_digest(csrf,app.state.csrf):raise HTTPException(403,'Invalid form token')
    def go(url):return RedirectResponse(url,status_code=303)
    @app.get('/',response_class=HTMLResponse)
    def index(q:str='',status:str='',category:str='',series:str='',sort:str='title'):
        with db() as c:
            where=['1=1'];args=[]
            if q:
                where.append('(b.title LIKE ? OR b.authors LIKE ? OR b.series LIKE ?)');args += [f'%{q}%']*3
            if status:
                where.append('r.status=?');args.append(status)
            if series:
                where.append('b.series=?');args.append(series)
            if category:
                where.append('EXISTS (SELECT 1 FROM book_categories bc JOIN categories cat ON cat.id=bc.category_id WHERE bc.book_id=b.id AND cat.name=?)');args.append(category)
            order={'title':'b.title COLLATE NOCASE','author':'b.authors COLLATE NOCASE','date':'b.created_at DESC','series':'b.series COLLATE NOCASE,b.series_index'}.get(sort,'b.title COLLATE NOCASE')
            rows=c.execute(f'SELECT b.*,r.status FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE {" AND ".join(where)} ORDER BY {order} LIMIT 1000',args).fetchall()
            categories=[x[0] for x in c.execute('SELECT name FROM categories ORDER BY name')]
            series_names=[x[0] for x in c.execute('SELECT DISTINCT series FROM books WHERE series IS NOT NULL AND series<>"" ORDER BY series')]
            count=c.execute('SELECT COUNT(*) FROM books').fetchone()[0]; pending=c.execute('SELECT COUNT(*) FROM review_queue WHERE resolved=0').fetchone()[0]
        options=lambda opts,current:''.join(f'<option value="{h(v)}" {"selected" if v==current else ""}>{h(n)}</option>' for v,n in opts)
        filters=f'<form method="get" class="panel toolbar"><input name="q" placeholder="Title, author or series" value="{h(q)}"><select name="status">{options([("","Any reading status")]+[(x,LABELS[x]) for x in STATES],status)}</select><select name="category">{options([("","Any category")]+[(x,x) for x in categories],category)}</select><select name="series">{options([("","Any series")]+[(x,x) for x in series_names],series)}</select><select name="sort">{options([("title","Title"),("author","Author"),("date","Recently indexed"),("series","Series order")],sort)}</select><button>Filter</button></form>'
        cards=''.join(f'<article class="panel"><a href="/book/{b["id"]}"><strong>{h(b["title"])}</strong></a><p class="muted">{h(", ".join(jsonarr(b["authors"])))}</p><p>{h(b["series"] or "")}{" · #"+h(b["series_index"]) if b["series_index"] is not None else ""}</p><span class="tag">{h(LABELS.get(b["status"],"Not answered"))}</span> {"<span class=\"badge\">Needs review</span>" if b["needs_review"] else ""}</article>' for b in rows)
        return layout('Library',f'<h1>Library</h1><p>{count} titles · {pending} unresolved metadata suggestions · {len(rows)} shown</p>{filters}<section class="grid">{cards or "<p>No books found. Run bookledger scan first.</p>"}</section>')
    @app.get('/book/{book_id}',response_class=HTMLResponse)
    def book(book_id:int):
        with db() as c:
            b=c.execute('SELECT * FROM books WHERE id=?',(book_id,)).fetchone()
            if not b:raise HTTPException(404)
            r=c.execute('SELECT * FROM reading WHERE book_id=?',(book_id,)).fetchone()
            files=c.execute('SELECT * FROM files WHERE book_id=?',(book_id,)).fetchall()
            cats=c.execute('SELECT c.name,bc.confidence,bc.confirmed FROM book_categories bc JOIN categories c ON c.id=bc.category_id WHERE bc.book_id=?',(book_id,)).fetchall()
            sessions=c.execute('SELECT * FROM reading_sessions WHERE book_id=? ORDER BY id DESC',(book_id,)).fetchall()
        fields=''.join(f'<p><b>{h(key.replace("_"," ").title())}:</b> {h(", ".join(jsonarr(b[key])) if key in ("authors","subjects") else b[key])}</p>' for key in ('isbn13','isbn10','language','publisher','published','description','series','series_index','page_count','page_count_kind','word_count','cover_url') if b[key])
        statusopts=''.join(f'<option value="{s}" {"selected" if r and r["status"]==s else ""}>{LABELS[s]}</option>' for s in STATES)
        def val(k):return h(r[k] if r and r[k] is not None else '')
        reading=f'''<form method="post" action="/book/{book_id}/reading" class="panel">{token()}<h2>Reading record</h2><label>Status<select name="status">{statusopts}</select></label><label>Started<input type="date" name="started" value="{val('started')}"></label><label>Finished<input type="date" name="finished" value="{val('finished')}"></label><label>Time read (minutes)<input type="number" min="0" name="minutes_read" value="{val('minutes_read')}"></label><label>Current page<input type="number" min="0" name="current_page" value="{val('current_page')}"></label><label>Rating (0–5)<input type="number" min="0" max="5" step="0.5" name="rating" value="{val('rating')}"></label><label>Read count<input type="number" min="0" name="read_count" value="{val('read_count')}"></label><label>Notes<textarea name="notes" rows="5">{val('notes')}</textarea></label><button>Save reading record</button></form>'''
        sessionform=f'<form method="post" action="/book/{book_id}/session" class="panel">{token()}<h3>Add reading session</h3><label>Started<input type="date" name="started"></label><label>Finished<input type="date" name="finished"></label><label>Minutes<input type="number" min="0" name="minutes_read"></label><label>Pages read<input type="number" min="0" name="pages_read"></label><label>Note<input name="note"></label><button>Add session</button></form>'
        fileitems=''.join(f'<li>{h(x["path"])} · {x["bytes"]:,} bytes · {h(x["extension"])} {"(unavailable)" if x["missing"] else ""}{" · "+h(x["extract_error"]) if x["extract_error"] else ""}</li>' for x in files)
        category_form=f'<form method="post" action="/book/{book_id}/category">{token()}<label>Add category/shelf<input name="category" maxlength="80" required></label><button>Add category</button></form>'
        card=f'<section class="panel"><h1>{h(b["title"])}</h1><p>{h(", ".join(jsonarr(b["authors"])))}</p>{fields}<p>Categories: {" ".join(f"<span class=tag>{h(x[0])} · {int(x[1]*100)}%</span>" for x in cats)}</p>{category_form}<h3>Files (read-only references)</h3><ul>{fileitems}</ul><details><summary>Metadata sources & confidence</summary><pre>{h(json.dumps(json.loads(b["provenance_json"]),indent=2))}</pre><pre>{h(json.dumps(json.loads(b["confidence_json"]),indent=2))}</pre><pre>{h(json.dumps(json.loads(b["metadata_json"]),indent=2))}</pre></details></section>'
        sessions_html=''.join(f'<li>{h(x["started"])} → {h(x["finished"])} · {h(x["minutes_read"])} min · {h(x["note"])}</li>' for x in sessions)
        return layout(b['title'],f'<div class="split"><div>{card}<section class="panel"><h3>Reading sessions</h3><ul>{sessions_html or "No sessions yet"}</ul></section>{sessionform}</div><div>{reading}</div></div>')
    @app.post('/book/{book_id}/reading')
    def save_reading(book_id:int,csrf:str=Form(...),status:str=Form(...),started:str=Form(''),finished:str=Form(''),minutes_read:str=Form(''),current_page:str=Form(''),rating:str=Form(''),read_count:str=Form(''),notes:str=Form('')):
        guard(csrf)
        if status not in STATES: raise HTTPException(422,'Invalid status')
        def number(x,decimal=False):
            if not x:return None
            try:v=float(x) if decimal else int(x)
            except ValueError:raise HTTPException(422,'Invalid numeric value')
            if v<0 or (decimal and v>5):raise HTTPException(422,'Invalid numeric range')
            return v
        start=safe_date(started);finish=safe_date(finished)
        if start and finish and start>finish:raise HTTPException(422,'Finish before start')
        with db() as c:
            if not c.execute('SELECT 1 FROM books WHERE id=?',(book_id,)).fetchone():raise HTTPException(404)
            c.execute('INSERT INTO reading(book_id,status,started,finished,minutes_read,current_page,rating,notes,read_count,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(book_id) DO UPDATE SET status=excluded.status,started=excluded.started,finished=excluded.finished,minutes_read=excluded.minutes_read,current_page=excluded.current_page,rating=excluded.rating,notes=excluded.notes,read_count=excluded.read_count,updated_at=excluded.updated_at',(book_id,status,start,finish,number(minutes_read),number(current_page),number(rating,True),notes,number(read_count) or 0,now()));c.commit()
        return go(f'/book/{book_id}')
    @app.post('/book/{book_id}/session')
    def add_session(book_id:int,csrf:str=Form(...),started:str=Form(''),finished:str=Form(''),minutes_read:str=Form(''),pages_read:str=Form(''),note:str=Form('')):
        guard(csrf)
        try: minutes=int(minutes_read) if minutes_read else None;pages=int(pages_read) if pages_read else None
        except ValueError:raise HTTPException(422,'Invalid session value')
        if any(v is not None and v<0 for v in (minutes,pages)):raise HTTPException(422)
        with db() as c:
            c.execute('INSERT INTO reading_sessions(book_id,started,finished,minutes_read,pages_read,note) VALUES(?,?,?,?,?,?)',(book_id,safe_date(started),safe_date(finished),minutes,pages,note))
            # Reading total is derived from sessions only when no manual total exists.
            c.execute('UPDATE reading SET minutes_read=COALESCE(minutes_read,0)+?,updated_at=? WHERE book_id=?',(minutes or 0,now(),book_id));c.commit()
        return go(f'/book/{book_id}')
    @app.post('/book/{book_id}/category')
    def category(book_id:int,csrf:str=Form(...),category:str=Form(...)):
        guard(csrf);category=category.strip()
        if not category or len(category)>80:raise HTTPException(422)
        with db() as c:
            c.execute('INSERT OR IGNORE INTO categories(name) VALUES(?)',(category,))
            id=c.execute('SELECT id FROM categories WHERE name=? COLLATE NOCASE',(category,)).fetchone()[0]
            c.execute('INSERT INTO book_categories VALUES(?,?,1,?,1) ON CONFLICT(book_id,category_id) DO UPDATE SET confidence=1,source=excluded.source,confirmed=1',(book_id,id,'manual'));c.commit()
        return go(f'/book/{book_id}')
    @app.get('/review',response_class=HTMLResponse)
    def review():
        with db() as c: rows=c.execute('SELECT q.*,b.title FROM review_queue q JOIN books b ON q.book_id=b.id WHERE q.resolved=0 ORDER BY q.confidence,q.book_id LIMIT 250').fetchall()
        blocks=''.join(f'<div class="panel"><a href="/book/{x["book_id"]}">{h(x["title"])}</a><p><b>{h(x["field"])}</b>: {h(json.loads(x["suggested"]))} <span class="badge">{round(x["confidence"]*100)}% confidence</span></p><p class="muted">{h(x["reason"])}</p><form method="post" action="/review/{x["id"]}">{token()}<label>Correct value (JSON for authors; number for series index)<input name="value" value="{h(json.loads(x["suggested"])) if x["field"]!="authors" else h(x["suggested"])}"></label><button name="action" value="confirm">Confirm / correct</button> <button class="ghost" name="action" value="dismiss">Dismiss</button></form></div>' for x in rows)
        return layout('Review',f'<h1>Metadata review queue</h1><p>{len(rows)} unresolved suggestions shown. Manual corrections are protected from future scans.</p>{blocks or "<p>No pending items.</p>"}')
    @app.post('/review/{review_id}')
    def resolve(review_id:int,csrf:str=Form(...),value:str=Form(''),action:str=Form(...)):
        guard(csrf)
        if action not in ('confirm','dismiss'):raise HTTPException(422)
        with db() as c:
            q=c.execute('SELECT * FROM review_queue WHERE id=? AND resolved=0',(review_id,)).fetchone()
            if not q:raise HTTPException(404)
            if action=='confirm':
                field=q['field'];value=value.strip()
                if field=='authors':
                    try:parsed=json.loads(value)
                    except ValueError:raise HTTPException(422,'Authors must be JSON list')
                    if not isinstance(parsed,list) or not all(isinstance(a,str) for a in parsed):raise HTTPException(422)
                    value=json.dumps(parsed)
                if field=='series_index':
                    try:value=float(value)
                    except ValueError:raise HTTPException(422)
                if field=='title' and not value:raise HTTPException(422)
                if field not in ('title','authors','series','series_index'):raise HTTPException(422)
                c.execute(f'UPDATE books SET {field}=?,manually_verified=1,updated_at=? WHERE id=?',(value,now(),q['book_id']))
            c.execute('UPDATE review_queue SET resolved=1 WHERE id=?',(review_id,))
            remaining=c.execute('SELECT 1 FROM review_queue WHERE book_id=? AND resolved=0',(q['book_id'],)).fetchone()
            c.execute('UPDATE books SET needs_review=? WHERE id=?',(int(bool(remaining)),q['book_id']));c.commit()
        return go('/review')
    @app.get('/reading',response_class=HTMLResponse)
    def reading(scope:str='all',category:str='',series:str='',include_answered:int=0):
        with db() as c:
            categories=[x[0] for x in c.execute('SELECT name FROM categories ORDER BY name')]; series_names=[x[0] for x in c.execute('SELECT DISTINCT series FROM books WHERE series IS NOT NULL ORDER BY series')]
            conditions=['1=1'];args=[]
            if not include_answered:conditions.append("r.status='unanswered'")
            if scope=='category' and category:
                conditions.append('EXISTS(SELECT 1 FROM book_categories bc JOIN categories cat ON cat.id=bc.category_id WHERE bc.book_id=b.id AND cat.name=?)');args.append(category)
            if scope=='series' and series:conditions.append('b.series=?');args.append(series)
            rows=c.execute(f'SELECT b.id,b.title,b.series,r.status FROM books b JOIN reading r ON b.id=r.book_id WHERE {" AND ".join(conditions)} ORDER BY b.series,b.series_index,b.title LIMIT 200',args).fetchall()
        opts=lambda data,current:''.join(f'<option value="{h(x)}" {"selected" if x==current else ""}>{h(x)}</option>' for x in data)
        controls=f'<form method="get" class="panel toolbar"><select name="scope">{opts(["all","category","series"],scope)}</select><select name="category"><option value="">Choose category</option>{opts(categories,category)}</select><select name="series"><option value="">Choose series</option>{opts(series_names,series)}</select><label><input type="checkbox" name="include_answered" value="1" {"checked" if include_answered else ""}> Show answered</label><button>Apply</button></form>'
        cards=''.join(f'<div class="panel"><a href="/book/{x["id"]}"><b>{h(x["title"])}</b></a><p class="muted">{h(x["series"])} · {h(LABELS.get(x["status"],""))}</p><form method="post" action="/reading/quick/{x["id"]}">{token()}<select name="status">{"".join(f"<option value={s}>{LABELS[s]}</option>" for s in STATES if s!="unanswered")}</select><button>Save & next</button></form></div>' for x in rows)
        return layout('Reading review',f'<h1>Have you read it?</h1><p>Choose all titles, a series, or a category. Detailed dates, time and notes are editable on each book page.</p>{controls}{cards or "<p>Nothing left in this selection.</p>"}')
    @app.post('/reading/quick/{book_id}')
    def quick(book_id:int,csrf:str=Form(...),status:str=Form(...)):
        guard(csrf)
        if status not in STATES:raise HTTPException(422)
        with db() as c:
            c.execute('UPDATE reading SET status=?,updated_at=? WHERE book_id=?',(status,now(),book_id));c.commit()
        return go('/reading')
    @app.get('/series',response_class=HTMLResponse)
    def series_index():
        with db() as c:
            rows=c.execute("""SELECT s.*,COUNT(b.id) AS total, SUM(CASE WHEN r.status='finished' THEN 1 ELSE 0 END) AS completed FROM series_catalog s LEFT JOIN books b ON b.series=s.name COLLATE NOCASE LEFT JOIN reading r ON r.book_id=b.id GROUP BY s.id ORDER BY s.name""").fetchall()
        items=''.join(f'<section class="panel"><h2>{h(x["name"])}</h2><p>{x["total"]} books · {x["completed"] or 0} finished</p><p>{h(x["description"] or "")}</p><p class="muted">{h(x["notes"] or "")}</p><form method="post" action="/series/{x["id"]}">{token()}<label>Name<input name="name" value="{h(x["name"])}" required maxlength="250"></label><label>Description<textarea name="description">{h(x["description"] or "")}</textarea></label><label>Personal notes<textarea name="notes">{h(x["notes"] or "")}</textarea></label><button>Save series</button></form></section>' for x in rows)
        return layout('Series',f'<h1>Series catalog</h1><p>Renaming a series updates its member books without touching your files.</p>{items or "<p>No series found.</p>"}')
    @app.post('/series/{series_id}')
    def update_series(series_id:int,csrf:str=Form(...),name:str=Form(...),description:str=Form(''),notes:str=Form('')):
        guard(csrf);name=name.strip()
        if not name or len(name)>250:raise HTTPException(422)
        with db() as c:
            old=c.execute('SELECT * FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not old:raise HTTPException(404)
            collision=c.execute('SELECT id FROM series_catalog WHERE name=? COLLATE NOCASE AND id<>?',(name,series_id)).fetchone()
            if collision:raise HTTPException(409,'Another series already uses this name')
            c.execute('UPDATE books SET series=?,updated_at=? WHERE series=? COLLATE NOCASE',(name,now(),old['name']))
            c.execute('UPDATE series_catalog SET name=?,description=?,notes=?,updated_at=? WHERE id=?',(name,description,notes,now(),series_id));c.commit()
        return go('/series')
    @app.get('/duplicates',response_class=HTMLResponse)
    def duplicates():
        with db() as c:
            rows=c.execute("""SELECT l.*,a.title AS a_title,b.title AS b_title,a.authors AS a_authors FROM book_links l JOIN books a ON a.id=l.book_id JOIN books b ON b.id=l.candidate_id WHERE l.resolved=0 ORDER BY l.confidence DESC LIMIT 250""").fetchall()
            exact=c.execute("""SELECT content_sha256,COUNT(*) AS copies FROM files WHERE content_sha256 IS NOT NULL GROUP BY content_sha256 HAVING COUNT(*)>1""").fetchall()
        panels=''.join(f'<div class="panel"><b><a href="/book/{x["book_id"]}">{h(x["a_title"])}</a></b> and <b><a href="/book/{x["candidate_id"]}">{h(x["b_title"])}</a></b><p class="muted">Possible alternate editions · similarity {round(x["confidence"]*100)}% · {h(", ".join(jsonarr(x["a_authors"])))}</p><form method="post" action="/duplicates/{x["id"]}">{token()}<button name="action" value="distinct" class="ghost">Keep as distinct editions</button><button name="action" value="related">Mark as related editions</button></form></div>' for x in rows)
        return layout('Possible editions',f'<h1>Possible alternate editions</h1><p>{len(exact)} content hashes have multiple file references. Matching titles are never silently merged. Resolving a suggestion only labels the relationship; it does not merge book records or files.</p>{panels or "<p>No pending edition matches.</p>"}')
    @app.post('/duplicates/{link_id}')
    def resolve_duplicate(link_id:int,csrf:str=Form(...),action:str=Form(...)):
        guard(csrf)
        if action not in ('distinct','related'):raise HTTPException(422)
        with db() as c:
            result=c.execute('UPDATE book_links SET resolved=? WHERE id=? AND resolved=0',(1 if action=='related' else 2,link_id))
            if not result.rowcount:raise HTTPException(404)
            c.commit()
        return go('/duplicates')
    @app.get('/stats',response_class=HTMLResponse)
    def stats():
        with db() as c:
            totals=c.execute('SELECT COUNT(*) AS books,COALESCE(SUM(page_count),0) AS pages FROM books').fetchone();statuses=c.execute('SELECT r.status,COUNT(*) AS total FROM reading r GROUP BY r.status').fetchall();formats=c.execute('SELECT extension,COUNT(*) AS n FROM files GROUP BY extension ORDER BY n DESC').fetchall();minutes=c.execute('SELECT COALESCE(SUM(minutes_read),0) FROM reading').fetchone()[0]
        return layout('Stats',f'<h1>Library statistics</h1><div class="panel"><h2>{totals["books"]} books · {totals["pages"]:,} reported pages · {minutes:,} reading minutes</h2><h3>Reading states</h3>{"".join(f"<p>{h(LABELS.get(x[0],x[0]))}: {x[1]}</p>" for x in statuses)}<h3>Files</h3>{"".join(f"<p>{h(x[0])}: {x[1]}</p>" for x in formats)}</div>')
    return app
