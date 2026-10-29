"""Regression tests for safe nested filtering, cross-table fields, sorting and persisted views."""
from fastapi.testclient import TestClient
from bookledger.core import connect, now
from bookledger.webapp import create_app


def make_library(tmp_path):
    path=tmp_path/'db.sqlite3'
    with connect(path) as c:
        data=[('Alpha','["Ann"]','Saga',1,'D:/eBooks/Alpha.epub',500,'finished',5),
              ('Beta','["Bob"]','Saga',2,'D:/eBooks/Fantasy/Beta.epub',750,'reading',4),
              ('Gamma','["Ann"]',None,None,'D:/eBooks-other/Gamma.epub',900,'unanswered',None),
              ('Delta','["Cat"]',None,None,'D:/eBooks/Delta.pdf',400,'not_read',None)]
        for title,authors,series,idx,file,size,status,rating in data:
            c.execute('INSERT INTO books(title,authors,series,series_index,created_at,updated_at,page_count) VALUES(?,?,?,?,?,?,?)',(title,authors,series,idx,now(),now(),size))
            ident=c.execute('SELECT last_insert_rowid()').fetchone()[0]
            c.execute('INSERT INTO files(book_id,path,extension,bytes,modified_ns,fingerprint,last_seen) VALUES(?,?,?,?,?,?,?)',(ident,file,'.pdf' if file.endswith('.pdf') else '.epub',size*1024,1,'finger'+str(ident),now()))
            c.execute('INSERT INTO reading(book_id,status,rating,updated_at) VALUES(?,?,?,?)',(ident,status,rating,now()))
        c.execute('INSERT INTO series_catalog(name,updated_at) VALUES(?,?)',('Saga',now()))
        c.execute('INSERT INTO review_queue(book_id,field,suggested,confidence,reason) VALUES(?,?,?,?,?)',(2,'publisher','Some publisher',0.4,'guess'))
        c.commit()
    return TestClient(create_app(path))


def run(client,filters=None,sort=None,**kw):
    resp=client.post('/api/query/books',json={'filters':filters or {'match':'all','rules':[]},'sort':sort or [],**kw})
    assert resp.status_code==200,resp.text
    return resp.json()


def titles(response):return [book['title'] for book in response['items']]


def test_nested_boolean_sort_and_paging(tmp_path):
    c=make_library(tmp_path)
    group={'match':'all','rules':[
        {'match':'any','rules':[{'field':'authors','op':'contains','value':'Ann'},{'field':'reading_status','op':'eq','value':'reading'}]},
        {'field':'pages','op':'between','value':[500,950]}]}
    data=run(c,group,sort=[{'field':'pages','direction':'desc'}],per_page=1,page=1)
    assert data['total']==3 and titles(data)==['Gamma']
    assert titles(run(c,group,sort=[{'field':'pages','direction':'desc'}],per_page=1,page=2))==['Beta']
    assert titles(run(c,group,sort=[{'field':'pages','direction':'desc'}],per_page=1,page=3))==['Alpha']


def test_file_paths_formats_status_and_negation(tmp_path):
    c=make_library(tmp_path)
    assert titles(run(c,{'rules':[{'field':'folder','op':'eq','value':'D:/eBooks','subfolders':False}]},sort=[{'field':'title','direction':'asc'}]))==['Alpha','Delta']
    assert titles(run(c,{'rules':[{'field':'folder','op':'eq','value':'D:/eBooks','subfolders':True}]},sort=[{'field':'title','direction':'asc'}]))==['Alpha','Beta','Delta']
    assert titles(run(c,{'rules':[{'field':'format','op':'eq','value':'.pdf'}]}))==['Delta']
    assert titles(run(c,{'rules':[{'field':'reading_status','op':'in','value':['reading','finished']}]}))==['Alpha','Beta']
    assert titles(run(c,{'rules':[{'field':'title','op':'not_contains','value':'a'}]}))==[]  # all titles include a
    assert titles(run(c,{'rules':[{'field':'authors','op':'contains','value':'Ann'}]},visibility='hidden'))==[]


def test_series_review_and_saved_views(tmp_path):
    c=make_library(tmp_path)
    payload={'filters':{'rules':[{'field':'book_count','op':'gte','value':2},{'field':'progress','op':'gt','value':0}]},'sort':[{'field':'progress','direction':'desc'}]}
    res=c.post('/api/query/series',json=payload)
    assert res.status_code==200 and res.json()['items'][0]['name']=='Saga'
    res=c.post('/api/query/reviews',json={'filters':{'rules':[{'field':'confidence','op':'lt','value':0.5}]},'per_page':10})
    assert res.status_code==200 and res.json()['total']==1
    res=c.post('/api/query/views',json={'scope':'books','name':'Readable','query':{'filters':{'rules':[{'field':'reading_status','op':'eq','value':'finished'}]},'sort':[{'field':'rating','direction':'desc'}]}})
    assert res.status_code==200,res.text
    view_id=res.json()['id']
    assert len(c.get('/api/query/views?scope=books').json()['items'])==1
    assert c.delete('/api/query/views/'+str(view_id)).status_code==200
    assert not c.get('/api/query/views?scope=books').json()['items']


def test_invalid_filters_never_execute_sql(tmp_path):
    c=make_library(tmp_path)
    for field,op,value in [('b.title; DROP TABLE books','eq','x'),('pages','contains','4'),('title','eq','x'*501)]:
        assert c.post('/api/query/books',json={'filters':{'rules':[{'field':field,'op':op,'value':value}]}}).status_code==422
    assert c.post('/api/query/books',json={'filters':{'rules':[{'field':'pages','op':'between','value':[1]}]}}).status_code==422
    assert c.post('/api/query/books',json={'sort':[{'field':'title;--','direction':'desc'}]}).status_code==422
    assert c.post('/api/query/books',json={'filters':{'rules':[{'match':'invalid','rules':[]}]}}).status_code==422
    assert c.post('/api/query/books',json={'filters':{'rules':[{'field':'title','op':'eq','value':'x'}]*31}}).status_code==422
    assert c.get('/api/books').json()['total']==4


def test_quick_batch_and_format(tmp_path):
    c=make_library(tmp_path)
    data=c.post('/api/query/quick-sort',json={'filters':{'rules':[{'field':'series','op':'eq','value':'Saga'}]},'sort':[{'field':'series_index','direction':'desc'}],'per_page':20}).json()
    assert titles(data)==['Beta','Alpha']
    assert c.get('/api/query/metadata').json()['books']['file_size']['sortable']


def test_advanced_export_and_series_members_saved_view(tmp_path):
    c=make_library(tmp_path)
    filtered={'filters':{'rules':[{'field':'series','op':'eq','value':'Saga'}]},
              'sort':[{'field':'series_index','direction':'desc'}],
              'visibility':'all'}
    res=c.post('/api/exports/custom',json={'fields':['title','series','status'],'advanced_query':filtered})
    assert res.status_code==200,res.text
    assert 'Beta,Saga,reading' in res.text
    assert 'Alpha,Saga,finished' in res.text
    assert 'Gamma' not in res.text and 'Delta' not in res.text
    assert res.text.index('Beta,Saga,reading')<res.text.index('Alpha,Saga,finished')
    view=c.post('/api/query/views',json={'scope':'series_members','name':'reading only','query':filtered})
    assert view.status_code==200,view.text
    assert len(c.get('/api/query/views?scope=series_members').json()['items'])==1
    assert c.post('/api/query/views',json={'scope':'exports','name':'my export','query':filtered}).status_code==200
    assert c.get('/api/query/metadata').json()['choices']['folder']
