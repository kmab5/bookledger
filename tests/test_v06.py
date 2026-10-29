import io, zipfile
from fastapi.testclient import TestClient
from bookledger.core import connect, scan, cache_cover
from bookledger.legacy_webapp import create_app

def test_hidden_books_filter_and_toggle(tmp_path):
    with connect(tmp_path/'db.sqlite') as db:
        db.execute("INSERT INTO books(title,authors,created_at,updated_at) VALUES('Hidden title','[]','now','now')")
        db.commit()
    app=create_app(tmp_path/'db.sqlite'); client=TestClient(app)
    assert 'Hidden title' in client.get('/').text
    r=client.post('/book/1/visibility',data={'csrf':app.state.csrf,'hidden':'1'},follow_redirects=False)
    assert r.status_code==303
    assert 'Hidden title' not in client.get('/').text
    assert 'Hidden title' in client.get('/?visibility=hidden').text
    assert 'Hidden title' in client.get('/?visibility=all').text
    assert client.post('/book/1/visibility',data={'csrf':app.state.csrf,'hidden':'bad'}).status_code==422
    assert client.post('/book/1/visibility',data={'csrf':'bad','hidden':'0'}).status_code==403
    assert client.post('/book/1/visibility',data={'csrf':app.state.csrf,'hidden':'0'},follow_redirects=False).status_code==303
    assert 'Hidden title' in client.get('/').text

def test_corrupted_cover_does_not_abort_batch(tmp_path,monkeypatch):
    library=tmp_path/'library'; library.mkdir()
    for name in ('Bad','Good'):
        with zipfile.ZipFile(library/f'{name}.epub','w') as z:
            z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="package.opf"/></rootfiles></container>')
            z.writestr('package.opf',f'<package><metadata><title>{name}</title></metadata><manifest><item id="cover" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/></manifest></package>')
            z.writestr('cover.jpg',b'badimage')
    import bookledger.core as core
    original=core.cache_cover
    def fail_for_bad(db,book_id,path=None,**kwargs):
        if path and path.stem=='Bad':
            import zlib
            raise zlib.error('Error -3 while decompressing data: invalid distance too far back')
        return original(db,book_id,path=path,**kwargs)
    monkeypatch.setattr(core,'cache_cover',fail_for_bad)
    with connect(tmp_path/'db.sqlite') as db:
        result=scan(db,library,online=False)
        assert result['new']==2
        assert db.execute('SELECT count(*) FROM books').fetchone()[0]==2

def test_scan_log_has_autoscroll(tmp_path):
    app=create_app(tmp_path/'db.sqlite')
    html=TestClient(app).get('/scan').text
    assert 'log.scrollTop=log.scrollHeight' in html
    assert 'role="log"' in html
