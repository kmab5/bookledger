import zipfile
from fastapi.testclient import TestClient
from bookledger.core import connect,scan,enrich_existing,EXTRACTOR_VERSION
from bookledger.webapp import create_app

def test_enrich_missing_fields_no_crash(tmp_path,monkeypatch):
    import bookledger.core as core
    db=connect(tmp_path/'lib.db')
    db.execute("INSERT INTO books(title,authors,created_at,updated_at) VALUES('Example','[]','now','now')")
    db.commit()
    monkeypatch.setattr(core,'enrich',lambda *args,**kw:({'publisher':'Acme','page_count':200},{}))
    stats=enrich_existing(db)
    assert stats['errors']==0 and stats['enriched']==1
    assert db.execute('SELECT publisher FROM books').fetchone()[0]=='Acme'

def test_enrich_one_failure_continues(tmp_path,monkeypatch):
    import bookledger.core as core
    db=connect(tmp_path/'lib.db')
    for title in ('Bad','Good'):
        db.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',(title,'[]','now','now'))
    db.commit()
    def lookup(db,data,allow):
        if data['title']=='Bad':raise RuntimeError('external catalog failure')
        return {'language':'eng'},{}
    monkeypatch.setattr(core,'enrich',lookup)
    stats=enrich_existing(db)
    assert stats['errors']==1 and stats['enriched']==1 and stats['examined']==2

def test_folder_categories_and_rescan_upgrade(tmp_path):
    folder=tmp_path/'Library'/'Historical Fiction'/'Example Saga'
    folder.mkdir(parents=True)
    path=folder/'Novel - Writer.epub'
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="content.opf"/></rootfiles></container>')
        z.writestr('content.opf','<package><metadata><title>Novel</title><creator>Writer</creator></metadata></package>')
    db=connect(tmp_path/'lib.db')
    assert scan(db,tmp_path/'Library',online=False)['new']==1
    assert db.execute('SELECT COUNT(*) FROM folder_categories').fetchone()[0]==2
    assert scan(db,tmp_path/'Library',online=False)['unchanged']==1
    db.execute('UPDATE files SET extractor_version=?',(EXTRACTOR_VERSION-1,));db.commit()
    assert scan(db,tmp_path/'Library',online=False)['updated']==1
    assert db.execute('SELECT COUNT(*) FROM folder_categories').fetchone()[0]==2

def test_pages_quick_read_and_series(tmp_path):
    db=connect(tmp_path/'lib.db')
    db.execute("INSERT INTO books(title,authors,series,created_at,updated_at) VALUES('Example','[]','Saga','now','now')")
    book_id=db.execute('SELECT id FROM books').fetchone()[0]
    db.execute("INSERT INTO reading(book_id,updated_at) VALUES(?,?)",(book_id,'now'))
    db.execute("INSERT INTO series_catalog(name,updated_at) VALUES('Saga','now')")
    db.commit();db.close()
    app=create_app(tmp_path/'lib.db');client=TestClient(app)
    assert client.get('/book/1').status_code==200
    assert client.get('/series').status_code==200
    assert client.get('/series/1').status_code==200
    csrf=app.state.csrf
    assert client.post('/book/1/quick',data={'csrf':csrf,'status':'finished'},follow_redirects=False).status_code==303
    with connect(tmp_path/'lib.db') as db:
        assert db.execute('SELECT status FROM reading').fetchone()[0]=='finished'

def test_explicit_series_title_patterns(tmp_path):
    from bookledger.core import parse_name
    result=parse_name(tmp_path/'Novel [Great Saga #2].epub')
    assert result['title']=='Novel' and result['series']=='Great Saga' and result['series_index']==2
