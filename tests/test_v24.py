from fastapi.testclient import TestClient
from bookledger.core import connect,now
from bookledger.webapp import create_app

def test_bulk_series_assignment_and_quick_queues(tmp_path):
    db_path=tmp_path/'library.db'
    with connect(db_path) as c:
        for title,author in [('Alpha','["Writer"]'),('Beta','["Writer"]'),('Gamma','["Other"]')]:
            c.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',(title,author,now(),now()))
        c.commit()
    client=TestClient(create_app(db_path))
    res=client.post('/api/books/bulk',json={'ids':[1,2],'action':'assign_series','series_name':'A New Series'})
    assert res.status_code==200,res.text
    with connect(db_path) as c:
        assert c.execute('SELECT COUNT(*) FROM books WHERE series=?',('A New Series',)).fetchone()[0]==2
        assert c.execute('SELECT COUNT(*) FROM series_catalog WHERE name=?',('A New Series',)).fetchone()[0]==1
    queue=client.get('/api/quick-sort/queue',params={'scope':'series','value':'A New Series','size':1})
    assert queue.status_code==200,queue.text
    assert queue.json()['total']==2 and len(queue.json()['items'])==1
    authors=client.get('/api/quick-sort/authors').json()['items']
    assert 'Writer' in authors
    assert client.get('/api/quick-sort/queue',params={'scope':'author','value':'Writer'}).json()['total']==2
    assert client.post('/api/books/bulk',json={'ids':[1],'action':'assign_series'}).status_code==422
