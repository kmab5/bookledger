from fastapi.testclient import TestClient
from bookledger.core import connect, now
from bookledger.webapp import create_app


def test_quick_sort_editor_and_metadata_persistence(tmp_path):
    path = tmp_path / 'library.sqlite'
    with connect(path) as db:
        db.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',
                   ('Old title','["Old author"]',now(),now()))
        db.commit()
    client = TestClient(create_app(path))
    javascript = client.get('/main.js').text
    assert 'id="quick-metadata"' in javascript
    assert 'book details' in javascript
    assert 'swipe on the cover' in javascript
    assert 'show details' not in javascript.lower()
    payload = {'title':'New title','authors':['Writer One','Writer Two'],
               'publisher':'Test Press','description':'Updated description',
               'series':'Test Saga','series_index':2.5,'page_count':315,
               'started':'2026-01-01','minutes_read':90,'notes':'A good book'}
    response=client.patch('/api/books/1',json=payload)
    assert response.status_code==200, response.text
    result=client.get('/api/books/1').json()
    assert result['book']['title']=='New title'
    assert result['book']['authors']==['Writer One','Writer Two']
    assert result['book']['series_index']==2.5
    assert result['book']['page_count']==315
    assert result['reading']['minutes_read']==90
    assert result['reading']['notes']=='A good book'
    assert client.patch('/api/books/1',json={'title':'  '}).status_code==422
