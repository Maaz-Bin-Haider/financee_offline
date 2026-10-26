"""Batch tenant record existence checks, with the source screen's capabilities."""
from urllib.parse import urlencode
from django.db import connection
from spotlight.policy import DOCUMENTS, MASTERS, PAGES
from spotlight.queries import DOC_SQL
from .recorder import as_id


def record_links(request,records):
    grouped={};links={}
    for kind,action,raw in records:
        ident=as_id(raw)
        if ident and action!='delete':grouped.setdefault(kind,set()).add(ident)
    for kind,ids in grouped.items():
        target=DOCUMENTS.get(kind) or MASTERS.get(kind)
        if not target:
            page=PAGES.get(kind)
            if page and page.allowed(request):
                links.update({(kind,ident):page.path for ident in ids})
            continue
        if not target.allowed(request):continue
        if kind in MASTERS:
            table,key,clause=('parties','party_id','TRUE') if kind=='party' else ('items','item_id','TRUE')
        else:
            table,key,*_=DOC_SQL[kind];clause=DOC_SQL[kind][-1]
        # All identifiers/clauses come from the fixed Spotlight catalog.
        with connection.cursor() as cur:
            cur.execute(f'SELECT d.{key} FROM {table} d WHERE d.{key}=ANY(%s) AND ({clause})',[list(ids)])
            found=[row[0] for row in cur.fetchall()]
        parameter=kind if kind in MASTERS else 'open'
        links.update({(kind,ident):target.path+'?'+urlencode({parameter:ident}) for ident in found})
    return links
