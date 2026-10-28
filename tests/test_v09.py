from fastapi.testclient import TestClient
from bookledger.core import connect, now
from bookledger.webapp import create_app


def test_v09_quick_hide_stats_and_context(tmp_path):
    path=tmp_path/'books.sqlite3'
    with connect(path) as db:
        db.execute("INSERT INTO books(title,authors,created_at,updated_at) VALUES('Test book','[]',?,?)",(now(),now()))
        book=db.execute('SELECT id FROM books').fetchone()[0]
        db.execute("INSERT INTO series_catalog(name,updated_at) VALUES('Test Series',?)",(now(),))
        sid=db.execute('SELECT id FROM series_catalog').fetchone()[0]
        db.execute('UPDATE books SET series=? WHERE id=?',('Test Series',book))
        db.commit()
    app=create_app(path)
    client=TestClient(app)
    page=client.get('/quick-sort')
    assert page.status_code==200
    assert '↓ hide' in page.text
    assert "ArrowDown:'hide'" in page.text
    token=app.state.csrf
    r=client.post(f'/quick-sort/{book}',data={'csrf':token,'status':'hide'})
    assert r.status_code==200
    with connect(path) as db:
        assert db.execute('SELECT hidden FROM books WHERE id=?',(book,)).fetchone()[0]==1
    assert client.get('/stats').status_code==200
    assert 'catalog health' in client.get('/stats').text
    assert 'data-menu="series"' in client.get('/series').text
    assert 'data-menu="book"' in client.get(f'/series/{sid}').text
    script=client.get('/series-menu.js')
    assert script.status_code==200
    assert 'contextmenu' in script.text
    assert 'Delete this series?' in script.text
