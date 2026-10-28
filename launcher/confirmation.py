"""Explicit, single-use local consent for replacing the active business."""
from .storage import LauncherError
class RestoreConsent:
    def __init__(self,digest):self.digest=digest;self.used=False
    def confirm(self,text):
        if self.used:raise LauncherError('This restore confirmation was already used. Inspect and confirm the ZIP again.')
        if text!='RESTORE':raise LauncherError('Type RESTORE exactly to confirm replacing the active business.')
        self.used=True;return self.digest
