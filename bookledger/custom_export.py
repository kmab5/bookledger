"""Custom CSV exports. No claims of undocumented service-specific compatibility."""
import csv, io, json
from .core import jsonarr
FIELDS={
 'title':'title','subtitle':'subtitle','author':'author','authors':'authors','isbn10':'isbn10','isbn13':'isbn13','publisher':'publisher','published':'published','language':'language','description':'description','subjects':'subjects','series':'series','series_index':'series_index','page_count':'page_count','page_count_kind':'page_count_kind','cover_url':'cover_url','status':'status','started':'started','finished':'finished','minutes_read':'minutes_read','rating':'rating','read_count':'read_count','notes':'notes','categories':'categories','file_paths':'file_paths','formats':'formats','added':'added','confidence':'confidence'}
TEMPLATES={
 'full':list(FIELDS),
 'reading':['title','author','isbn13','status','started','finished','minutes_read','rating','read_count','notes'],
 'catalog':['title','authors','isbn13','isbn10','publisher','published','language','series','series_index','categories','formats'],
 'bookmory-reference':['title','author','isbn13','status','started','finished','rating','notes','minutes_read'],
 'hardcover-reference':['title','author','isbn13','status','started','finished','rating','notes']}
def export_custom(db, fields, status='',category='', series='', search=''):
    fields=[f for f in fields if f in FIELDS]
    if not fields:raise ValueError('Select at least one column')
    query='SELECT b.*,r.status,r.started,r.finished,r.minutes_read,r.rating,r.read_count,r.notes FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE 1=1'
    args=[]
    if status:query+=' AND r.status=?';args.append(status)
    if series:query+=' AND b.series=?';args.append(series)
    if search:query+=' AND (b.title LIKE ? OR b.authors LIKE ?)';args.extend(['%'+search+'%']*2)
    if category:
        query+=' AND EXISTS(SELECT 1 FROM book_categories bc JOIN categories c ON c.id=bc.category_id WHERE bc.book_id=b.id AND c.name=?)';args.append(category)
    query+=' ORDER BY b.title COLLATE NOCASE'
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fieldnames=fields);writer.writeheader()
    for row in db.execute(query,args):
        item=dict(row);authors=jsonarr(item.get('authors'));item['authors']=', '.join(authors);item['author']=authors[0] if authors else ''
        item['subjects']=', '.join(jsonarr(item.get('subjects')))
        item['added']=item.get('created_at','')
        item['confidence']=item.get('confidence_json','')
        item['categories']=', '.join(r[0] for r in db.execute('SELECT c.name FROM book_categories bc JOIN categories c ON c.id=bc.category_id WHERE bc.book_id=? ORDER BY c.name',(item['id'],)))
        files=db.execute('SELECT path,extension FROM files WHERE book_id=?',(item['id'],)).fetchall()
        item['file_paths']=' | '.join(r[0] for r in files);item['formats']=', '.join(sorted({r[1] for r in files}))
        writer.writerow({field:item.get(field,'') if item.get(field) is not None else '' for field in fields})
    return output.getvalue().encode('utf-8-sig')
