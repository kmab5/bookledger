from fastapi.testclient import TestClient
from bookledger.webapp import create_app
from bookledger.core import connect

def test_settings_and_nested_folder_filter(tmp_path):
    app=create_app(tmp_path/'library.sqlite3')
    with TestClient(app) as client:
        defaults=client.get('/api/settings').json()
        assert defaults['values']['library.include_subfolders'] is True
        assert client.patch('/api/settings',json={'library.include_subfolders':False,'library.page_size':12}).status_code==200
        assert client.patch('/api/settings',json={'library.page_size':-1}).status_code==422
        assert client.patch('/api/settings',json={'unknown.key':'no'}).status_code==422
        with connect(tmp_path/'library.sqlite3') as db:
            # Use real schema, preserving existing migration behavior.
            names={row['name'] for row in db.execute('PRAGMA table_info(books)')}
            assert 'title' in names
        assert client.get('/api/books?folder=/a/b').status_code==200
    # Settings survive application restart
    with TestClient(create_app(tmp_path/'library.sqlite3')) as client:
        assert client.get('/api/settings').json()['values']['library.include_subfolders'] is False
        assert client.post('/api/settings/reset').json()['values']['library.include_subfolders'] is True

def test_exact_vs_nested_folder_integration(tmp_path):
    path=tmp_path/'folder.sqlite'
    with connect(path) as c:
        for n,p in [('Direct','D:/eBooks/Direct.epub'),('Nested','D:/eBooks/Fiction/Nested.epub'),('Other','D:/other/Other.epub')]:
            c.execute("INSERT INTO books(title,authors,created_at,updated_at) VALUES(?,'[]','now','now')",(n,))
            book_id=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            cols={r['name'] for r in c.execute('PRAGMA table_info(files)')}
            # File rows require scanner fields; insert using schema defaults.
            c.execute('INSERT INTO files(book_id,path,extension,bytes,modified_ns,fingerprint,last_seen) VALUES(?,?,?,?,?,?,?)',(book_id,p,'.epub',100,1,'f'+str(book_id),'now'))
        c.commit()
    with TestClient(create_app(path)) as client:
        def titles():return {x['title'] for x in client.get('/api/books?folder=D%3A%2FeBooks').json()['items']}
        assert titles()=={'Direct','Nested'}
        client.patch('/api/settings',json={'library.include_subfolders':False})
        assert titles()=={'Direct'}
        assert {x['title'] for x in client.get('/api/books?folder=D%3A%2FeBooks&include_subfolders=true').json()['items']}=={'Direct','Nested'}
