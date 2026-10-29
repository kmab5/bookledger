import io,zipfile
from pathlib import Path
from PIL import Image
from fastapi.testclient import TestClient
from bookledger.core import connect,scan
from bookledger.legacy_webapp import create_app
from bookledger.custom_export import export_custom

def test_cover_folder_export_and_routes(tmp_path):
    root=tmp_path/'Library';folder=root/'Science Fiction';folder.mkdir(parents=True)
    img=io.BytesIO();Image.new('RGB',(40,60),'purple').save(img,format='JPEG')
    p=folder/'Nebula - Writer.epub'
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="OPS/package.opf"/></rootfiles></container>')
        z.writestr('OPS/package.opf','<package><metadata><title>Nebula</title><creator>Writer</creator></metadata><manifest><item id="cover" href="cover.jpg" media-type="image/jpeg" properties="cover-image"/></manifest></package>')
        z.writestr('OPS/cover.jpg',img.getvalue())
    dbfile=tmp_path/'data.db'
    with connect(dbfile) as db:
        assert scan(db,root,online=False)['new']==1
        b=db.execute('select * from books').fetchone()
        assert b['cover_path'] and Path(b['cover_path']).exists()
        cat=db.execute('select name,confidence from categories join book_categories on categories.id=book_categories.category_id').fetchall()
        assert ('Science Fiction',.48) in [tuple(x) for x in cat]
        csv=export_custom(db,['title','categories','file_paths'])
        assert b'Science Fiction' in csv
    c=TestClient(create_app(dbfile))
    assert c.get('/').status_code==200
    assert b'/cover/1' in c.get('/').content
    assert c.get('/cover/1').headers['content-type']=='image/jpeg'
    assert c.get('/favicon.svg').status_code==200
    assert c.get('/exports').status_code==200
    assert c.get('/enrich').status_code==200
    assert c.get('/exports/preset/storygraph').status_code==200
    assert c.get('/exports/preset/json').status_code==200
