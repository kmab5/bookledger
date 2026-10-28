import json, zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from bookledger.core import connect, scan, parse_name
from bookledger.export import export_csv,export_json
from bookledger.webapp import create_app
from fastapi.testclient import TestClient

def epub_file(path):
    opf='''<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>The Test Book</dc:title><dc:creator>Jane Writer</dc:creator><dc:language>en</dc:language><dc:subject>Fantasy</dc:subject><dc:identifier>9780000000002</dc:identifier><meta name="calibre:series" content="Examples"/><meta name="calibre:series_index" content="2"/></metadata><manifest><item id="p1" href="text.xhtml" media-type="application/xhtml+xml"/></manifest></package>'''
    container='''<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>'''
    with zipfile.ZipFile(path,'w') as f:
        f.writestr('META-INF/container.xml',container)
        f.writestr('OEBPS/content.opf',opf)
        f.writestr('OEBPS/text.xhtml','<html xmlns="http://www.w3.org/1999/xhtml"><body>Some example words here</body></html>')

def test_scan_and_exports(tmp_path):
    folder=tmp_path/'books';folder.mkdir();epub_file(folder/'Unknown.epub')
    db=connect(tmp_path/'db.sqlite3')
    first=scan(db,folder,online=False)
    assert first['new']==1 and first['errors']==0
    b=db.execute('SELECT * FROM books').fetchone()
    assert b['title']=='The Test Book' and b['series']=='Examples' and b['series_index']==2
    assert b['word_count']==4
    assert scan(db,folder,online=False)['unchanged']==1
    json_path=tmp_path/'backup.json';csv_path=tmp_path/'storygraph.csv'
    assert export_json(db,json_path)==1
    assert export_csv(db,csv_path)==1
    assert 'The Test Book' in csv_path.read_text(encoding='utf-8-sig')
    assert json.loads(json_path.read_text())['books'][0]['files'][0]['path'].endswith('.epub')
    (folder/'Unknown.epub').unlink()
    scan(db,folder,online=False)
    assert db.execute('SELECT missing FROM files').fetchone()[0]==1
    db.close()

def test_filename():
    assert parse_name(Path('Example Series - 03 - The Last Book.epub'))['series_index']==3
    assert parse_name(Path('Alpha - Zoe Smith.pdf'))['authors']==['Zoe Smith']

def test_dashboard_and_reading(tmp_path):
    folder=tmp_path/'books';folder.mkdir();epub_file(folder/'Unknown.epub')
    db_path=tmp_path/'library.db'
    with connect(db_path) as db:scan(db,folder,online=False)
    app=create_app(db_path);client=TestClient(app)
    assert client.get('/').status_code==200
    assert 'The Test Book' in client.get('/').text
    assert client.get('/reading').status_code==200
    assert client.get('/review').status_code==200
    response=client.post('/book/1/reading',data={'csrf':app.state.csrf,'status':'finished','started':'2026-01-01','finished':'2026-01-09','minutes_read':'150','rating':'4.5','notes':'Nice'})
    assert response.status_code==200
    with connect(db_path) as db:
        row=db.execute('SELECT * FROM reading WHERE book_id=1').fetchone()
        assert row['status']=='finished' and row['minutes_read']==150 and row['finished']=='2026-01-09'
    assert client.post('/book/1/reading',data={'csrf':'bogus','status':'reading'},follow_redirects=False).status_code==403

def test_catalog_categories_and_review(tmp_path):
    folder=tmp_path/'books';folder.mkdir();epub_file(folder/'Unknown.epub')
    db_path=tmp_path/'library.db'
    with connect(db_path) as db:
        scan(db,folder,online=False)
        assert db.execute("SELECT name FROM categories").fetchone()[0]=='Fantasy'
    app=create_app(db_path);client=TestClient(app)
    assert client.post('/book/1/category',data={'csrf':app.state.csrf,'category':'Favorites'}).status_code==200
    with connect(db_path) as db:
        assert db.execute("SELECT 1 FROM categories WHERE name='Favorites'").fetchone()
    assert 'Favorites' in client.get('/?category=Favorites').text
    assert client.post('/reading/quick/1',data={'csrf':app.state.csrf,'status':'abandoned'}).status_code==200
    with connect(db_path) as db:
        assert db.execute('SELECT status FROM reading').fetchone()[0]=='abandoned'
