"""SPA-focused smoke tests. Legacy HTML tests live under the legacy renderer."""
from fastapi.testclient import TestClient
from bookledger.webapp import create_app
from bookledger.core import connect, now


def test_new_static_frontend_is_shipped(tmp_path):
    with connect(tmp_path / 'books.db'):
        pass
    client = TestClient(create_app(tmp_path / 'books.db'))
    assert client.get('/').status_code == 200
    assert 'src="/main.js"' in client.get('/').text
    js = client.get('/main.js')
    css = client.get('/style.css')
    assert js.status_code == 200 and css.status_code == 200
    assert 'nav-group' in js.text
    assert 'query-launch' in client.get('/advanced.js').text
    assert 'adv-group' in client.get('/advanced.js').text
    assert 'reading-tabs' in js.text
    assert 'series-controls' in js.text
    assert 'quick-progress' in js.text
    assert 'prefers-reduced-motion' in css.text
    assert '#b24bff' in css.text.lower()


def test_spa_deep_links_and_json_api_still_work(tmp_path):
    path = tmp_path / 'books.db'
    with connect(path) as db:
        db.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)', ('Read Me', '["Writer"]', now(), now()))
        db.commit()
    client = TestClient(create_app(path))
    for route in ('/series', '/reading', '/quick-sort', '/stats', '/scan', '/enrich', '/exports', '/settings', '/book/1'):
        assert client.get(route).status_code == 200
    assert client.get('/api/books').json()['items'][0]['title'] == 'Read Me'
    assert client.patch('/api/books/1', json={'status':'finished'}).status_code == 200
    assert client.get('/api/books/1').json()['reading']['status'] == 'finished'
