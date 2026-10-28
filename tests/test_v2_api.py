from fastapi.testclient import TestClient
from bookledger.core import connect,now
from bookledger.webapp import create_app

def test_spa_and_api(tmp_path):
    path=tmp_path/'library.db'
    with connect(path) as c:
        for name in ('Alpha','Beta'):
            c.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',(name,'["Writer"]',now(),now()))
        c.commit()
    client=TestClient(create_app(path))
    assert client.get('/').status_code==200
    assert client.get('/main.js').status_code==200
    assert client.get('/style.css').status_code==200
    assert client.get('/api/books').json()['total']==2
    assert client.patch('/api/books/1',json={'status':'finished','hidden':True}).status_code==200
    assert client.get('/api/books?visibility=hidden').json()['total']==1
    assert client.post('/api/books/bulk',json={'ids':[1,2],'action':'reading'}).json()['changed']==2
    assert client.get('/api/books/2').json()['reading']['status']=='reading'
    assert client.post('/api/books/2/sessions',json={'minutes_read':40,'note':'nice'}).status_code==200
    assert client.get('/api/stats').json()['counts']['minutes_read']==40
    assert client.post('/api/books/1/categories?name=Favorites').status_code==200
    assert client.get('/api/books/1').json()['categories'][0]['name']=='Favorites'

def test_series_and_exports(tmp_path):
    path=tmp_path/'library.db'
    with connect(path) as c:
        c.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',('Alpha','[]',now(),now()));c.commit()
    client=TestClient(create_app(path))
    sid=client.post('/api/series',json={'name':'Saga'}).json()['id']
    assert client.put(f'/api/series/{sid}/members',json={'book_id':1,'index':2}).status_code==200
    assert client.get(f'/api/series/{sid}').json()['members'][0]['series_index']==2
    assert client.patch(f'/api/series/{sid}',json={'name':'Renamed'}).status_code==200
    assert client.delete(f'/api/series/{sid}').status_code==200
    assert client.get('/api/books/1').json()['book']['series'] is None
    assert client.get('/api/exports/preset/json').status_code==200
    assert client.get('/api/exports/preset/storygraph').status_code==200
