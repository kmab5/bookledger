import re
import time
from pathlib import Path
from fastapi.testclient import TestClient
from bookledger.core import connect,scan
from bookledger.webapp import create_app

def test_progress_events(tmp_path):
    library=tmp_path/'library';library.mkdir();(library/'A Novel.txt').write_text('book')
    events=[]
    with connect(tmp_path/'test.sqlite') as con:
        result=scan(con,library,online=False,progress=events.append)
    assert result['new']==1
    assert any(x['event']=='file_start' for x in events)
    assert any(x['event']=='complete' for x in events)

def test_website_scan(tmp_path):
    library=tmp_path/'books';library.mkdir();(library/'Example.txt').write_text('example')
    app=create_app(tmp_path/'app.sqlite')
    client=TestClient(app)
    page=client.get('/scan');assert page.status_code==200
    token=re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
    response=client.post('/scan',data={'csrf':token,'folder':str(library)},follow_redirects=False)
    assert response.status_code==303
    for _ in range(80):
        status=client.get('/scan/status').json()
        if status['status']!='running':break
        time.sleep(.05)
    assert status['status']=='completed',status
    assert status['counts']['new']==1
    assert client.post('/scan',data={'csrf':token,'folder':str(tmp_path/'nonexistent')}).status_code==422
