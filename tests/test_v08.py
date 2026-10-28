from fastapi.testclient import TestClient
from bookledger.core import connect, enrich_existing
from bookledger.webapp import create_app

def test_quick_sort_and_delete_series(tmp_path):
    path=tmp_path/'library.sqlite'
    with connect(path) as c:
        c.execute("INSERT INTO series_catalog(name,updated_at) VALUES('My Saga','now')")
        c.execute("INSERT INTO books(title,authors,series,created_at,updated_at) VALUES('Book 1','[]','My Saga','now','now')")
        c.execute("INSERT INTO reading(book_id,status,updated_at) VALUES(1,'unanswered','now')")
        c.commit()
    app=create_app(path);client=TestClient(app)
    response=client.get('/quick-sort')
    assert response.status_code==200 and 'quick sort.' in response.text
    assert client.post('/quick-sort/1',data={'csrf':app.state.csrf,'status':'finished'}).json()['ok']
    with connect(path) as c:
        assert c.execute('SELECT status FROM reading WHERE book_id=1').fetchone()[0]=='finished'
    assert client.get('/series/1').status_code==200
    assert 'delete series' in client.get('/series/1').text
    assert client.post('/series/1/delete',data={'csrf':app.state.csrf},follow_redirects=False).status_code==303
    with connect(path) as c:
        assert c.execute('SELECT series FROM books WHERE id=1').fetchone()[0] is None
        assert c.execute('SELECT COUNT(*) FROM books').fetchone()[0]==1
        assert c.execute('SELECT status FROM reading WHERE book_id=1').fetchone()[0]=='finished'

def test_enrich_batches(tmp_path,monkeypatch):
    path=tmp_path/'db.sqlite'
    with connect(path) as c:
        for n in range(5):
            c.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',(f'Book {n}','[]','now','now'))
        c.commit()
        import bookledger.core as core
        monkeypatch.setattr(core,'enrich',lambda db,data,allow_online=True: ({},{}))
        monkeypatch.setattr(core,'cache_cover',lambda *a,**kw: None)
        a=enrich_existing(c,start_after=0,limit=2,mode='covers')
        assert a['examined']==2 and a['last_id']==2
        b=enrich_existing(c,start_after=a['last_id'],limit=2,mode='covers')
        assert b['examined']==2 and b['last_id']==4
    app=create_app(path);client=TestClient(app)
    assert client.get('/enrich').status_code==200
    assert client.get('/enrich/status').status_code==200
