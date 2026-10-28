from __future__ import annotations
import html, json, os, secrets, sqlite3, threading, time
from pathlib import Path
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse, Response, StreamingResponse
from .core import connect, jsonarr, now, scan, enrich_existing, cache_cover
from .custom_export import FIELDS,TEMPLATES,export_custom
from .export import export_csv,export_json

STATES=['unanswered','not_read','want_to_read','reading','finished','abandoned','on_hold','rereading']
LABELS={'unanswered':'Not answered','not_read':'Not read','want_to_read':'Want to read','reading':'Currently reading','finished':'Finished','abandoned':'Started & abandoned','on_hold':'On hold','rereading':'Rereading'}
GLOBAL_CSRF=secrets.token_urlsafe(32)
CSS=Path(__file__).with_name('ui.css').read_text(encoding='utf-8')
def h(s):return html.escape(str(s if s is not None else ''),quote=True)
def layout(title,body):
    links=[('/', 'library'),('/scan','scan'),('/review','review'),('/reading','reading'),('/quick-sort','quick sort'),('/series','series'),('/duplicates','editions'),('/stats','statistics'),('/enrich','enrich'),('/exports','exports')]
    nav=''.join(f'<a href="{url}">{label}</a>' for url,label in links)
    return HTMLResponse(f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#0E0E11"><meta name="bookledger-csrf" content="{h(GLOBAL_CSRF)}"><link rel="icon" type="image/svg+xml" href="/favicon.svg"><title>{h(title).lower()} · bookledger</title><style>{CSS}</style></head><body><a class="skip-link" href="#main-content">skip to content</a><header><a href="/"><strong>bookledger</strong></a><nav>{nav}</nav></header><main id="main-content">{body}</main><script src="/series-menu.js" defer></script><script src="/context-menu.js" defer></script><script src="/bulk.js" defer></script></body></html>''')
def bulk_toolbar(kind):
    if kind=='series':
        choices='<option value="delete">delete selected series (books stay)</option>'
    else:
        choices=''.join(f'<option value="{x}">{h(LABELS[x])}</option>' for x in ('finished','reading','not_read','want_to_read','on_hold','abandoned','rereading'))
        choices+='<option value="hide">hide selected</option><option value="unhide">unhide selected</option><option value="unassign_series">remove from series</option>'
    return f'<form class="bulk-toolbar" hidden data-bulk-toolbar="{kind}" method="post" action="/bulk/{"series" if kind=="series" else "books"}"><input type="hidden" name="csrf" value="{h(GLOBAL_CSRF)}"><label class="bulk-select-all"><input type="checkbox" data-bulk-all> select all shown</label><output aria-live="polite" class="bulk-count">0 selected</output><label class="bulk-action-label">bulk action <select name="action" required><option value="">choose action…</option>{choices}</select></label><button type="submit" disabled>apply to selection</button><button type="button" class="ghost" data-bulk-clear>done</button><span data-bulk-inputs></span></form>'

def safe_date(v):
    if not v: return None
    from datetime import date
    try: return date.fromisoformat(v).isoformat()
    except ValueError: raise HTTPException(422,'Invalid date')
def create_app(db_path):
    app=FastAPI(title='BookLedger',docs_url=None,redoc_url=None)
    app.state.db_path=str(Path(db_path).expanduser());app.state.csrf=GLOBAL_CSRF
    def db():return connect(app.state.db_path)
    @app.get('/series-menu.js')
    def series_menu_script():
        return Response(r"""(()=>{'use strict';const menu=document.createElement('div');menu.className='series-context-menu';menu.setAttribute('role','menu');menu.hidden=true;document.body.append(menu);let target=null,timer=null,suppressClick=false;const csrf=document.querySelector('input[name=csrf]')?.value;function close(){menu.hidden=true;target=null}function command(label,cb,danger=false){const b=document.createElement('button');b.type='button';b.setAttribute('role','menuitem');b.textContent=label;if(danger)b.className='menu-danger';b.onclick=()=>{const t=target;close();cb(t)};menu.append(b)}function post(url,data,confirmText){if(confirmText&&!confirm(confirmText))return;const form=document.createElement('form');form.method='POST';form.action=url;for(const [key,value] of Object.entries({...data,csrf})){const i=document.createElement('input');i.type='hidden';i.name=key;i.value=value;form.append(i)}document.body.append(form);form.submit()}function show(el,x,y){target=el;menu.replaceChildren();const type=el.dataset.menu, sid=el.dataset.seriesId,bid=el.dataset.bookId;if(type==='series'){command('select series',()=>window.BookLedgerBulk?.start(el));command('open series',()=>location.assign('/series/'+sid));command('edit series',()=>location.assign('/series/'+sid+'#series-settings'));command('copy series link',()=>navigator.clipboard?.writeText(location.origin+'/series/'+sid));command('delete series',()=>post('/series/'+sid+'/delete',{},'Delete this series? All books will remain in your library.'),true)}else if(type==='book'){command('select book',()=>window.BookLedgerBulk?.start(el));command('open book',()=>location.assign('/book/'+bid));command('copy book link',()=>navigator.clipboard?.writeText(location.origin+'/book/'+bid));command('remove from series',()=>post('/series/'+sid+'/member/'+bid,{action:'remove',index:''},'Remove this book from the series?'),true)}else{command('select book',()=>window.BookLedgerBulk?.start(el));command('open book',()=>location.assign('/book/'+bid));command('add to series',()=>post('/series/'+sid+'/member/'+bid,{action:'add',index:''}))}menu.hidden=false;suppressClick=true;setTimeout(()=>{suppressClick=false},900);menu.style.left=Math.min(x,innerWidth-menu.offsetWidth-12)+'px';menu.style.top=Math.min(y,innerHeight-menu.offsetHeight-12)+'px';menu.querySelector('button')?.focus()}document.addEventListener('contextmenu',e=>{const el=e.target.closest('[data-menu]');if(!el)return;e.preventDefault();show(el,e.clientX,e.clientY)});document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))close();if(e.pointerType==='touch'){const el=e.target.closest('[data-menu]');if(el){clearTimeout(timer);const x=e.clientX,y=e.clientY;timer=setTimeout(()=>show(el,x,y),550)}}});document.addEventListener('pointerup',()=>clearTimeout(timer));document.addEventListener('pointercancel',()=>clearTimeout(timer));document.addEventListener('pointermove',e=>{if(e.pointerType==='touch')clearTimeout(timer)});document.addEventListener('keydown',e=>{if(e.key==='Escape')close();if((e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))&&e.target.closest('[data-menu]')){e.preventDefault();const el=e.target.closest('[data-menu]'),r=el.getBoundingClientRect();show(el,r.left+20,r.top+20)}});document.addEventListener('click',e=>{if(suppressClick&&e.target.closest('[data-menu]')){e.preventDefault();e.stopPropagation();suppressClick=false;return}if(!menu.contains(e.target))close()},true);})();""",media_type='text/javascript')
    @app.get('/context-menu.js')
    def general_context_menu_script():
        return FileResponse(Path(__file__).with_name('context-menu.js'),media_type='text/javascript',headers={'Cache-Control':'no-cache'})
    @app.get('/bulk.js')
    def bulk_script():
        return FileResponse(Path(__file__).with_name('bulk.js'),media_type='text/javascript')
    @app.get('/favicon.svg')
    def favicon(): return FileResponse(Path(__file__).with_name('favicon.svg'),media_type='image/svg+xml')
    @app.get('/cover/{book_id}')
    def cover(book_id:int):
        with db() as c:
            b=c.execute('SELECT cover_path FROM books WHERE id=?',(book_id,)).fetchone()
        if not b or not b['cover_path']:raise HTTPException(404)
        path=Path(b['cover_path'])
        expected=Path(app.state.db_path).resolve().parent/'covers'
        if not path.resolve().is_relative_to(expected.resolve()) or not path.is_file():raise HTTPException(404)
        return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, max-age=3600'})

    def token():return f'<input type="hidden" name="csrf" value="{h(app.state.csrf)}">'
    def guard(csrf):
        if not secrets.compare_digest(csrf,app.state.csrf):raise HTTPException(403,'Invalid form token')
    def go(url):return RedirectResponse(url,status_code=303)
    app.state.scan_lock=threading.Lock()
    app.state.scan_job=None
    def public_job():
        with app.state.scan_lock:
            job=app.state.scan_job
            if job is None: return {'status':'idle'}
            return {k:v for k,v in job.items() if k!='thread'}
    @app.get('/scan',response_class=HTMLResponse)
    def scan_page():
        job=public_job()
        return layout('Scan folders','''<h1>scan folders</h1><p>Index metadata from a folder on the machine running BookLedger. Files are never moved or modified.</p>
        <section class="panel"><form action="/scan" method="post">__CSRF_TOKEN__
        <label>Absolute folder path on server<input name="folder" placeholder="D:/eBooks or /home/user/Books" required></label>
        <label><input type="checkbox" name="online" value="yes" checked style="width:auto"> Online catalog enrichment</label>
        <button>Start scan</button></form><p class="muted">Only one scan can run at a time. Phone browsers can start a scan of folders accessible to the PC, not folders stored solely on the phone.</p></section>
        <section class="panel"><h2>scan status</h2><div id="job">Loading...</div></section>
        <script>
        const target=document.getElementById('job');
        const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        async function refresh(){try{const r=await fetch('/scan/status',{cache:'no-store'});if(!r.ok)throw Error('Status request failed');const j=await r.json();
        if(j.status==='idle'){target.textContent='No scan started yet.';return}
        const counts=j.counts||{};const lines=(j.events||[]).map(e=>esc(e)).join('\\n');
        target.innerHTML='<p><strong>'+esc(j.status)+'</strong> · '+esc(j.folder)+'</p><p>'+esc(j.processed||0)+' files encountered · '+esc(counts.new||0)+' new · '+esc(counts.updated||0)+' updated · '+esc(counts.unchanged||0)+' unchanged · '+esc(counts.errors||0)+' errors</p><p>Current: '+esc(j.current||'—')+'</p><p>Stage: '+esc(j.stage||'—')+'</p>'+(j.error?'<p>'+esc(j.error)+'</p>':'')+'<pre id="scan-log" role="log" aria-label="scan event log" style="max-height:350px;overflow:auto">'+lines+'</pre>';const log=document.getElementById('scan-log');if(log)log.scrollTop=log.scrollHeight;
        }catch(e){target.textContent=e.message}}
        refresh();setInterval(refresh,1500);
        </script>'''.replace('__CSRF_TOKEN__',token()))
    @app.get('/scan/status')
    def scan_status():
        return JSONResponse(public_job(),headers={'Cache-Control':'no-store'})
    @app.post('/scan')
    def begin_scan(folder:str=Form(...),csrf:str=Form(...),online:str=Form('')):
        guard(csrf)
        path=Path(folder).expanduser().resolve()
        if not path.is_dir(): raise HTTPException(422,'Folder does not exist or is not accessible to the server')
        with app.state.scan_lock:
            if app.state.scan_job and app.state.scan_job['status']=='running':
                raise HTTPException(409,'A scan is already running')
            job={'status':'running','folder':str(path),'processed':0,'current':'','stage':'discovering',
                 'counts':{'new':0,'updated':0,'unchanged':0,'errors':0},'events':[],'error':None}
            app.state.scan_job=job
        def progress(evt):
            with app.state.scan_lock:
                job['processed']=evt.get('processed',job['processed'])
                job['counts']={k:evt.get(k,job['counts'].get(k,0)) for k in job['counts']}
                if evt.get('path'):job['current']=evt['path']
                job['stage']=evt.get('stage',evt['event'])
                if evt['event'] in ('file_start','file_done','error','complete'):
                    description={'file_start':'reading','file_done':evt.get('outcome','done'),'error':'ERROR','complete':'COMPLETE'}[evt['event']]
                    detail=evt.get('message') or evt.get('warning') or ''
                    job['events'].append(f'{description}: {evt.get("path","")} {detail}'.strip())
                    job['events']=job['events'][-120:]
        def worker():
            try:
                with db() as connection:
                    scan(connection,path,online=(online=='yes'),progress=progress)
                with app.state.scan_lock:job['status']='completed';job['stage']='finished'
            except Exception as exc:
                with app.state.scan_lock:
                    job['status']='failed';job['error']=f'{type(exc).__name__}: {exc}';job['stage']='failed'
        threading.Thread(target=worker,daemon=True,name='bookledger-scan').start()
        return go('/scan')

    app.state.enrich_job={'status':'idle','processed':0,'total':0,'title':'','result':{},'last_id':0}
    app.state.enrich_lock=threading.Lock()
    app.state.enrich_cancel=threading.Event()
    @app.get('/enrich')
    def enrich_page():
        with app.state.enrich_lock: state=dict(app.state.enrich_job)
        next_id=state.get('last_id',0)
        return layout('enrichment',f'''<div class="section-head">catalog / external metadata</div><h1>enrichment.</h1><p class="hero-sub">Run controlled batches. Keep manual edits and reading data intact. Open Library may be slow or incomplete.</p><div class="enrich-columns"><section class="panel"><h2>new pass</h2><form method="post" action="/enrich">{token()}<label>mode<select name="mode"><option value="missing">fill incomplete metadata</option><option value="covers">fetch missing covers</option><option value="all">check every record (fill blanks only)</option></select></label><label>maximum books per pass<input type="number" name="limit" value="100" min="1" max="10000" required></label><label>start after book ID<input type="number" name="start_after" value="{int(next_id)}" min="0"></label><button>start batch</button></form><form method="post" action="/enrich/cancel">{token()}<button class="ghost">stop after current book</button></form><p class="muted">To restart at the beginning, set the starting ID to 0. Repeated passes never overwrite existing non-empty fields.</p></section><section class="panel"><h2>live results</h2><div id="enrich-status" role="status" aria-live="polite">loading…</div><progress id="enrich-progress" value="0" max="100" style="width:100%"></progress><h3>recent failures</h3><ul id="enrich-errors" class="enrich-errors"></ul></section></div><script>
async function poll(){{try{{const r=await fetch('/enrich/status',{{cache:'no-store'}});if(!r.ok)return;const j=await r.json();const result=j.result||{{}};document.getElementById('enrich-status').textContent=`${{j.status}} · ${{j.processed||0}} / ${{j.total||0}} · book #${{j.last_id||0}} · ${{j.title||''}} · updated ${{result.enriched||0}} · covers ${{result.covers||0}} · errors ${{result.errors||0}}`;const p=document.getElementById('enrich-progress');p.max=Math.max(1,j.total||1);p.value=j.processed||0;document.getElementById('enrich-errors').replaceChildren(...(result.failures||[]).slice(-12).map(x=>{{const li=document.createElement('li');li.textContent='#'+x.id+' '+x.title+': '+x.error;return li}}))}}catch(e){{}}}}poll();setInterval(poll,1600);
</script>''')
    @app.get('/enrich/status')
    def enrichment_status():
        with app.state.enrich_lock:return dict(app.state.enrich_job)
    @app.post('/enrich/cancel')
    def stop_enrich(csrf:str=Form(...)):
        guard(csrf);app.state.enrich_cancel.set();return go('/enrich')
    @app.post('/enrich')
    def start_enrich(csrf:str=Form(...),mode:str=Form('missing'),limit:int=Form(100),start_after:int=Form(0)):
        guard(csrf)
        if mode not in ('missing','covers','all') or not 1<=limit<=10000 or start_after<0:raise HTTPException(422,'Invalid batch settings')
        with app.state.enrich_lock:
            if app.state.enrich_job['status']=='running':raise HTTPException(409,'Enrichment already running')
            with db() as c: count=c.execute('SELECT COUNT(*) FROM (SELECT id FROM books WHERE id>? ORDER BY id LIMIT ?)',(start_after,limit)).fetchone()[0]
            app.state.enrich_job={'status':'running','processed':0,'total':count,'title':'','result':{},'last_id':start_after}
            app.state.enrich_cancel.clear()
        def update(event):
            with app.state.enrich_lock:app.state.enrich_job.update(event)
        def worker():
            try:
                with db() as c:result=enrich_existing(c,update,start_after=start_after,limit=limit,mode=mode,stop=app.state.enrich_cancel.is_set)
                with app.state.enrich_lock:app.state.enrich_job.update(status='cancelled' if result['cancelled'] else 'completed',result=result,last_id=result['last_id'])
            except Exception as exc:
                with app.state.enrich_lock:app.state.enrich_job.update(status='failed',result={'error':f'{type(exc).__name__}: {exc}'})
        threading.Thread(target=worker,daemon=True,name='bookledger-enrichment').start();return go('/enrich')

    @app.get('/exports')
    def exports_page(template:str='full'):
        selected=TEMPLATES.get(template,TEMPLATES['full'])
        with db() as c:
            cats=[r[0] for r in c.execute('SELECT name FROM categories ORDER BY name')]
            series=[r[0] for r in c.execute('SELECT DISTINCT series FROM books WHERE series IS NOT NULL ORDER BY series')]
        options=''.join(f'<option value="{h(n)}" {"selected" if template==n else ""}>{h(n.replace("-"," "))}</option>' for n in TEMPLATES)
        checks=''.join(f'<label style="display:flex;gap:8px;align-items:center;margin:0;padding:8px 0"><input type="checkbox" name="fields" value="{h(field)}" {"checked" if field in selected else ""}>{h(field.replace("_"," "))}</label>' for field in FIELDS)
        statuses=''.join(f'<option value="{h(k)}">{h(v)}</option>' for k,v in LABELS.items())
        cat_options=''.join(f'<option value="{h(v)}">{h(v)}</option>' for v in cats)
        series_options=''.join(f'<option value="{h(v)}">{h(v)}</option>' for v in series)
        return layout('exports',f'''<div class="section-head">your data / portability</div><h1>export your library.</h1><p class="hero-sub">Build a spreadsheet with only the fields and books you want. All exports are generated locally.</p><div class="split"><section class="panel"><h2>custom csv</h2><label>starting template</label><select onchange="window.location.href='/exports?template='+encodeURIComponent(this.value)">{options}</select><form method="post" action="/exports/download">{token()}<div class="toolbar"><label>reading status<select name="status"><option value="">all statuses</option>{statuses}</select></label><label>category<select name="category"><option value="">all categories</option>{cat_options}</select></label><label>series<select name="series"><option value="">all series</option>{series_options}</select></label></div><label>search titles or authors<input name="search" placeholder="optional"></label><h3>columns</h3><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:0 16px">{checks}</div><button>download custom csv</button></form></section><section class="panel"><h2>service templates</h2><p>Goodreads-shaped exports are accepted by StoryGraph. CSV formats for other apps can change, so the reference templates are editable rather than claiming guaranteed compatibility.</p><a class="button" href="/exports/preset/goodreads">goodreads csv</a><p style="margin-top:22px"><a class="button" href="/exports/preset/storygraph">storygraph csv</a></p><p style="margin-top:22px"><a class="button" href="/exports/preset/json">full json backup</a></p><p class="muted" style="margin-top:28px">Bookmory and Hardcover have editable reference column presets. Check the current import mapping in each app before uploading.</p></section></div>''')
    @app.post('/exports/download')
    def custom_download(csrf:str=Form(...),fields:list[str]=Form(...),status:str=Form(''),category:str=Form(''),series:str=Form(''),search:str=Form('')):
        guard(csrf)
        if len(fields)>len(FIELDS):raise HTTPException(422)
        with db() as c: data=export_custom(c,fields,status,category,series,search)
        return Response(data,media_type='text/csv; charset=utf-8',headers={'Content-Disposition':'attachment; filename="bookledger-custom.csv"'})
    @app.get('/exports/preset/{kind}')
    def preset(kind:str):
        if kind not in ('goodreads','storygraph','json'):raise HTTPException(404)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/('library.json' if kind=='json' else 'library.csv')
            with db() as c:
                if kind=='json':export_json(c,output)
                else:export_csv(c,output)
            data=output.read_bytes()
        return Response(data,media_type='application/json' if kind=='json' else 'text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="bookledger-{kind}.{ "json" if kind=="json" else "csv"}"'})

    @app.get('/',response_class=HTMLResponse)
    def index(q:str='',status:str='',category:str='',series:str='',sort:str='title',visibility:str='visible'):
        with db() as c:
            where=['1=1'];args=[]
            if visibility=='hidden':where.append('b.hidden=1')
            elif visibility!='all':where.append('b.hidden=0')
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
        filters=f'<form method="get" class="panel toolbar"><input name="q" placeholder="Title, author or series" value="{h(q)}"><select name="status">{options([("","Any reading status")]+[(x,LABELS[x]) for x in STATES],status)}</select><select name="category">{options([("","Any category")]+[(x,x) for x in categories],category)}</select><select name="series">{options([("","Any series")]+[(x,x) for x in series_names],series)}</select><select name="visibility" aria-label="Book visibility">{options([("visible","Visible books"),("hidden","Hidden books only"),("all","All books")],visibility)}</select><select name="sort">{options([("title","Title"),("author","Author"),("date","Recently indexed"),("series","Series order")],sort)}</select><button>Filter</button></form>'
        cards=''.join(f'<article class="panel book-card bulk-item" data-bulk-kind="book"><label class="bulk-check" aria-label="select book {h(b["title"])}"><input type="checkbox" class="bulk-select" value="{b["id"]}"><span>select</span></label><a href="/book/{b["id"]}">'+(f'<img class="book-cover" loading="lazy" src="/cover/{b["id"]}" alt="cover of {h(b["title"])}">' if b['cover_path'] else f'<div class="book-cover-placeholder">{h(b["title"])}</div>')+f'</a><div class="book-info"><a href="/book/{b["id"]}"><strong>{h(b["title"])}</strong></a><p>{h(", ".join(jsonarr(b["authors"])))}</p><p>{h(b["series"] or "")}{" · #"+h(b["series_index"]) if b["series_index"] is not None else ""}</p><span class="tag">{h(LABELS.get(b["status"],"Not answered"))}</span>{"<span class=badge>review</span>" if b["needs_review"] else ""}</div></article>' for b in rows)
        return layout('Library',f'<div class=section-head>your catalog / overview</div><h1>your library<span style="color:var(--primary)">.</span></h1><div class=stat-strip><div class=stat-chip><b>{count:,}</b> titles</div><div class=stat-chip><b>{pending:,}</b> suggestions</div><div class=stat-chip><b>{len(rows):,}</b> shown</div></div>{filters}{bulk_toolbar('book')}<section class="grid bulk-scope">{cards or "<p>No books found. Run bookledger scan first.</p>"}</section>')
    @app.post('/bulk/books')
    async def bulk_books(request:Request):
        form=await request.form();guard(str(form.get('csrf','')))
        action=str(form.get('action',''))
        ids=list(dict.fromkeys(int(v) for v in form.getlist('ids') if str(v).isdigit() and int(v)>0))
        if not ids or len(ids)>1000:raise HTTPException(422,'Select 1–1000 books')
        if action not in ('finished','reading','not_read','want_to_read','on_hold','abandoned','rereading','hide','unhide','unassign_series'):
            raise HTTPException(422,'Invalid bulk action')
        placeholders=','.join('?' for _ in ids)
        with db() as c:
            found=c.execute(f'SELECT id FROM books WHERE id IN ({placeholders})',ids).fetchall()
            if len(found)!=len(ids):raise HTTPException(422,'Some selected books no longer exist')
            if action in STATES:
                c.execute(f'UPDATE reading SET status=?,updated_at=? WHERE book_id IN ({placeholders})',(action,now(),*ids))
                c.execute(f'INSERT INTO reading(book_id,status,updated_at) SELECT id,?,? FROM books WHERE id IN ({placeholders}) AND id NOT IN (SELECT book_id FROM reading)',(action,now(),*ids))
            elif action in ('hide','unhide'):
                c.execute(f'UPDATE books SET hidden=?,updated_at=? WHERE id IN ({placeholders})',(int(action=='hide'),now(),*ids))
            else:
                c.execute(f'UPDATE books SET series=NULL,series_index=NULL,manually_verified=1,updated_at=? WHERE id IN ({placeholders})',(now(),*ids))
            c.commit()
        referer=request.headers.get('referer','')
        from urllib.parse import urlparse
        parsed=urlparse(referer)
        destination=parsed.path + ('?'+parsed.query if parsed.query else '') if parsed.path.startswith('/') and not parsed.path.startswith('//') else '/'
        return go(destination)

    @app.post('/bulk/series')
    async def bulk_series(request:Request):
        form=await request.form();guard(str(form.get('csrf','')))
        action=str(form.get('action',''))
        if action!='delete':raise HTTPException(422,'Invalid series action')
        ids=list(dict.fromkeys(int(v) for v in form.getlist('ids') if str(v).isdigit() and int(v)>0))
        if not ids or len(ids)>500:raise HTTPException(422,'Select 1–500 series')
        with db() as c:
            names=c.execute(f'SELECT name FROM series_catalog WHERE id IN ({",".join("?" for _ in ids)})',ids).fetchall()
            if len(names)!=len(ids):raise HTTPException(422,'Some series no longer exist')
            for row in names:
                c.execute('UPDATE books SET series=NULL,series_index=NULL,manually_verified=1,updated_at=? WHERE series=? COLLATE NOCASE',(now(),row['name']))
            c.execute(f'DELETE FROM series_catalog WHERE id IN ({",".join("?" for _ in ids)})',ids)
            c.commit()
        return go('/series')

    @app.post('/book/{book_id}/visibility')
    def set_visibility(book_id:int,csrf:str=Form(...),hidden:str=Form(...)):
        guard(csrf)
        if hidden not in ('0','1'):raise HTTPException(422,'Invalid visibility')
        with db() as c:
            changed=c.execute('UPDATE books SET hidden=?,updated_at=? WHERE id=?',(int(hidden),now(),book_id))
            if not changed.rowcount:raise HTTPException(404)
            c.commit()
        return go(f'/book/{book_id}')

    @app.get('/book/{book_id}',response_class=HTMLResponse)
    def book(book_id:int):
        with db() as c:
            b=c.execute('SELECT * FROM books WHERE id=?',(book_id,)).fetchone()
            if not b:raise HTTPException(404)
            series_names=[x[0] for x in c.execute('SELECT name FROM series_catalog ORDER BY name')]
            r=c.execute('SELECT * FROM reading WHERE book_id=?',(book_id,)).fetchone()
            files=c.execute('SELECT * FROM files WHERE book_id=?',(book_id,)).fetchall()
            cats=c.execute('SELECT c.name,bc.confidence,bc.confirmed FROM book_categories bc JOIN categories c ON c.id=bc.category_id WHERE bc.book_id=?',(book_id,)).fetchall()
            sessions=c.execute('SELECT * FROM reading_sessions WHERE book_id=? ORDER BY id DESC',(book_id,)).fetchall()
            relations=c.execute('''SELECT l.id,l.kind,l.confidence,l.resolved,other.id AS other_id,other.title AS other_title FROM book_links l JOIN books other ON other.id=CASE WHEN l.book_id=? THEN l.candidate_id ELSE l.book_id END WHERE l.book_id=? OR l.candidate_id=?''',(book_id,book_id,book_id)).fetchall()
            folders=c.execute('''SELECT DISTINCT fc.folder_path,fc.category,fc.confidence FROM folder_categories fc JOIN files f ON f.id=fc.file_id WHERE f.book_id=? ORDER BY fc.folder_path''',(book_id,)).fetchall()
            series_members=c.execute('SELECT id,title,series_index FROM books WHERE series=? AND id<>? ORDER BY series_index,title LIMIT 150',(b['series'],book_id)).fetchall() if b['series'] else []
            pending=c.execute('SELECT id,field,suggested,confidence,reason FROM review_queue WHERE book_id=? AND resolved=0',(book_id,)).fetchall()
        fields=''.join(f'<p><b>{h(key.replace("_"," ").title())}:</b> {h(", ".join(jsonarr(b[key])) if key in ("authors","subjects") else b[key])}</p>' for key in ('isbn13','isbn10','language','publisher','published','description','series','series_index','page_count','page_count_kind','word_count','cover_url') if b[key])
        visibility_form=f'<form method="post" action="/book/{book_id}/visibility" class="visibility-form">{token()}<input type="hidden" name="hidden" value="{0 if b["hidden"] else 1}"><button class="ghost" type="submit">{ "unhide book" if b["hidden"] else "hide from library" }</button><span class="muted">{ "this book is hidden from the default catalog" if b["hidden"] else "keep the metadata; remove it from the default catalog" }</span></form>'
        statusopts=''.join(f'<option value="{s}" {"selected" if r and r["status"]==s else ""}>{LABELS[s]}</option>' for s in STATES)
        def val(k):return h(r[k] if r and r[k] is not None else '')
        reading=f'''<form method="post" action="/book/{book_id}/reading" class="panel">{token()}<h2>Reading record</h2><label>Status<select name="status">{statusopts}</select></label><label>Started<input type="date" name="started" value="{val('started')}"></label><label>Finished<input type="date" name="finished" value="{val('finished')}"></label><label>Time read (minutes)<input type="number" min="0" name="minutes_read" value="{val('minutes_read')}"></label><label>Current page<input type="number" min="0" name="current_page" value="{val('current_page')}"></label><label>Rating (0–5)<input type="number" min="0" max="5" step="0.5" name="rating" value="{val('rating')}"></label><label>Read count<input type="number" min="0" name="read_count" value="{val('read_count')}"></label><label>Notes<textarea name="notes" rows="5">{val('notes')}</textarea></label><button>Save reading record</button></form>'''
        sessionform=f'<form method="post" action="/book/{book_id}/session" class="panel">{token()}<h3>Add reading session</h3><label>Started<input type="date" name="started"></label><label>Finished<input type="date" name="finished"></label><label>Minutes<input type="number" min="0" name="minutes_read"></label><label>Pages read<input type="number" min="0" name="pages_read"></label><label>Note<input name="note"></label><button>Add session</button></form>'
        fileitems=''.join(f'<li>{h(x["path"])} · {x["bytes"]:,} bytes · {h(x["extension"])} {"(unavailable)" if x["missing"] else ""}{" · "+h(x["extract_error"]) if x["extract_error"] else ""}</li>' for x in files)
        series_form=f'<form class=panel method=post action=/book/{book_id}/series>{token()}<h3>edit series membership</h3><label>Series name<input name=series value="{h(b["series"] or "")}" list=series-options></label><datalist id=series-options>{"".join(f"<option value={h(x[0])}>" for x in series_names)}</datalist><label>Volume number<input name=index type=number step=any min=0 value="{h(b["series_index"])}"></label><button>Save series assignment</button></form>'
        category_form=f'<form method="post" action="/book/{book_id}/category">{token()}<label>Add category/shelf<input name="category" maxlength="80" required></label><button>Add category</button></form>'
        card=f'<section class="panel">{f"<img class=detail-cover src=/cover/{book_id} alt=cover>" if b["cover_path"] else ""}<h1>{h(b["title"])}</h1><p>{h(", ".join(jsonarr(b["authors"])))}</p>{fields}<p>Categories: {" ".join(f"<span class=tag>{h(x[0])} · {int(x[1]*100)}%</span>" for x in cats)}</p>{category_form}<h3>Files (read-only references)</h3><ul>{fileitems}</ul><details><summary>Metadata sources & confidence</summary><pre>{h(json.dumps(json.loads(b["provenance_json"]),indent=2))}</pre><pre>{h(json.dumps(json.loads(b["confidence_json"]),indent=2))}</pre><pre>{h(json.dumps(json.loads(b["metadata_json"]),indent=2))}</pre></details></section>'
        sessions_html=''.join(f'<li>{h(x["started"])} → {h(x["finished"])} · {h(x["minutes_read"])} min · {h(x["note"])}</li>' for x in sessions)
        related=''.join(f'<li><a href="/book/{x["other_id"]}">{h(x["other_title"])}</a> · {h(x["kind"])} ({round(x["confidence"]*100)}%) · {"resolved" if x["resolved"] else "pending"}</li>' for x in relations)
        siblings=''.join(f'<li><a href="/book/{x["id"]}">{h(x["title"])}</a> · #{h(x["series_index"])}</li>' for x in series_members)
        folder_items=''.join(f'<li><code>{h(x["folder_path"])}</code> → {h(x["category"])} ({round(x["confidence"]*100)}%)</li>' for x in folders)
        pending_items=''.join(f'<li>{h(x["field"])} · {round(x["confidence"]*100)}% · {h(x["reason"])}</li>' for x in pending)
        quick=''.join(f'<form method="post" action="/book/{book_id}/quick">{token()}<button class="status-button" name="status" value="{st}" aria-label="Mark {h(b["title"])} as {h(LABELS[st])}">{h(LABELS[st])}</button></form>' for st in ("finished","reading","want_to_read","not_read","on_hold","abandoned"))
        overview=f'<section class="panel"><h2>quick reading status</h2><div class="status-actions">{quick}</div><p class="muted">One click updates your reading status; detailed dates and notes are below.</p></section><section class="panel"><h2>connected records</h2><h3>series</h3><p>{h(b["series"] or "No confirmed series")} · <a href="/series">manage series</a></p><ul>{siblings or "<li>No other volumes indexed</li>"}</ul><h3>possible editions & duplicates</h3><ul>{related or "<li>No matches</li>"}</ul><h3>source folders</h3><ul>{folder_items or "<li>No folder labels yet. Rescan to populate.</li>"}</ul><h3>metadata needing review</h3><ul>{pending_items or "<li>None</li>"}</ul></section>'
        return layout(b['title'],f'<div class="split"><div>{card}{overview}{series_form}<section class="panel"><h3>Reading sessions</h3><ul>{sessions_html or "No sessions yet"}</ul></section>{sessionform}</div><div>{reading}</div></div>')
    @app.post('/book/{book_id}/quick')
    def book_quick(book_id:int,csrf:str=Form(...),status:str=Form(...)):
        guard(csrf)
        if status not in STATES or status=='unanswered':raise HTTPException(422)
        with db() as c:
            result=c.execute('UPDATE reading SET status=?,updated_at=? WHERE book_id=?',(status,now(),book_id))
            if not result.rowcount:raise HTTPException(404)
            c.commit()
        return go(f'/book/{book_id}')
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
            rows=c.execute(f'SELECT b.id,b.title,b.series,b.cover_path,r.status FROM books b JOIN reading r ON b.id=r.book_id WHERE {" AND ".join(conditions)} ORDER BY b.series,b.series_index,b.title LIMIT 30',args).fetchall()
        opts=lambda data,current:''.join(f'<option value="{h(x)}" {"selected" if x==current else ""}>{h(x)}</option>' for x in data)
        controls=f'<form method="get" class="panel toolbar"><select name="scope">{opts(["all","category","series"],scope)}</select><select name="category"><option value="">Choose category</option>{opts(categories,category)}</select><select name="series"><option value="">Choose series</option>{opts(series_names,series)}</select><label><input type="checkbox" name="include_answered" value="1" {"checked" if include_answered else ""}> Show answered</label><button>Apply</button></form>'
        cards=''.join(f'<div class="panel reading-card bulk-item" data-bulk-kind="book"><label class="bulk-check"><input aria-label="select {h(x["title"])}" type="checkbox" class="bulk-select" value="{x["id"]}"><span>select</span></label><a class="reading-cover" href="/book/{x["id"]}">'+(f'<img src="/cover/{x["id"]}" loading="lazy" alt="cover of {h(x["title"])}" onerror="this.hidden=true">' if x['cover_path'] else f'<span class="book-cover-placeholder">{h(x["title"])}</span>')+f'</a><div class="reading-card-info"><a href="/book/{x["id"]}"><b>{h(x["title"])}</b></a><p class="muted">{h(x["series"])} · {h(LABELS.get(x["status"],""))}</p><form method="post" action="/reading/quick/{x["id"]}">{token()}<div class="status-actions">{"".join(f"<button class=status-button name=status value={st}>{h(LABELS[st])}</button>" for st in ("finished","reading","want_to_read","not_read","on_hold","abandoned"))}</div></form></div></div>' for x in rows)
        return layout('Reading review',f'<h1>reading review.</h1><p>One click per book. The queue shows up to 30 titles at a time; new entries appear automatically as you classify them. Filter by category or series. Dates, reading time, and notes are on each book page.</p>{controls}{bulk_toolbar("book")}{cards or "<p>Nothing left in this selection.</p>"}')
    @app.post('/reading/quick/{book_id}')
    def quick(book_id:int,csrf:str=Form(...),status:str=Form(...)):
        guard(csrf)
        if status not in STATES:raise HTTPException(422)
        with db() as c:
            c.execute('UPDATE reading SET status=?,updated_at=? WHERE book_id=?',(status,now(),book_id));c.commit()
        return go('/reading')
    @app.get('/quick-sort',response_class=HTMLResponse)
    def quick_sort(scope:str='unanswered',series:str='',category:str=''):
        if scope not in ('unanswered','all','unread'):raise HTTPException(422,'Invalid scope')
        with db() as c:
            where=['COALESCE(b.hidden,0)=0'];args=[]
            if scope=='unanswered':where.append("COALESCE(r.status,'unanswered')='unanswered'")
            if scope=='unread':where.append("COALESCE(r.status,'unanswered') IN ('unanswered','not_read','want_to_read')")
            if series:where.append('b.series=?');args.append(series)
            if category:
                where.append('EXISTS(SELECT 1 FROM book_categories bc JOIN categories cat ON cat.id=bc.category_id WHERE bc.book_id=b.id AND cat.name=?)');args.append(category)
            books=c.execute('SELECT b.id,b.title,b.authors,b.series,b.description,COALESCE(r.status,"unanswered") AS status FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE '+ ' AND '.join(where)+' ORDER BY b.id LIMIT 300',args).fetchall()
            series_options=[x[0] for x in c.execute('SELECT DISTINCT series FROM books WHERE series IS NOT NULL AND series<>"" ORDER BY series')]
            cats=[x[0] for x in c.execute('SELECT name FROM categories ORDER BY name')]
        data=[dict(x) for x in books]
        options=lambda values,chosen:''.join(f'<option value="{h(x)}" {"selected" if x==chosen else ""}>{h(x)}</option>' for x in values)
        controls=f'''<form method="get" class="qs-filters"><label>queue<select name="scope">{options(['unanswered','unread','all'],scope)}</select></label><label>series<select name="series"><option value="">all series</option>{options(series_options,series)}</select></label><label>category<select name="category"><option value="">all categories</option>{options(cats,category)}</select></label><button>apply</button></form>'''
        client=json.dumps(data).replace('<','\\u003c')
        return layout('quick sort',f'''<div class="section-head">reading / triage</div><h1>quick sort.</h1><p class="hero-sub">right → finished. left → not read. up → skip. down → hide. arrow keys work too.</p>{controls}<section class="qs-shell" aria-label="quick sort"><div class="qs-count" id="qs-count" aria-live="polite"></div><div class="qs-card" id="qs-card" tabindex="0" aria-label="book to classify"><div class="qs-cover"><img id="qs-cover" alt="book cover"></div><div class="qs-info"><span class="qs-kicker" id="qs-series"></span><h2 id="qs-title"></h2><p id="qs-author"></p><p id="qs-description"></p></div></div><p id="qs-message" role="status" aria-live="polite"></p><div class="qs-actions"><button type="button" id="qs-no" class="qs-no" aria-label="not read, left arrow">← not read</button><button type="button" id="qs-skip" class="ghost" aria-label="skip, up arrow">↑ skip</button><button type="button" id="qs-detail" class="ghost" aria-label="hide book, down arrow">↓ hide</button><button type="button" id="qs-yes" class="qs-yes" aria-label="finished, right arrow">read →</button></div></section><script>
(()=>{{'use strict';const books={client};const csrf={json.dumps(app.state.csrf)};let i=0,busy=false,start=null;const el=id=>document.getElementById(id);const card=el('qs-card');function render(){{if(i>=books.length){{card.hidden=true;el('qs-message').textContent='queue complete. choose another filter to continue.';el('qs-count').textContent=`${{books.length}} / ${{books.length}}`;return}}const b=books[i];card.hidden=false;el('qs-count').textContent=`${{i+1}} / ${{books.length}}`;el('qs-cover').src='/cover/'+b.id;el('qs-cover').alt='cover for '+b.title;el('qs-title').textContent=b.title;let authors=b.authors;try{{authors=JSON.parse(authors).join(', ')}}catch(e){{}}el('qs-author').textContent=authors||'unknown author';el('qs-series').textContent=b.series||'standalone / unknown series';el('qs-description').textContent=(b.description||'').slice(0,270);el('qs-message').textContent='';card.focus({{preventScroll:true}})}}async function act(action){{if(busy||i>=books.length)return;const b=books[i];if(action==='skip'){{i++;render();return}}busy=true;try{{const body=new URLSearchParams({{csrf,status:action}});const r=await fetch('/quick-sort/'+b.id,{{method:'POST',body,headers:{{'Accept':'application/json'}}}});if(!r.ok)throw Error(await r.text());i++;render()}}catch(e){{el('qs-message').textContent='could not save: '+e.message}}finally{{busy=false}}}}el('qs-no').onclick=()=>act('not_read');el('qs-yes').onclick=()=>act('finished');el('qs-skip').onclick=()=>act('skip');el('qs-detail').onclick=()=>act('hide');document.addEventListener('keydown',e=>{{if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(document.activeElement.tagName))return;const keys={{ArrowLeft:'not_read',ArrowRight:'finished',ArrowUp:'skip',ArrowDown:'hide'}};if(keys[e.key]){{e.preventDefault();act(keys[e.key])}}}});card.addEventListener('touchstart',e=>{{if(e.touches.length===1)start={{x:e.touches[0].clientX,y:e.touches[0].clientY}}}},{{passive:true}});card.addEventListener('touchend',e=>{{if(!start)return;const dx=e.changedTouches[0].clientX-start.x,dy=e.changedTouches[0].clientY-start.y;start=null;if(Math.max(Math.abs(dx),Math.abs(dy))<65)return;act(Math.abs(dx)>Math.abs(dy)?(dx>0?'finished':'not_read'):(dy<0?'skip':'hide'))}},{{passive:true}});render()}})();</script>''')
    @app.post('/quick-sort/{book_id}')
    def quick_sort_status(book_id:int,csrf:str=Form(...),status:str=Form(...)):
        guard(csrf)
        if status not in ('finished','not_read','hide'):raise HTTPException(422,'Unsupported quick sort status')
        with db() as c:
            found=c.execute('SELECT id FROM books WHERE id=? AND COALESCE(hidden,0)=0',(book_id,)).fetchone()
            if not found:raise HTTPException(404)
            if status=='hide':
                c.execute('UPDATE books SET hidden=1,updated_at=? WHERE id=?',(now(),book_id))
            else:
                c.execute('INSERT INTO reading(book_id,status,updated_at) VALUES(?,?,?) ON CONFLICT(book_id) DO UPDATE SET status=excluded.status,updated_at=excluded.updated_at',(book_id,status,now()))
            c.commit()
        return JSONResponse({'ok':True,'book_id':book_id,'status':status})

    # Series workspace: discovery is separate from editing. All changes are explicit.
    @app.get('/series',response_class=HTMLResponse)
    def series_index(q:str='',sort:str='name',view:str='grid',state:str='all'):
        with db() as c:
            rows=c.execute('''SELECT s.*, COUNT(b.id) AS total,
                SUM(CASE WHEN r.status='finished' THEN 1 ELSE 0 END) AS completed,
                SUM(CASE WHEN r.status='reading' THEN 1 ELSE 0 END) AS active,
                SUM(CASE WHEN b.series_index IS NULL THEN 1 ELSE 0 END) AS unordered
                FROM series_catalog s LEFT JOIN books b ON b.series=s.name COLLATE NOCASE
                LEFT JOIN reading r ON r.book_id=b.id GROUP BY s.id''').fetchall()
            covers={x['id']:c.execute('SELECT id,title FROM books WHERE series=? COLLATE NOCASE ORDER BY series_index IS NULL,series_index,title LIMIT 3',(x['name'],)).fetchall() for x in rows}
        entries=[x for x in rows if (not q or q.casefold() in x['name'].casefold()) and (state=='all' or (state=='unread' and not x['completed']) or (state=='in_progress' and x['active']) or (state=='complete' and x['total'] and x['total']==x['completed']) or (state=='needs_order' and x['unordered']))]
        entries.sort(key=({'name':lambda x:x['name'].casefold(),'size':lambda x:-x['total'],'progress':lambda x:-(x['completed'] or 0)/max(1,x['total'])}.get(sort,lambda x:x['name'].casefold())))
        def card(x):
            volumes=covers[x['id']]
            thumbs=''.join(f'<div class="series-cover"><img src="/cover/{bk["id"]}" alt="" loading="lazy" onerror="this.hidden=true"><span>{h(bk["title"])}</span></div>' for bk in volumes)
            return f'''<div class="bulk-item series-select-item" data-bulk-kind="series"><label class="bulk-check"><input type="checkbox" class="bulk-select" value="{x['id']}" aria-label="select series {h(x['name'])}"><span>select</span></label><a class="series-tile" data-menu="series" data-series-id="{x['id']}" href="/series/{x['id']}"><div class="series-stack">{thumbs or '<div class="series-empty">no books yet</div>'}</div><div class="series-tile-body"><div class="series-tile-title">{h(x['name'])}</div><div class="series-tile-meta">{x['total']} books <span aria-hidden="true">·</span> {x['completed'] or 0} finished</div><div class="series-progress" role="progressbar" aria-label="reading progress" aria-valuenow="{x['completed'] or 0}" aria-valuemin="0" aria-valuemax="{max(x['total'],1)}"><span style="width:{100*(x['completed'] or 0)/max(x['total'],1):.1f}%"></span></div>{'<div class="series-warning">order needs review</div>' if x['unordered'] else ''}</div></a></div>'''
        def opt(v,t,current):return f'<option value="{h(v)}" {"selected" if v==current else ""}>{h(t)}</option>'
        controls=f'''<form method="get" class="series-controls"><label>find a series<input name="q" value="{h(q)}" placeholder="search series…"></label><label>show<select name="state">{''.join(opt(v,t,state) for v,t in [('all','all series'),('in_progress','currently reading'),('complete','completed'),('unread','none finished'),('needs_order','missing volume order')])}</select></label><label>sort<select name="sort">{''.join(opt(v,t,sort) for v,t in [('name','name'),('size','most books'),('progress','most read')])}</select></label><button>apply</button></form>'''
        summary=f'<div class="series-summary"><div><strong>{len(rows)}</strong><span>series</span></div><div><strong>{sum(x["total"] for x in rows)}</strong><span>assigned books</span></div><div><strong>{sum(bool(x["unordered"]) for x in rows)}</strong><span>need ordering</span></div></div>'
        create=f'<details class="series-create"><summary>+ create a series</summary><form method="post" action="/series/new">{token()}<label>series name<input name="name" maxlength="250" required placeholder="new series name"></label><button>create series</button></form></details>'
        return layout('series',f'<div class="series-head"><div><div class="section-head">library / collections</div><h1>your series.</h1><p class="muted">Browse your collections; open one to arrange books, correct volumes, and manage membership.</p></div>{create}</div>{summary}{controls}{bulk_toolbar("series")}<div class="series-grid">{"".join(card(x) for x in entries) or "<p>No series match these filters.</p>"}</div>')

    @app.get('/series/{series_id}',response_class=HTMLResponse)
    def series_detail(series_id:int,q:str=''):
        with db() as c:
            item=c.execute('SELECT * FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not item:raise HTTPException(404)
            members=c.execute('SELECT b.id,b.title,b.series_index,b.authors,b.cover_path,r.status FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE b.series=? COLLATE NOCASE ORDER BY b.series_index IS NULL,b.series_index,b.title',(item['name'],)).fetchall()
            unassigned=c.execute('SELECT id,title,authors FROM books WHERE (series IS NULL OR TRIM(series)="") AND (title LIKE ? OR authors IN (SELECT authors FROM books WHERE series=? COLLATE NOCASE)) ORDER BY title LIMIT 40',(f'%{item["name"]}%',item['name'])).fetchall()
            searches=c.execute('SELECT id,title,authors,series FROM books WHERE title LIKE ? AND (series IS NULL OR series<>? COLLATE NOCASE) ORDER BY title LIMIT 40',(f'%{q}%',item['name'])).fetchall() if q.strip() else []
        count=len(members);done=sum(x['status']=='finished' for x in members)
        def row(b):
            status=LABELS.get(b['status'],'not answered')
            return f'''<div class="series-volume bulk-item" data-bulk-kind="book"><label class="bulk-check"><input type="checkbox" class="bulk-select" value="{b['id']}" aria-label="select {h(b['title'])}"><span>select</span></label><div class="series-volume-content" data-menu="book" data-book-id="{b['id']}" data-series-id="{series_id}"><a href="/book/{b['id']}" class="series-volume-cover"><img src="/cover/{b['id']}" loading="lazy" alt="cover of {h(b['title'])}" onerror="this.style.display='none'"></a><div class="series-volume-info"><a href="/book/{b['id']}"><strong>{h(b['title'])}</strong></a><span>{h(', '.join(jsonarr(b['authors'])))} · {h(status)}</span></div><form method="post" action="/series/{series_id}/member/{b['id']}" class="series-inline-edit">{token()}<label>volume<input type="number" step="any" min="0" name="index" value="{h(b['series_index'])}" aria-label="volume number for {h(b['title'])}"></label><button name="action" value="save">save</button><button class="ghost" name="action" value="remove" aria-label="remove {h(b['title'])} from series">remove</button></form></div></div>'''
        def add_row(b):return f'<form class="series-candidate" data-menu="candidate" data-book-id="{b["id"]}" data-series-id="{series_id}" method="post" action="/series/{series_id}/member/{b["id"]}">{token()}<div><strong>{h(b["title"])}</strong><span>{h(", ".join(jsonarr(b["authors"])))}</span></div><input type="hidden" name="index" value=""><button name="action" value="add">+ add</button></form>'
        edit=f'''<details id="series-settings" class="series-settings"><summary>series settings</summary><form method="post" action="/series/{series_id}">{token()}<label>series name<input name="name" maxlength="250" required value="{h(item['name'])}"></label><label>description<textarea name="description" rows="3">{h(item['description'] or '')}</textarea></label><label>private notes<textarea name="notes" rows="3">{h(item['notes'] or '')}</textarea></label><button>save details</button></form><form method="post" action="/series/{series_id}/delete" onsubmit="return confirm('Delete this series? Books will be kept and unassigned.');">{token()}<button class="danger" type="submit">delete series</button></form></details>'''
        candidates=f'''<section class="series-side-panel"><h2>add books</h2><p class="muted">Search your whole library, or choose one of the possible matches below. Nothing is assigned automatically.</p><form method="get" action="/series/{series_id}"><label>find by title<input name="q" value="{h(q)}" placeholder="search a title…"></label><button>search library</button></form><div class="series-candidates">{''.join(add_row(b) for b in searches or unassigned) or '<p class="muted">No candidates found.</p>'}</div></section>'''
        return layout(item['name'],f'''<div class="series-breadcrumb"><a href="/series">← all series</a></div><div class="series-detail-head"><div><div class="section-head">series / organize</div><h1>{h(item['name'])}</h1><p class="muted">{count} books · {done} finished · {count-done} remaining</p></div>{edit}</div><div class="series-workspace"><section class="series-main"><div class="series-section-top"><div><h2>reading order</h2><p class="muted">Set the volume number to organize your collection. Changes save per book.</p></div></div>{bulk_toolbar("book")}<div class="series-volumes">{''.join(row(b) for b in members) or '<div class="series-empty-state">No books assigned yet. Add books from the right.</div>'}</div></section>{candidates}</div>''')

    @app.post('/series/{series_id}/member/{book_id}')
    def update_member(series_id:int,book_id:int,csrf:str=Form(...),action:str=Form(...),index:str=Form('')):
        guard(csrf)
        if action not in ('save','add','remove'):raise HTTPException(422)
        try:ordinal=float(index) if index.strip() else None
        except ValueError:raise HTTPException(422,'Invalid volume')
        if ordinal is not None and ordinal<0:raise HTTPException(422,'Invalid volume')
        with db() as c:
            series=c.execute('SELECT name FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            book=c.execute('SELECT series FROM books WHERE id=?',(book_id,)).fetchone()
            if not series or not book:raise HTTPException(404)
            if action in ('save','remove') and (book['series'] or '').casefold()!=series['name'].casefold():raise HTTPException(409,'Book no longer belongs to series')
            c.execute('UPDATE books SET series=?,series_index=?,manually_verified=1,updated_at=? WHERE id=?',(None if action=='remove' else series['name'],None if action=='remove' else ordinal,now(),book_id))
            c.execute("UPDATE review_queue SET resolved=1 WHERE book_id=? AND field IN ('series','series_index')",(book_id,))
            c.commit()
        return go(f'/series/{series_id}')

    @app.post('/series/new')
    def create_series(csrf:str=Form(...),name:str=Form(...)):
        guard(csrf);name=name.strip()
        if not name or len(name)>250:raise HTTPException(422)
        with db() as c:
            c.execute('INSERT OR IGNORE INTO series_catalog(name,updated_at) VALUES(?,?)',(name,now()));c.commit()
            row=c.execute('SELECT id FROM series_catalog WHERE name=? COLLATE NOCASE',(name,)).fetchone()
        return go(f'/series/{row["id"]}')
    @app.post('/book/{book_id}/series')
    def assign_series(book_id:int,csrf:str=Form(...),series:str=Form(''),index:str=Form('')):
        guard(csrf);series=series.strip()
        if len(series)>250:raise HTTPException(422)
        try:ordinal=float(index) if index.strip() else None
        except ValueError:raise HTTPException(422,'Invalid series volume')
        with db() as c:
            if not c.execute('SELECT 1 FROM books WHERE id=?',(book_id,)).fetchone():raise HTTPException(404)
            if series:c.execute('INSERT OR IGNORE INTO series_catalog(name,updated_at) VALUES(?,?)',(series,now()))
            c.execute('UPDATE books SET series=?,series_index=?,manually_verified=1,updated_at=? WHERE id=?',(series or None,ordinal,now(),book_id))
            c.execute("UPDATE review_queue SET resolved=1 WHERE book_id=? AND field IN ('series','series_index')",(book_id,))
            c.commit()
        return go(f'/book/{book_id}')
    @app.post('/series/{series_id}/delete')
    def delete_series(series_id:int,csrf:str=Form(...)):
        guard(csrf)
        with db() as c:
            entry=c.execute('SELECT name FROM series_catalog WHERE id=?',(series_id,)).fetchone()
            if not entry:raise HTTPException(404)
            c.execute('UPDATE books SET series=NULL,series_index=NULL,manually_verified=1,updated_at=? WHERE series=? COLLATE NOCASE',(now(),entry['name']))
            c.execute('DELETE FROM series_catalog WHERE id=?',(series_id,));c.commit()
        return go('/series')
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
        return go(f'/series/{series_id}')
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
            count=c.execute('SELECT COUNT(*) FROM books').fetchone()[0]
            hidden=c.execute('SELECT COUNT(*) FROM books WHERE hidden=1').fetchone()[0]
            books_with_cover=c.execute("SELECT COUNT(*) FROM books WHERE cover_path IS NOT NULL AND cover_path<>''").fetchone()[0]
            pending=c.execute('SELECT COUNT(*) FROM review_queue WHERE resolved=0').fetchone()[0]
            unassigned=c.execute("SELECT COUNT(*) FROM books WHERE series IS NULL OR TRIM(series)=''").fetchone()[0]
            series_count=c.execute('SELECT COUNT(*) FROM series_catalog').fetchone()[0]
            duplicates=c.execute('SELECT COUNT(*) FROM book_links WHERE resolved=0').fetchone()[0]
            rows=c.execute("SELECT COALESCE(r.status,'unanswered') AS state,COUNT(*) AS n FROM books b LEFT JOIN reading r ON r.book_id=b.id GROUP BY state").fetchall()
            formats=c.execute('SELECT LOWER(extension) AS ext,COUNT(*) AS n FROM files GROUP BY LOWER(extension) ORDER BY n DESC LIMIT 10').fetchall()
            read_minutes=c.execute('SELECT COALESCE(SUM(minutes_read),0) FROM reading').fetchone()[0]
            sessions=c.execute('SELECT COUNT(*),COALESCE(SUM(minutes_read),0) FROM reading_sessions').fetchone()
            pages=c.execute("SELECT COALESCE(SUM(page_count),0) FROM books WHERE page_count_kind IN ('pdf','publisher')").fetchone()[0]
            monthly=c.execute("SELECT substr(finished,1,7) AS month,COUNT(*) AS n FROM reading WHERE finished IS NOT NULL AND finished<>'' GROUP BY month ORDER BY month DESC LIMIT 12").fetchall()
            sources=c.execute('SELECT COUNT(DISTINCT folder_path) FROM folder_categories').fetchone()[0]
            top_series=c.execute("SELECT series,COUNT(*) AS n FROM books WHERE series IS NOT NULL AND TRIM(series)<>'' GROUP BY series ORDER BY n DESC LIMIT 8").fetchall()
        by_state={r['state']:r['n'] for r in rows}
        classified=count-by_state.get('unanswered',0)
        finished=by_state.get('finished',0)
        def metric(value,label,sub=''):
            return f'<div class="analytics-metric"><strong>{h(value)}</strong><span>{h(label)}</span><small>{h(sub)}</small></div>'
        def bars(items,total=None):
            peak=max((v for _,v in items),default=0) if total is None else total
            return ''.join(f'<div class="analytics-row"><div><span>{h(name)}</span><strong>{n:,}</strong></div><div class="analytics-track"><span style="width:{min(100,100*n/max(1,peak)):.1f}%"></span></div></div>' for name,n in items) or '<p class="muted">Nothing to chart yet.</p>'
        metrics=''.join([metric(f'{count:,}','books indexed',f'{hidden:,} hidden'),metric(f'{classified/max(1,count):.0%}','classified',f'{classified:,} / {count:,}'),metric(f'{finished:,}','finished books',f'{by_state.get("reading",0):,} currently reading'),metric(f'{read_minutes/60:,.1f}h','reading time',f'{sessions[0]:,} reading sessions')])
        status_items=[(LABELS.get(k,k),by_state.get(k,0)) for k in STATES]
        quality=''.join([metric(f'{books_with_cover/max(1,count):.0%}','covers cached',f'{books_with_cover:,} books'),metric(f'{series_count:,}','series',f'{unassigned:,} books unassigned'),metric(f'{pending:,}','metadata suggestions','awaiting review'),metric(f'{duplicates:,}','possible editions','awaiting reconciliation')])
        return layout('statistics',f'''<div class="section-head">library / insights</div><h1>the numbers.</h1><p class="hero-sub">Your reading progress and the state of your catalog; nothing here requires online access.</p><div class="analytics-metrics">{metrics}</div><div class="analytics-grid"><section class="panel analytics-panel"><div class="analytics-heading"><h2>reading status</h2><a href="/reading">review books →</a></div>{bars(status_items,count)}</section><section class="panel analytics-panel"><div class="analytics-heading"><h2>format distribution</h2><span class="muted">file copies, not unique books</span></div>{bars([((x['ext'] or 'unknown').upper(),x['n']) for x in formats])}</section></div><div class="analytics-grid"><section class="panel analytics-panel"><div class="analytics-heading"><h2>catalog health</h2><a href="/review">review metadata →</a></div><div class="analytics-quality">{quality}</div><p class="muted">{sources:,} distinct source folder labels · {pages:,} reported fixed pages (when available).</p></section><section class="panel analytics-panel"><h2>finished by month</h2><p class="muted">Based on recorded finish dates, not automatically inferred statuses.</p>{bars([(x['month'],x['n']) for x in reversed(monthly)])}</section></div><section class="panel analytics-panel"><div class="analytics-heading"><h2>largest series</h2><a href="/series">browse series →</a></div>{bars([(x['series'],x['n']) for x in top_series])}</section>''')
    return app
