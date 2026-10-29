from fastapi.testclient import TestClient
from bookledger.core import connect
from bookledger.legacy_webapp import create_app

def test_series_workspace_edit_add_remove(tmp_path):
    path=tmp_path/'library.db'
    with connect(path) as c:
        c.execute("INSERT INTO series_catalog(name,updated_at) VALUES('Saga','now')")
        c.execute("INSERT INTO books(title,authors,series,series_index,created_at,updated_at) VALUES('One','[]','Saga',1,'now','now')")
        c.execute("INSERT INTO books(title,authors,created_at,updated_at) VALUES('Two','[]','now','now')")
        c.commit()
    app=create_app(path);client=TestClient(app);csrf=app.state.csrf
    assert 'series-stack' in client.get('/series').text
    assert 'reading order' in client.get('/series/1').text
    r=client.post('/series/1/member/2',data={'csrf':csrf,'action':'add','index':'2'},follow_redirects=False)
    assert r.status_code==303
    with connect(path) as c:
        assert c.execute('SELECT series,series_index FROM books WHERE id=2').fetchone()['series']=='Saga'
    r=client.post('/series/1/member/1',data={'csrf':csrf,'action':'remove','index':''},follow_redirects=False)
    assert r.status_code==303
    with connect(path) as c:
        assert c.execute('SELECT series FROM books WHERE id=1').fetchone()['series'] is None
