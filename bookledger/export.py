"""Portable exports; export does not change user data or source books."""
import csv, json
from pathlib import Path
from .core import now, jsonarr

HEADERS=['Book Id','Title','Author','Author l-f','Additional Authors','ISBN','ISBN13','My Rating','Average Rating','Publisher','Binding','Number of Pages','Year Published','Original Publication Year','Date Read','Date Added','Bookshelves','Bookshelves with positions','Exclusive Shelf','My Review','Spoiler','Private Notes','Read Count','Owned Copies']
STATUS={'finished':'read','rereading':'currently-reading','reading':'currently-reading','on_hold':'currently-reading','abandoned':'did-not-finish','want_to_read':'to-read','not_read':'to-read','unanswered':'to-read'}
def export_csv(db,dest):
    rows=db.execute('SELECT b.*,r.status,r.started,r.finished,r.minutes_read,r.rating,r.notes,r.read_count,r.updated_at AS reading_updated FROM books b LEFT JOIN reading r ON r.book_id=b.id ORDER BY b.title').fetchall()
    with open(dest,'w',newline='',encoding='utf-8-sig') as file:
        writer=csv.DictWriter(file,fieldnames=HEADERS);writer.writeheader()
        for b in rows:
            authors=jsonarr(b['authors']); first=authors[0] if authors else ''
            categories=[x[0] for x in db.execute('SELECT c.name FROM categories c JOIN book_categories bc ON bc.category_id=c.id WHERE bc.book_id=? ORDER BY c.name',(b['id'],))]
            shelf=STATUS.get(b['status'] or 'unanswered','to-read')
            writer.writerow({'Title':b['title'],'Author':first,'Additional Authors':', '.join(authors[1:]),'ISBN':b['isbn10'] or '', 'ISBN13':b['isbn13'] or '',
                'My Rating':int(round(b['rating'])) if b['rating'] is not None else 0,'Publisher':b['publisher'] or '',
                'Binding':next((x[0].lstrip('.') for x in db.execute('SELECT extension FROM files WHERE book_id=? ORDER BY id LIMIT 1',(b['id'],))),''),
                'Number of Pages':b['page_count'] or '', 'Year Published':(b['published'] or '')[:4], 'Original Publication Year':(b['published'] or '')[:4],
                'Date Read':(b['finished'] or '').replace('-','/'), 'Date Added':b['created_at'][:10].replace('-','/'),
                'Exclusive Shelf':shelf,'Bookshelves':', '.join(x.lower().replace(' ','-') for x in categories),'My Review':b['notes'] or '',
                'Private Notes':f"Started: {b['started'] or 'unknown'}; Minutes read: {b['minutes_read'] or 0}" if b['started'] or b['minutes_read'] else '',
                'Read Count':max(b['read_count'] or 0,1 if shelf=='read' else 0),'Owned Copies':1 if db.execute('SELECT 1 FROM files WHERE book_id=? LIMIT 1',(b['id'],)).fetchone() else 0})
    return len(rows)

def export_json(db,dest):
    result={'schema':'bookledger-1','exported_at':now(),'books':[],'categories':[dict(x) for x in db.execute('SELECT * FROM categories')],'reading_sessions':[dict(x) for x in db.execute('SELECT * FROM reading_sessions')]}
    for book in db.execute('SELECT * FROM books ORDER BY id').fetchall():
        item=dict(book)
        for key in ('authors','subjects','metadata_json','provenance_json','confidence_json'): item[key]=json.loads(item[key])
        item['files']=[dict(x) for x in db.execute('SELECT * FROM files WHERE book_id=?',(book['id'],))]
        item['reading']=dict(db.execute('SELECT * FROM reading WHERE book_id=?',(book['id'],)).fetchone() or {})
        item['categories']=[dict(x) for x in db.execute('SELECT c.name,bc.confidence,bc.source,bc.confirmed FROM categories c JOIN book_categories bc ON c.id=bc.category_id WHERE bc.book_id=?',(book['id'],))]
        item['review_queue']=[dict(x) for x in db.execute('SELECT * FROM review_queue WHERE book_id=?',(book['id'],))]
        result['books'].append(item)
    Path(dest).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');return len(result['books'])
