import os,uuid
from datetime import datetime,timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseForbidden
from django.shortcuts import render,redirect
from django.views.decorators.http import require_http_methods
from .engine import Engine
from .files import atomic,read

@staff_member_required
@require_http_methods(['GET','POST'])
def backups(request):
    if not request.user.is_superuser:return HttpResponseForbidden('Local owner access required.')
    engine=Engine()
    if request.method=='POST':
        atomic(engine.control/'backup-request.json',{'id':uuid.uuid4().hex,'requested_utc':datetime.now(timezone.utc).isoformat()})
        return redirect('local_backups')
    return render(request,'local/backups.html',{'status':engine.status(),'pending':bool(read(engine.control/'backup-request.json')),'backup_folder':os.environ.get('OFFLINE_BACKUP_DISPLAY_DIR',str(engine.folder))})
