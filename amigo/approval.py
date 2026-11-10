"""One-use approvals bound to a concrete, freshly validated operation plan.

No model tool can grant approvals. Grants exist only in memory and are consumed
before execution; a restart or a changed plan requires a new user decision.
"""
import hashlib
import json
import secrets
import threading
from .policy import Denied

class ApprovalRequired(RuntimeError):
    def __init__(self,token,plan):
        super().__init__('É necessária uma decisão sobre a operação preparada.')
        self.token=token;self.plan=plan

class ApprovalGate:
    def __init__(self):self.lock=threading.Lock();self.pending=None;self.granted=None
    @staticmethod
    def digest(plan):return hashlib.sha256(json.dumps(plan,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    def require(self,plan):
        fingerprint=self.digest(plan)
        with self.lock:
            if self.granted==fingerprint:
                self.granted=None;return
            self.granted=None
            token=secrets.token_urlsafe(24);self.pending=(token,fingerprint)
        raise ApprovalRequired(token,plan)
    def decide(self,token,allow):
        with self.lock:
            if not self.pending or not secrets.compare_digest(token,self.pending[0]):raise Denied('A confirmação expirou ou pertence a outra operação.')
            self.granted=self.pending[1] if allow else None;self.pending=None
    def clear(self):
        with self.lock:self.pending=None;self.granted=None
