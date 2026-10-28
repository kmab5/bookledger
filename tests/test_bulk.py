from fastapi.testclient import TestClient
from bookledger.core import connect, now
from bookledger.webapp import create_app


def test_bulk_book_operations_and_reading_covers(tmp_path):
    db_path=tmp_path/'library.sqlite3'
    with connect(db_path) as db:
        for title in ('Alpha','Beta','Gamma'):
            db.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',(title,'[]',now(),now()))
        db.execute("INSERT INTO series_catalog(name,updated_at) VALUES('Trilogy',?)",(now(),))
        db.execute("UPDATE books SET series='Trilogy' WHERE id<=2")
        db.execute("INSERT INTO reading(book_id,status,updated_at) VALUES(1,'unanswered',?)",(now(),))
        db.execute("INSERT INTO reading(book_id,status,updated_at) VALUES(2,'unanswered',?)",(now(),))
        db.commit()
    app=create_app(db_path);client=TestClient(app)
    for path in ('/','/reading','/series','/series/1'):
        response=client.get(path)
        assert response.status_code==200
        assert 'bulk-toolbar' in response.text
        assert 'bulk-select' in response.text
    assert 'reading-cover' in client.get('/reading').text
    assert client.get('/bulk.js').status_code==200
    csrf=app.state.csrf
    assert client.post('/bulk/books',data={'csrf':csrf,'ids':['1','2'],'action':'finished'},follow_redirects=False).status_code==303
    assert client.post('/bulk/books',data={'csrf':csrf,'ids':['1','3'],'action':'hide'},follow_redirects=False).status_code==303
    assert client.post('/bulk/books',data={'csrf':csrf,'ids':['1','2'],'action':'unassign_series'},follow_redirects=False).status_code==303
    with connect(db_path) as db:
        assert db.execute("SELECT count(*) FROM reading WHERE status='finished'").fetchone()[0]==2
        assert [x[0] for x in db.execute('SELECT hidden FROM books ORDER BY id')]==[1,0,1]
        assert db.execute('SELECT count(*) FROM books WHERE series IS NULL').fetchone()[0]==3
    assert client.post('/bulk/books',data={'csrf':csrf,'ids':['1'],'action':'nope'}).status_code==422
    assert client.post('/bulk/books',data={'csrf':'bad','ids':['1'],'action':'hide'}).status_code==403
    assert client.post('/bulk/series',data={'csrf':csrf,'ids':['1'],'action':'delete'},follow_redirects=False).status_code==303
    with connect(db_path) as db:
        assert db.execute('SELECT count(*) FROM books').fetchone()[0]==3
        assert db.execute('SELECT count(*) FROM series_catalog').fetchone()[0]==0
