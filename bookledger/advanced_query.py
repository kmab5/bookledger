"""Validated, parameterized advanced queries for BookLedger's dedicated frontend.

The syntax is intentionally declarative. No client-supplied SQL identifiers or
operators are interpolated. Saved views contain JSON filters, never SQL.
"""
from __future__ import annotations

import json
from typing import Any
from fastapi import HTTPException

BOOK_FIELDS = {
    'title': ('b.title', 'text'), 'subtitle': ('b.subtitle', 'text'),
    'authors': ('b.authors', 'text'), 'series': ('b.series', 'text'),
    'series_index': ('b.series_index', 'number'), 'publisher': ('b.publisher', 'text'),
    'language': ('b.language', 'text'), 'published': ('b.published', 'text'),
    'isbn': ("COALESCE(b.isbn13,b.isbn10)", 'text'),
    'pages': ('b.page_count', 'number'), 'words': ('b.word_count', 'number'),
    'reading_status': ("COALESCE(r.status,'unanswered')", 'text'),
    'rating': ('r.rating', 'number'), 'read_count': ('r.read_count', 'number'),
    'time_read': ('r.minutes_read', 'number'), 'current_page': ('r.current_page', 'number'),
    'started': ('r.started', 'date'), 'finished': ('r.finished', 'date'),
    'notes': ('r.notes', 'text'), 'hidden': ('b.hidden', 'bool'),
    'has_cover': ('(b.cover_path IS NOT NULL)', 'bool'),
    'needs_review': ('b.needs_review', 'bool'),
    'verified': ('b.manually_verified', 'bool'),
    'has_series': ("(NULLIF(TRIM(b.series),'') IS NOT NULL)", 'bool'),
    'has_isbn': ('(b.isbn13 IS NOT NULL OR b.isbn10 IS NOT NULL)', 'bool'),
    'has_duplicates': ('EXISTS(SELECT 1 FROM book_links l WHERE (l.book_id=b.id OR l.candidate_id=b.id) AND l.resolved=0)', 'bool'),
    'missing_file': ('EXISTS(SELECT 1 FROM files f WHERE f.book_id=b.id AND f.missing=1)', 'bool'),
    'file_count': ('(SELECT COUNT(*) FROM files f WHERE f.book_id=b.id)', 'number'),
    'file_size': ('(SELECT COALESCE(MAX(f.bytes),0) FROM files f WHERE f.book_id=b.id)', 'number'),
    'indexed': ('b.created_at', 'date'), 'updated': ('b.updated_at', 'date'),
    'category': ('EXISTS(SELECT 1 FROM book_categories bc JOIN categories cat ON cat.id=bc.category_id WHERE bc.book_id=b.id AND {test})', 'relation'),
    'folder': ("EXISTS(SELECT 1 FROM files f WHERE f.book_id=b.id AND {test})", 'folder'),
    'format': ('EXISTS(SELECT 1 FROM files f WHERE f.book_id=b.id AND {test})', 'relation'),
}
BOOK_SORT_FIELDS = {k:v[0] for k,v in BOOK_FIELDS.items() if v[1] not in ('relation','folder')}
BOOK_SORT_FIELDS['author'] = 'b.authors'

SERIES_FIELDS = {
    'name': ('s.name','text'), 'description': ('s.description','text'),
    'notes': ('s.notes','text'), 'book_count': ('s.book_count','number'),
    'finished_count': ('s.finished_count','number'), 'unread_count': ('s.unread_count','number'),
    'unordered_count': ('s.unordered_count','number'),
    'progress': ('s.progress','number'), 'updated': ('s.updated_at','date'),
    'has_cover': ('(s.cover_id IS NOT NULL)','bool'),
}

REVIEW_FIELDS = {**BOOK_FIELDS,
    'confidence': ('rv.confidence','number'), 'review_field': ('rv.field','text'),
    'suggestion': ('rv.suggested','text'), 'reason': ('rv.reason','text'),
}
REVIEW_SORT_FIELDS = {**BOOK_SORT_FIELDS,'confidence':'rv.confidence','review_field':'rv.field','suggestion':'rv.suggested'}

OPS = {
 'text': ['contains','not_contains','eq','neq','starts_with','ends_with','in','not_in','is_empty','is_not_empty'],
 'number': ['eq','neq','gt','gte','lt','lte','between','is_empty','is_not_empty'],
 'date': ['eq','neq','gt','gte','lt','lte','between','is_empty','is_not_empty'],
 'bool': ['is_true','is_false'],
 'relation': ['eq','neq','contains','not_contains','in','not_in','is_empty','is_not_empty'],
 'folder': ['eq','neq','contains','not_contains','is_empty','is_not_empty'],
}


def _bad(msg): raise HTTPException(422, msg)

def _scalar(field_type, value):
    if value is None: _bad('Rule value required')
    if field_type == 'number':
        try:
            if isinstance(value,bool): raise ValueError()
            return float(value)
        except (TypeError,ValueError): _bad('Expected a numeric value')
    val=str(value).strip()
    if len(val)>500: _bad('Filter value too long')
    return val


def _like(value):
    return str(value).replace('\\','\\\\').replace('%','\\%').replace('_','\\_')


def _predicate(rule, fields):
    if not isinstance(rule,dict): _bad('Invalid filter rule')
    name=rule.get('field');op=rule.get('op');value=rule.get('value')
    if name not in fields: _bad(f'Unsupported field: {name}')
    expr,kind=fields[name]
    if op not in OPS[kind]: _bad(f'Unsupported operator for {name}: {op}')
    if kind=='folder':
        # Normalizes Windows/Linux delimiters and respects path boundaries when exact.
        path="REPLACE(f.path,CHAR(92),'/')"; folder_expr=f"SUBSTR({path},1,LENGTH({path})-LENGTH(REPLACE({path},'/','')))" if False else f"SUBSTR({path},1,LENGTH({path})-LENGTH(TRIM({path},REPLACE({path},'/',''))))"
        # Actual file parent path, with no accidental match on similarly prefixed directories.
        folder_expr=f"SUBSTR({path},1,LENGTH({path})-INSTR(REVERSE_PLACEHOLDER,'/'))" if False else None
        # Use a path-relative prefix test without requiring a SQLite reverse() function.
        if op in ('is_empty','is_not_empty'):
            exists='EXISTS(SELECT 1 FROM files f WHERE f.book_id=b.id)'
            return (('NOT ' if op=='is_empty' else '')+exists),[]
        norm=_scalar('text',value).replace('\\','/').rstrip('/')
        if op in ('eq','neq'):
            include_children=bool(rule.get('subfolders',True))
            test=f"SUBSTR({path},1,LENGTH(?)+1)=?"
            args=[norm,norm+'/']
            if not include_children:
                test+=f" AND INSTR(SUBSTR({path},LENGTH(?)+2),'/')=0";args.append(norm)
        else:
            test=f"{path} LIKE ? ESCAPE '\\'";args=['%'+_like(norm)+'%']
        sql=expr.format(test=test)
        return ('NOT '+sql if op in ('neq','not_contains','not_in') else sql),args
    if kind=='relation':
        if name=='category':term='cat.name'
        else:term='f.extension'
        if op in ('is_empty','is_not_empty'):
            sql=expr.format(test='1=1')
            return ('NOT '+sql if op=='is_empty' else sql),[]
        if op in ('in','not_in'):
            if not isinstance(value,list) or not 1<=len(value)<=30:_bad('Expected 1–30 values')
            vals=[_scalar('text',x) for x in value]
            test=f'{term} COLLATE NOCASE IN ({",".join("?" for _ in vals)})';args=vals
        elif op in ('contains','not_contains'):
            test=f"{term} LIKE ? ESCAPE '\\' COLLATE NOCASE";args=['%'+_like(_scalar('text',value))+'%']
        else:
            test=f'{term} = ? COLLATE NOCASE';args=[_scalar('text',value)]
        sql=expr.format(test=test)
        return ('NOT '+sql if op in ('neq','not_contains','not_in') else sql),args
    if op=='is_true':return f'({expr})=1',[]
    if op=='is_false':return f'({expr})=0',[]
    if op=='is_empty':return f'({expr} IS NULL OR TRIM(CAST({expr} AS TEXT))=\'\')',[]
    if op=='is_not_empty':return f'({expr} IS NOT NULL AND TRIM(CAST({expr} AS TEXT))<>\'\')',[]
    if op in ('in','not_in'):
        if not isinstance(value,list) or not 1<=len(value)<=30:_bad('Expected 1–30 values')
        vals=[_scalar(kind,x) for x in value]
        return f'({expr} {"NOT IN" if op=="not_in" else "IN"} ({",".join("?" for _ in vals)}))',vals
    if op=='between':
        if not isinstance(value,list) or len(value)!=2:_bad('Between requires two bounds')
        return f'({expr} BETWEEN ? AND ?)',[_scalar(kind,v) for v in value]
    v=_scalar(kind,value)
    if op in ('contains','not_contains','starts_with','ends_with'):
        pattern=_like(v)
        if op in ('contains','not_contains'):pattern='%'+pattern+'%'
        elif op=='starts_with':pattern=pattern+'%'
        else:pattern='%'+pattern
        expr_sql=f"({expr} LIKE ? ESCAPE '\\' COLLATE NOCASE)"
        return (f'NOT {expr_sql}' if op=='not_contains' else expr_sql),[pattern]
    comp={'eq':'=','neq':'!=','gt':'>','gte':'>=','lt':'<','lte':'<='}[op]
    return f'({expr} {comp} ? {"COLLATE NOCASE" if kind=="text" else ""})',[v]


def compile_group(node,fields,depth=0,counter=None):
    if counter is None:counter=[0]
    if depth>3:_bad('Filter groups too deeply nested')
    if not node:return '1=1',[]
    if not isinstance(node,dict):_bad('Filter groups must be objects')
    mode=node.get('match','all')
    if mode not in ('all','any'):_bad('Group match must be all or any')
    rules=node.get('rules',[])
    if not isinstance(rules,list):_bad('Rules must be a list')
    clauses=[];args=[]
    for rule in rules:
        counter[0]+=1
        if counter[0]>30:_bad('Maximum 30 filter rules')
        if isinstance(rule,dict) and 'rules' in rule:sql,params=compile_group(rule,fields,depth+1,counter)
        else:sql,params=_predicate(rule,fields)
        clauses.append('('+sql+')');args.extend(params)
    if not clauses:return '1=1',[]
    return (' AND ' if mode=='all' else ' OR ').join(clauses),args


def _sorting(sorts,allowed,default):
    if not isinstance(sorts,list) or len(sorts)>4:_bad('Maximum four sorting criteria')
    chunks=[]
    for rule in sorts:
        if not isinstance(rule,dict) or rule.get('field') not in allowed:_bad('Invalid sort field')
        d=rule.get('direction','asc')
        if d not in ('asc','desc'):_bad('Invalid sorting direction')
        expr=allowed[rule['field']]
        chunks.append(f'({expr}) IS NULL ASC')
        chunks.append(f'{expr} COLLATE NOCASE {d.upper()}' if rule['field'] in ('title','subtitle','authors','author','series','publisher','language','name') else f'{expr} {d.upper()}')
    return ', '.join(chunks or [default])


def _payload(data,max_per_page=200):
    if not isinstance(data,dict):_bad('Invalid query')
    page=data.get('page',1);size=data.get('per_page',48)
    if type(page)!=int or page<1 or page>100000:_bad('Invalid page')
    if type(size)!=int or not 1<=size<=max_per_page:_bad(f'Page size must be 1–{max_per_page}')
    return page,size


def query_books(db, data, max_per_page=200, randomize=False):
    page,size=_payload(data,max_per_page)
    filters,vals=compile_group(data.get('filters'),BOOK_FIELDS)
    q=data.get('search','')
    if not isinstance(q,str) or len(q)>500:_bad('Invalid search')
    clauses=['('+filters+')'];args=list(vals)
    if q.strip():
        clauses.append('(b.title LIKE ? OR b.authors LIKE ? OR COALESCE(b.series,\'\') LIKE ? OR COALESCE(b.isbn13,\'\') LIKE ?)')
        args += ['%'+q.strip()+'%']*4
    visibility=data.get('visibility','visible')
    if visibility not in ('visible','hidden','all'):_bad('Invalid visibility')
    if visibility=='visible':clauses.append('b.hidden=0')
    if visibility=='hidden':clauses.append('b.hidden=1')
    base=' FROM books b LEFT JOIN reading r ON r.book_id=b.id WHERE '+' AND '.join(clauses)
    sort='RANDOM()' if randomize else _sorting(data.get('sort',[]),BOOK_SORT_FIELDS,'b.title COLLATE NOCASE ASC')
    total=db.execute('SELECT COUNT(*)'+base,args).fetchone()[0]
    offset=data.get('offset',(page-1)*size)
    if type(offset)!=int or offset<0:_bad('Invalid offset')
    rows=db.execute("SELECT b.*,COALESCE(r.status,'unanswered') reading_status,r.rating reading_rating,r.minutes_read reading_minutes"+base+' ORDER BY '+sort+',b.id ASC LIMIT ? OFFSET ?',args+[size,offset]).fetchall()
    return {'items':[dict(x) for x in rows],'total':total,'page':page,'per_page':size,'pages':max(1,(total+size-1)//size)}


SERIES_BASE = '''FROM (SELECT c.id,c.name,c.description,c.notes,c.updated_at,
 COUNT(b.id) book_count,
 SUM(CASE WHEN r.status='finished' THEN 1 ELSE 0 END) finished_count,
 SUM(CASE WHEN COALESCE(r.status,'unanswered')<>'finished' THEN 1 ELSE 0 END) unread_count,
 SUM(CASE WHEN b.id IS NOT NULL AND b.series_index IS NULL THEN 1 ELSE 0 END) unordered_count,
 CASE WHEN COUNT(b.id)>0 THEN 100.0*SUM(CASE WHEN r.status='finished' THEN 1 ELSE 0 END)/COUNT(b.id) ELSE 0 END progress,
 (SELECT id FROM books WHERE series=c.name AND cover_path IS NOT NULL ORDER BY series_index LIMIT 1) cover_id
 FROM series_catalog c LEFT JOIN books b ON b.series=c.name LEFT JOIN reading r ON r.book_id=b.id
 GROUP BY c.id) s'''


def query_series(db,data):
    page,size=_payload(data)
    where,args=compile_group(data.get('filters'),SERIES_FIELDS)
    search=data.get('search','')
    if not isinstance(search,str) or len(search)>500:_bad('Invalid search')
    if search.strip():where+=' AND s.name LIKE ?';args.append('%'+search.strip()+'%')
    base=' '+SERIES_BASE+' WHERE '+where
    order=_sorting(data.get('sort',[]),{k:v[0] for k,v in SERIES_FIELDS.items()},'s.name COLLATE NOCASE ASC')
    total=db.execute('SELECT COUNT(*)'+base,args).fetchone()[0]
    rows=db.execute('SELECT s.*'+base+' ORDER BY '+order+',s.id ASC LIMIT ? OFFSET ?',args+[size,(page-1)*size]).fetchall()
    return {'items':[dict(x) for x in rows],'total':total,'page':page,'per_page':size,'pages':max(1,(total+size-1)//size)}


def query_reviews(db,data):
    page,size=_payload(data)
    filters,args=compile_group(data.get('filters'),REVIEW_FIELDS)
    search=data.get('search','')
    if not isinstance(search,str) or len(search)>500:_bad('Invalid search')
    if search.strip():
        filters+=' AND (b.title LIKE ? OR rv.field LIKE ? OR rv.reason LIKE ?)'
        args.extend(['%'+search.strip()+'%']*3)
    base=' FROM review_queue rv JOIN books b ON b.id=rv.book_id LEFT JOIN reading r ON r.book_id=b.id WHERE rv.resolved=0 AND ('+filters+')'
    order=_sorting(data.get('sort',[]),REVIEW_SORT_FIELDS,'rv.confidence ASC')
    total=db.execute('SELECT COUNT(*)'+base,args).fetchone()[0]
    rows=db.execute('SELECT rv.*,b.title,b.authors,b.series'+base+' ORDER BY '+order+',rv.id LIMIT ? OFFSET ?',args+[size,(page-1)*size]).fetchall()
    return {'items':[dict(x) for x in rows],'total':total,'page':page,'per_page':size,'pages':max(1,(total+size-1)//size)}


def metadata():
    return {'books':{k:{'type':v[1],'operators':OPS[v[1]],'sortable':k in BOOK_SORT_FIELDS} for k,v in BOOK_FIELDS.items()},
            'series':{k:{'type':v[1],'operators':OPS[v[1]],'sortable':True} for k,v in SERIES_FIELDS.items()},
            'review':{k:{'type':v[1],'operators':OPS[v[1]],'sortable':k in REVIEW_SORT_FIELDS} for k,v in REVIEW_FIELDS.items()},
            'max_rules':30,'max_sort':4}
