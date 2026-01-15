# xo_ws.py
import asyncio
import json
import uuid
import aiohttp
from contextlib import asynccontextmanager

class XoWsClient:
    def __init__(self, url, username=None, password=None, token=None, timeout=30, verify_ssl=True, max_msg_size=16 * 1024 * 1024):
        # Normalize to ws:// or wss:// as needed
        base = url.rstrip("/")
        if base.startswith("ws://") or base.startswith("wss://"):
            ws_base = base
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://"):]
        elif base.startswith("https://"):
            ws_base = "wss://" + base[len("https://"):]
        else:
            # no scheme provided → assume ws://
            ws_base = "ws://" + base

        # XO listens on /api/
        self.url = ws_base + "/api/"
        self.username = username
        self.password = password
        self.token = token
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.max_msg_size = max_msg_size
        self._ws = None
        self._session = None
        self._pending = {}

    @asynccontextmanager
    async def connect(self):
        # if verify_ssl is False, pass ssl=False to ws_connect
        import ssl as _ssl
        ssl_ctx = None
        if self.url.startswith("wss://") and not self.verify_ssl:
            ssl_ctx = False  # aiohttp treats False as "don’t verify"

        self._session = aiohttp.ClientSession()
        async with self._session.ws_connect(self.url, heartbeat=20, ssl=ssl_ctx,max_msg_size=self.max_msg_size) as ws:
            self._ws = ws
            # auth…
            if self.token:
                try:
                    await self.call("session.signInWithToken", {"token": self.token})
                except Exception:
                    await self.call("session.signIn", {"token": self.token})
            elif self.username and self.password:
                await self.call("session.signIn", {"username": self.username, "password": self.password})
            else:
                raise RuntimeError("Provide either token or username/password for XO auth.")
            yield self
        await self._session.close()
        self._ws = None
        self._session = None


    async def _send(self, method, params):
        req_id = str(uuid.uuid4())
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": req_id}
        await self._ws.send_str(json.dumps(msg))
        while True:
            msg = await self._ws.receive(timeout=self.timeout)
            if msg.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data.get("id") == req_id:
                    if "error" in data:
                        e = data["error"]
                        raise RuntimeError(f"XO error in {method}: {e.get('message')} (code {e.get('code')})")
                    return data.get("result")
            elif msg.type == aiohttp.WSMsgType.CLOSED:
                raise RuntimeError(f"WebSocket CLOSED while waiting for {method} reply (possibly wrong scheme or path: {self.url})")
            elif msg.type == aiohttp.WSMsgType.ERROR:
                raise RuntimeError(f"WebSocket ERROR while waiting for {method} reply: {msg.data!r}")

    async def call(self, method, params=None):
        return await self._send(method, params)

    # Convenience helpers mirroring your cli-based functions
    async def get_all_objects(self, filter=None):
        params = {"filter": filter} if filter else None
        return await self.call("xo.getAllObjects", params)


    async def vm_create(self, **kwargs):
        # returns VM xo-id (string or dict depending on XO; normalize to id)
        res = await self.call("vm.create", kwargs)
        if isinstance(res, str):
            return res
        if isinstance(res, dict):
            return res.get("id") or res.get("vm") or res.get("result") or res.get("data")
        return None

    async def vm_set(self, vm_id, **kwargs):
        return await self.call("vm.set", {"id": vm_id, **kwargs})

    async def vm_start(self, vm_id):
        return await self.call("vm.start", {"id": vm_id})

    async def vm_stop(self, vm_id):
        return await self.call("vm.stop", {"id": vm_id})

    async def vm_delete(self, vm_id, force=False):
        return await self.call("vm.delete", {"id": vm_id, "force": bool(force)})

    async def vdi_set(self, vdi_id, **kwargs):
        return await self.call("vdi.set", {"id": vdi_id, **kwargs})
