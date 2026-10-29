from fastapi.testclient import TestClient
from bookledger.core import connect
from bookledger.webapp import create_app

def test_folder_filter_and_book_paths(tmp_path):
    db=tmp_path/'library.sqlite3'
    app=create_app(db)
    with connect(db) as con:
        now='2026-10-29T00:00:00'
        # Look up relevant required columns to stay compatible with the schema.
        for name in ('Alpha','Beta'):
            con.execute('INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,?,?,?)',(name,'[]',now,now))
        a,b=[x[0] for x in con.execute('SELECT id FROM books ORDER BY id')]
        con.execute('INSERT INTO files(book_id,path,extension,bytes,modified_ns,fingerprint,last_seen,missing) VALUES(?,?,?,?,0,?,?,0)',(a,'D:/eBooks/Fantasy/Epic/alpha.epub','.epub',100,'test','now'))
        con.execute('INSERT INTO files(book_id,path,extension,bytes,modified_ns,fingerprint,last_seen,missing) VALUES(?,?,?,?,0,?,?,0)',(b,'D:/eBooks/History/beta.pdf','.pdf',200,'test','now'))
        con.commit()
    client=TestClient(app)
    options=client.get('/api/options').json()
    assert 'D:/eBooks/Fantasy/Epic' in options['folders']
    assert client.get('/api/books',params={'folder':'D:/eBooks/Fantasy'}).json()['total']==1
    assert client.get('/api/books',params={'folder':'D:/eBooks/History'}).json()['total']==1
    assert client.get('/api/books',params={'folder':'D:/eBooks/Fant'}).json()['total']==0
    assert client.get('/api/books',params={'folder':'D:/eBooks'}).json()['total']==2
    assert client.get(f'/api/books/{a}').json()['files'][0]['path']=='D:/eBooks/Fantasy/Epic/alpha.epub'
