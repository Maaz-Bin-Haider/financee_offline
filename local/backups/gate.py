"""Drain whole requests, including session/activity writes and streamed media."""
from contextlib import ExitStack
from pathlib import Path
from django.conf import settings
from django.http import JsonResponse
from .files import lock,read,Busy

class MaintenanceMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        root=getattr(settings,'OFFLINE_CUSTOMER_ROOT','')
        if not root:return self.get_response(request)
        journal=read(Path(root)/'Config/restore-journal.json',{})
        pending=journal.get('stage') not in (None,'committed','rolled_back','failed_before_switch')
        configured=read(Path(root)/'Config/active.json',{})
        stale=getattr(settings,'OFFLINE_GENERATION',configured.get('generation'))!=configured.get('generation')
        if (pending or stale) and request.path!='/health/':return self.unavailable('Recovery is being verified. Please wait or reopen Financee maintenance.')
        stack=ExitStack()
        try:
            folder=Path(root)/'Config/maintenance'
            with lock(folder/'intent.lock',exclusive=False):
                stack.enter_context(lock(folder/'gate.lock',exclusive=False))
        except Busy:
            stack.close();return self.unavailable('A local backup or recovery is pausing requests. Please retry shortly.')
        try:
            response=self.get_response(request)
            if response.streaming:
                original=response.streaming_content
                def stream():
                    try:yield from original
                    finally:stack.close()
                response.streaming_content=stream()
                response._resource_closers.append(stack.close)
            else:stack.close()
            return response
        except BaseException:stack.close();raise
    @staticmethod
    def unavailable(message):
        response=JsonResponse({'status':'maintenance','message':message},status=503)
        response['Retry-After']='5';response['Cache-Control']='no-store';return response
