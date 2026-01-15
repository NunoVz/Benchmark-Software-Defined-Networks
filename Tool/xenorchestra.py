# =========================================
# Imports
# =========================================
import os
import socket
import subprocess
import time
import paramiko
import json
import re
import shlex
from pathlib import Path
import asyncio
from dotenv import load_dotenv

# Import the WebSocket client implementation. The helper lives in wo_ws.py,
# but is logically called XoWsClient. If you rename the file, adjust
# this import accordingly.
from wo_ws import XoWsClient

load_dotenv()

# =========================================
# Configuração Geral / Constantes
# =========================================
MININET_VM_IP = os.environ.get("MININET_VM_IP")
MININET_VM_USER = os.environ.get("MININET_VM_USER")
MININET_VM_PASSWORD = os.environ.get("MININET_VM_PASSWORD")
GRPC_SYSTEMD_SERVICE = os.environ.get("GRPC_SYSTEMD_SERVICE", "mininet-grpc.service")

GRPC_PORT = 80

# Host que corre QEMU + mininet-qemu.sh Deprecated
HOST_WITH_QEMU = "10.3.1.117"
HOST_WITH_QEMU_USER = "vasques"
HOST_WITH_QEMU_KEY = "/home/admin/.ssh/id_ed25519"

# Xen Orchestra (novo endpoint por defeito)
XO_URL = os.environ.get("XO_URL")
XO_TOKEN = os.environ.get("XO_TOKEN")
XO_USER = os.environ.get("XO_USER")
XO_PASSWORD = os.environ.get("XO_PASSWORD")
XO_VM_ID = os.environ.get("XO_VM_ID")

# Caminho do script QEMU
QEMU_SCRIPT = Path("/home/vasques/mininet-qemu/mininet-qemu.sh")

SSH_KEY_CANDIDATES = [Path.home()/".ssh/id_ed25519", Path.home()/".ssh/id_rsa"]
HOST_VM_IP = os.environ.get("HOST_VM_IP")  # IP a usar por outras VMs para chegar ao gRPC

# Estado descoberto em runtime (QEMU)
_LAST_SSHPORT = None   # forwarded SSH na máquina host de QEMU
_LAST_GRPCPORT = None  # forwarded gRPC na máquina host de QEMU


# --- Clone-from-template (novo modo) ---
#MININET_TEMPLATE_UUID = "a3123f4b-1ef2-6ab4-8ac0-6b2b8b3ca5c5"  # Template base

MININET_TEMPLATE_UUID = os.environ.get("MININET_TEMPLATE_UUID")

MININET_CLONE_NAME    = os.environ.get("MININET_CLONE_NAME", "SDN_Mininet")  # nome opcional
MININET_CPUS          = int(os.environ.get("MININET_CPUS", "18"))
MININET_MEM_GB        = int(os.environ.get("MININET_MEM_GB", "8"))  # GB
# Redes para VIFs (IDs de network no XO)
MININET_NET_VIF1      = os.environ.get("MININET_NET_VIF1")
MININET_NET_VIF2      = os.environ.get("MININET_NET_VIF2")

# =========================================
# Helpers: Xen Orchestra Web Socket(XO)
# =========================================


def _arun(coro):
    return asyncio.run(coro)

def xo_vm_set_boot_order(url, vm_id, order, *, token=None, username=None, password=None):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.call("vm.setBootOrder", {"vm": vm_id, "order": order})
    return asyncio.run(_inner())  # uses your XoWsClient  :contentReference[oaicite:1]{index=1}

def xo_get_all_objects(url, username=None, password=None, token=None, filter="VM"):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.get_all_objects(filter=filter)
    return _arun(_inner())


def xo_vm_create(url, *, token=None, username=None, password=None, **params):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.vm_create(**params)
    return _arun(_inner())

def xo_vm_set(url, vm_id, *, token=None, username=None, password=None, **params):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.vm_set(vm_id, **params)
    return _arun(_inner())

def xo_vm_start(url, vm_id, *, token=None, username=None, password=None):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.vm_start(vm_id)
    return _arun(_inner())

def xo_vm_stop(url, vm_id, *, token=None, username=None, password=None):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.vm_stop(vm_id)
    return _arun(_inner())

def xo_vm_delete(url, vm_id, *, token=None, username=None, password=None, force=False):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.vm_delete(vm_id, force=force)
    return _arun(_inner())

def xo_vdi_set(url, vdi_id, *, token=None, username=None, password=None, **params):
    async def _inner():
        async with XoWsClient(url, username, password, token).connect() as xo:
            return await xo.vdi_set(vdi_id, **params)
    return _arun(_inner())

# =========================================
# Helpers: Xen Orchestra (XO)
# =========================================

#---- Creating From Template ----
def _xo_call(method: str, params: dict | None = None):
    """
    Generic wrapper around the Xen Orchestra JSON‑RPC API via WebSocket.

    This replaces the previous implementation which shell‑invoked `xo-cli`.
    It uses the asynchronous ``XoWsClient`` to issue a RPC call and wraps
    the coroutine in ``asyncio.run`` for synchronous use.

    :param method: The fully qualified JSON‑RPC method name (e.g. "vm.delete").
    :param params: Dictionary of parameters to pass to the RPC method. Optional.
    :returns: The result of the RPC call, already deserialised from JSON.
    :raises RuntimeError: If the RPC call fails or returns an error.
    """
    params = params or {}

    async def _inner():
        # Create a WebSocket client with the configured URL and credentials.
        async with XoWsClient(
            XO_URL,
            username=XO_USER,
            password=XO_PASSWORD,
            token=XO_TOKEN,
        ).connect() as xo:
            # Perform the RPC call. If the method raises an exception
            # (e.g. due to a JSON‑RPC error), let it propagate up.
            return await xo.call(method, params)

    # Use the helper defined above to run the async coroutine synchronously.
    return _run(_inner())

def _delete_vm_by_name(force=False):
    """
    Apaga uma VM no Xen Orchestra com base no name_label (nome visível no XO).
    Faz:
      1) Pesquisa via xo.getAllObjects
      2) Para a VM se estiver a correr
      3) Executa vm.delete
    """
    objs = _xo_get_all_objects()
    target_vm_id = None
    target_uuid = None
    for oid, obj in objs.items():
        if obj.get("type") != "VM":
            continue
        if obj.get("name_label") == MININET_CLONE_NAME:
            target_vm_id = oid
            target_uuid = obj.get("uuid")
            break

    if not target_vm_id:
        print(f"[WARN] Nenhuma VM encontrada com o nome '{MININET_CLONE_NAME}'. Nada para apagar.")
        return False

    print(f"[INFO] Encontrada VM '{MININET_CLONE_NAME}' → id={target_vm_id}, uuid={target_uuid}")

    xo_vm_delete(
        XO_URL,
        target_vm_id,
        token=XO_TOKEN,
        username=XO_USER,
        password=XO_PASSWORD,
        force=bool(force),
    )
    print(f"[INFO] VM '{MININET_CLONE_NAME}' apagada com sucesso.")
    return True




def _vm_wait_power(vm_id: str, desired: str, timeout=180, interval=3):
    env = _xo_env()
    desired = desired.lower()
    t0 = time.time()
    while time.time() - t0 < timeout:
        state = _get_vm_state_xo(vm_id, env)
        if state == desired:
            return True
        time.sleep(interval)
    raise TimeoutError(f"VM {vm_id} did not reach '{desired}' in {timeout}s.")

def _create_mininet_vm_from_template():

    # 4.1 resolver IDs
    template_id = MININET_TEMPLATE_UUID
    net1_id = MININET_NET_VIF1
    net2_id = MININET_NET_VIF2

    params = {
        "template": template_id,          
        "name_label": MININET_CLONE_NAME,
        "bootAfterCreate": False,
        "VIFs": [
            {"network": net1_id},
            {"network": net2_id},
        ],
    }


    print(f"[INFO] Creating VM from template {MININET_TEMPLATE_UUID} …")
    # Use the WebSocket RPC helper to create the VM. ``xo_vm_create`` returns
    # the new VM's xo-id as a string.
    vm_id = xo_vm_create(
        XO_URL,
        token=XO_TOKEN,
        username=XO_USER,
        password=XO_PASSWORD,
        **params,
    )
    if not vm_id:
        raise RuntimeError("vm.create did not return a VM id")
    print(f"[INFO] New VM id: {vm_id}")
    xo_vm_set_boot_order(XO_URL, vm_id, "c", token=XO_TOKEN, username=XO_USER, password=XO_PASSWORD)
    xo_vm_start(XO_URL, vm_id, token=XO_TOKEN, username=XO_USER, password=XO_PASSWORD)

   
    # Esperar 'running' (ou forçar arranque)
    try:
        _vm_wait_power(vm_id, "running", timeout=180, interval=3)
    except TimeoutError:
        print("[WARN] VM not 'running' yet. Forcing start …")
        # Force start via WebSocket RPC instead of xo-cli
        try:
            xo_vm_start(
                XO_URL,
                vm_id,
                token=XO_TOKEN,
                username=XO_USER,
                password=XO_PASSWORD,
            )
        except Exception as e:
            print("[WARN] Error starting VM via websocket:", e)
        _vm_wait_power(vm_id, "running", timeout=120, interval=3)

    # Descobrir UUID da nova VM e guardar em ficheiro
    objs = _xo_get_all_objects()
    _, vm_obj = _find_vm_obj(vm_id, objs)
    new_uuid = vm_obj.get("uuid") if vm_obj else None
    save_path = Path("./tmp/mininet_last_vm.json")
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with open(save_path, "w") as f:
        json.dump({"xo_id": vm_id, "uuid": new_uuid, "name_label": MININET_CLONE_NAME}, f, indent=2)
    print(f"[INFO] Saved new VM identifiers to {save_path}")

  

    return vm_id, {"CPUs": MININET_CPUS, "uuid": new_uuid}

#---Only Boot
def _xo_env():
    # keep for other uses if needed
    return {}

def _xo_cli_base():
    host = XO_URL.rstrip("/")
    base = ["xo-cli", f"--url={host}"]
    if XO_TOKEN:
        base += [f"--token={XO_TOKEN}"]
    return base



def _resolve_xo_id_by_uuid(obj_type: str, uuid_or_id: str) -> str:
    objs = _xo_get_all_objects()
    if uuid_or_id in objs:
        return uuid_or_id
    # procura por uuid e tipo
    for oid, o in objs.items():
        if o.get("type") == obj_type and o.get("uuid") == uuid_or_id:
            return oid
    raise RuntimeError(f"[XO] Não encontrei {obj_type} com uuid '{uuid_or_id}'.")


def _xo_get_all_objects():
    """
    Fetch all objects from Xen Orchestra via the WebSocket JSON‑RPC API.

    This replaces the old implementation that invoked ``xo-cli``. It uses
    the ``xo_get_all_objects`` helper defined at the top of this module,
    which internally creates a WebSocket connection and issues the
    ``xo.getAllObjects`` call.

    :returns: A dictionary mapping XO object IDs to their metadata.
    :raises RuntimeError: If the RPC call returns no data or fails.
    """
    objs = xo_get_all_objects(
        XO_URL,
        token=XO_TOKEN,
        username=XO_USER,
        password=XO_PASSWORD,
    )
    # Ensure we have a non-empty dictionary. If the RPC call failed,
    # ``objs`` may be ``None`` or not a mapping, so guard against that.
    if not isinstance(objs, dict) or not objs:
        raise RuntimeError("xo.getAllObjects returned empty/invalid result")
    return objs


def _find_vm_obj(vm_id_or_uuid, objects=None):
    """Find a VM by XO object id OR by uuid. Return its dict or None."""
    if objects is None:
        objects = _xo_get_all_objects()
    for oid, obj in objects.items():
        if obj.get("type") != "VM":
            continue
        if oid == vm_id_or_uuid or obj.get("uuid") == vm_id_or_uuid:
            return oid, obj
    return None, None

def _get_vm_state_xo(vm_id_or_uuid, _env_unused):
    try:
        objs = _xo_get_all_objects()
    except Exception as e:
        print("[ERROR]", e)
        return "unknown"

    oid, vm = _find_vm_obj(vm_id_or_uuid, objs)
    if not vm:
        print(f"[WARN] VM not found by id/uuid '{vm_id_or_uuid}'.")
        # show a small sample to help
        sample = []
        for oid2, obj in objs.items():
            if obj.get("type") == "VM":
                sample.append((oid2, obj.get("uuid"), obj.get("name_label"), obj.get("power_state") or obj.get("powerState")))
                if len(sample) >= 10:
                    break
        if sample:
            print("[HINT] id | uuid | name | power_state")
            for r in sample:
                print(" | ".join(str(x or "") for x in r))
        return "unknown"

    power = (vm.get("power_state") or vm.get("powerState") or "unknown").lower()
    print(f"[INFO] Current VM power state: {power}")
    return power
def _stop_and_start_vm_xo(vm_id=XO_VM_ID):
    print(f"[INFO] Checking VM state before rebooting {vm_id}")
    env = _xo_env()

    # resolve state (retry a few times)
    for _ in range(5):
        state = _get_vm_state_xo(vm_id, env)
        if state != "unknown":
            break
        print("[WARN] Unknown state. Retrying in 3s...")
        time.sleep(3)
    else:
        raise RuntimeError(f"Could not resolve VM state for '{vm_id}'. Use XO object id or uuid.")

    # We no longer use ``xo-cli`` for these operations. Instead, call the
    # Xen Orchestra RPC methods via the WebSocket helpers defined above.
    if state == "running":
        print("[INFO] Stopping VM...")
        try:
            xo_vm_stop(
                XO_URL,
                vm_id,
                token=XO_TOKEN,
                username=XO_USER,
                password=XO_PASSWORD,
            )
        except Exception as e:
            print("[WARN] Failed to stop VM via websocket:", e)
        wait_for_vm_state(vm_id, "halted", env)
        print("[INFO] Starting VM after stop...")
        try:
            xo_vm_start(
                XO_URL,
                vm_id,
                token=XO_TOKEN,
                username=XO_USER,
                password=XO_PASSWORD,
            )
        except Exception as e:
            print("[WARN] Failed to start VM via websocket:", e)
        wait_for_vm_state(vm_id, "running", env)

    elif state in ("paused", "suspended"):
        print(f"[INFO] VM is {state}. Resuming...")
        # Xen Orchestra has a ``vm.resume`` method for paused or suspended VMs.
        # Use the generic ``_xo_call`` wrapper to invoke it.
        try:
            _xo_call("vm.resume", {"id": vm_id})
        except Exception as e:
            print("[WARN] Failed to resume VM via websocket:", e)
        wait_for_vm_state(vm_id, "running", env)

    elif state == "halted":
        print("[INFO] Starting VM...")
        try:
            xo_vm_start(
                XO_URL,
                vm_id,
                token=XO_TOKEN,
                username=XO_USER,
                password=XO_PASSWORD,
            )
        except Exception as e:
            print("[WARN] Failed to start VM via websocket:", e)
        wait_for_vm_state(vm_id, "running", env)

    else:
        print(f"[INFO] VM already in state '{state}'. No action needed.")



def wait_for_grpc(ip, port=GRPC_PORT, timeout=180):
    print(f"[INFO] Waiting for gRPC port {port} to open...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.create_connection((ip, port), timeout=5)
            s.close()
            print("[INFO] gRPC server is now reachable.")
            return True
        except:
            time.sleep(5)
    raise TimeoutError("Timeout: gRPC server not available.")
# =========================================
# Helpers: QEMU / SSH / TCP
# =========================================
def _pick_key():
    for k in SSH_KEY_CANDIDATES:
        if k.exists():
            return str(k)
    return None


def _run(cmd, check=True, env=None, shell=False):
    res = subprocess.run(
        cmd if shell else shlex.split(cmd),
        text=True, capture_output=True, env=env, shell=shell
    )
    if check and res.returncode != 0:
        raise RuntimeError(f"[CMD FAIL] rc={res.returncode}\nCMD: {cmd}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}")
    return res


def _qemu_parse_ports(s: str):
    m = re.search(r"SSHPORT=(\d+)\s+PORT=(\d+)", s)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _qemu_start():
    global _LAST_SSHPORT, _LAST_GRPCPORT
    out, err, _ = _host_run("./mininet-qemu.sh start", check=False)
    blob = out + "\n" + err
    sshp, grpcp = _qemu_parse_ports(blob)
    if not sshp:
        sout, serr, _ = _host_run("./mininet-qemu.sh status", check=False)
        sshp, grpcp = _qemu_parse_ports(sout + "\n" + serr)
        if not sshp:
            raise RuntimeError(f"Could not parse SSH/PORT from qemu output.\n---\n{blob}\n---\n{sout}\n{serr}")
    _host_wait_tcp(HOST_WITH_QEMU, grpcp, timeout=180)
    _LAST_SSHPORT, _LAST_GRPCPORT = sshp, grpcp
    return sshp, grpcp


def _qemu_stop():
    _host_run("./mininet-qemu.sh stop", check=False)


def _host_wait_tcp(host, port, timeout=180, interval=2):
    print(f"[INFO] Waiting for TCP {host}:{port} ...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection((host, port), timeout=5):
                print(f"[OK] {host}:{port} reachable.")
                return True
        except OSError:
            time.sleep(interval)
    raise TimeoutError(f"Timeout: {host}:{port} not reachable")


# =========================================
# SSH Helpers
# =========================================
HOST_WITH_QEMU_PASSWORD = os.environ.get("QEMU_HOST_PASSWORD")
def _host_ssh_client():
    target = HOST_WITH_QEMU
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        if HOST_WITH_QEMU_KEY and os.path.exists(HOST_WITH_QEMU_KEY):
            pkey = paramiko.Ed25519Key.from_private_key_file(
                HOST_WITH_QEMU_KEY,
                password=os.environ.get("QEMU_HOST_KEY_PASSPHRASE")
            )
            ssh.connect(target, username=HOST_WITH_QEMU_USER, pkey=pkey, look_for_keys=False, allow_agent=False, timeout=15)
            return ssh
    except Exception:
        pass
    if HOST_WITH_QEMU_PASSWORD:
        ssh.connect(target, username=HOST_WITH_QEMU_USER, password=HOST_WITH_QEMU_PASSWORD,
                    look_for_keys=False, allow_agent=False, timeout=15)
        return ssh
    raise paramiko.AuthenticationException(f"SSH auth failed for {HOST_WITH_QEMU_USER}@{target}.")


def _host_run(cmd, check=True):
    ssh = _host_ssh_client()
    if not cmd.startswith("/"):
        cmd = f"cd {QEMU_SCRIPT.parent} && {cmd}"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    out, err = stdout.read().decode(), stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    ssh.close()
    if check and rc != 0:
        raise RuntimeError(f"[HOST RUN] rc={rc}\nCMD: {cmd}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    return out, err, rc




# =========================================
# Operações: Mininet e GRPC
# =========================================
def start_mininet_grpc(ip=None, username=MININET_VM_USER, password=None, port=80):
    if _LAST_SSHPORT is not None:
        print("[INFO] Restarting mininet-grpc.service via QEMU jump…")
        _ssh_run(None, username, password,
                 "systemctl daemon-reload; systemctl restart mininet-grpc.service; "
                 "systemctl --no-pager --full status mininet-grpc.service | sed -n '1,25p'",
                 check=False)
        return
    target_ip = ip or MININET_VM_IP
    ssh_password = password or os.getenv("MININET_VM_PASSWORD")
    print("[INFO] Restarting mininet-grpc.service via direct SSH…")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(target_ip, username=username, password=ssh_password, look_for_keys=False, allow_agent=False, timeout=20)
    cmd_inner = 'systemctl daemon-reload && systemctl restart mininet-grpc.service && systemctl --no-pager --full status mininet-grpc.service | sed -n "1,25p"'
    quoted = shlex.quote(cmd_inner)
    full_cmd = f"echo {ssh_password} | sudo -S bash -lc {quoted}"
    stdin, stdout, stderr = ssh.exec_command(full_cmd)
    out, err = stdout.read().decode(), stderr.read().decode()
    rc = stdout.channel.recv_exit_status()
    ssh.close()
    if rc != 0:
        raise RuntimeError(f"[ERROR] service restart rc={rc}\nSTDOUT:\n{out}\nSTDERR:\n{err}")
    print(out.strip() or "[INFO] Service restarted.")


import time
import shlex, paramiko

def start_mininet_grpc_xen(ip=MININET_VM_IP, username=MININET_VM_USER, password=None, grpc_port=80):
    print("[INFO] Starting mininet_server.py via SSH with sudo...")
    
    ssh_password = password or os.getenv("MININET_VM_PASSWORD")
    if not ssh_password:
        raise ValueError("Mininet VM password not found in environment or arguments.")

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(
        ip,
        username=username,
        password=ssh_password,
        look_for_keys=False,
        allow_agent=False,
        timeout=20
    )

    # 1) Valida credenciais sudo antecipadamente (mata logo se falhar)
    #  -S  -> lê password do stdin
    #  -k  -> força pedido de password (não usa timestamp antigo)
    #  -p '' -> prompt vazio (não poluir o output)
    validate_cmd = "sudo -S -k -p '' -v && echo SUDO_OK || echo SUDO_FAIL"
    stdin, stdout, stderr = ssh.exec_command(validate_cmd, get_pty=True)
    stdin.write(ssh_password + "\n"); stdin.flush()
    out_v = stdout.read().decode(errors="ignore")
    err_v = stderr.read().decode(errors="ignore")
    rc_v = stdout.channel.recv_exit_status()
    if "SUDO_OK" not in out_v or rc_v != 0:
        ssh.close()
        raise RuntimeError(f"[ERROR] sudo validation failed (rc={rc_v}). OUT:\n{out_v}\nERR:\n{err_v}")

    # 2) Script remoto via HEREDOC 
    remote_script = f"""\
set -euo pipefail

LOGDIR=/home/{username}/Omega/Mininet/logs
APPDIR=/home/{username}/Omega/Mininet
PY=/usr/bin/python3    # evita problemas de PATH sob sudo

mkdir -p "$LOGDIR"
cd "$APPDIR"

if [ -f "$LOGDIR/mininet_server.pid" ] && ! kill -0 "$(cat "$LOGDIR/mininet_server.pid")" 2>/dev/null; then
  rm -f "$LOGDIR/mininet_server.pid"
fi

# Se já estiver (confirmado com pgrep), não relançar
if [ -f "$LOGDIR/mininet_server.pid" ] && kill -0 "$(cat "$LOGDIR/mininet_server.pid")" 2>/dev/null \
   && pgrep -f "mininet_server.py" >/dev/null; then
  echo "[INFO] Já está a correr (PID $(cat "$LOGDIR/mininet_server.pid"))" >> "$LOGDIR/mininet_server.log"
else
  # mata restos antigos
  pgrep -f "mininet_server.py" >/dev/null && pkill -f "mininet_server.py" || true
  # arranque completamente desacoplado
  setsid nohup "$PY" mininet_server.py >> "$LOGDIR/mininet_server.log" 2>&1 &
  echo $! > "$LOGDIR/mininet_server.pid"
  echo "[INFO] Started mininet_server.py (PID $(cat "$LOGDIR/mininet_server.pid"))" >> "$LOGDIR/mininet_server.log"
fi

# Health-check básico (se o teu servidor realmente escuta TCP; se não, comenta)
if ! ss -ltnp | grep -E ":{grpc_port}\\s" >/dev/null 2>&1; then
  echo "[WARN] Nada a ouvir em :{grpc_port} (pode ser normal se o gRPC não expõe TCP imediatamente)"
fi

echo "---TAIL-LOG-START---"
tail -n 80 "$LOGDIR/mininet_server.log" || true
echo "---TAIL-LOG-END---"
"""

    # 3) Executa o script remoto via sudo bash -s + HEREDOC
    # Usamos -S para password; -p '' para prompt vazio; get_pty=True por compat com sudo
    full_cmd = "sudo -S -p '' bash -s"
    stdin, stdout, stderr = ssh.exec_command(full_cmd, get_pty=True)
    # envia a password primeiro
    stdin.write(password + "\n"); stdin.flush()
    # envia o corpo do script (heredoc implícito por Paramiko)
    stdin.write(remote_script + "\n"); stdin.flush()
    # fecha stdin para o bash não ficar à espera
    stdin.channel.shutdown_write()

    out = stdout.read().decode(errors="ignore")
    err = stderr.read().decode(errors="ignore")
    rc = stdout.channel.recv_exit_status()

    ssh.close()

    # 4) Diagnóstico claro
    if rc != 0:
        # Mostra tudo para veres porque o sudo/bash falhou
        raise RuntimeError(f"[ERROR] remote rc={rc} ao lançar mininet_server.py\nOUT:\n{out}\nERR:\n{err}")

    # Opcional: extrai só a parte do tail
    print(out.strip() or "[INFO] Comando remoto OK.")
    print("[INFO] mininet_server.py lançado (ou já estava em execução).")

# =========================================
# Orquestração principal
# =========================================
def full_restart_mininet(mode="container", grpc_port=GRPC_PORT):
    if mode in ("container", "qemu"):
        print("[INFO] Restarting Mininet (QEMU)…")
        _qemu_stop()
        _qemu_start()
        return True
    elif mode == "xen":
        print("[INFO] Restarting Mininet via Xen Orchestra…")
        _stop_and_start_vm_xo(XO_VM_ID)
        wait_for_vm(MININET_VM_IP, 22, 600)
        #start_mininet_grpc_xen()
        wait_for_grpc(MININET_VM_IP)
        print("[SUCCESS] XO reboot done and gRPC is up.")
        return True
    elif mode == "xen_from_template":

        print("[INFO] Recreating Mininet VM from template via XO …")
        vm_id, spec = _create_mininet_vm_from_template()
        print(f"[INFO] Created VM {vm_id} with spec: {spec}")

        # Se a VM nova vai usar o MESMO IP (DHCP estável/estático), podes esperar já:
        wait_for_vm(MININET_VM_IP, 22, 600)
        wait_for_grpc(MININET_VM_IP)
        print("[SUCCESS] New VM is up and gRPC is reachable.")
        return True

    else:
        raise ValueError("mode must be 'container', 'qemu', or 'xen'")


# =========================================
# Waits e main
# =========================================
def wait_for_vm_state(vm_id_or_uuid, desired_state, env, timeout=60, interval=5):
    desired_state = desired_state.lower()
    print(f"[INFO] Waiting for VM {vm_id_or_uuid} to reach '{desired_state}'...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        state = _get_vm_state_xo(vm_id_or_uuid, env)
        print(f"[DEBUG] Current state: {state}")
        if state == desired_state:
            print(f"[INFO] VM reached desired state: {state}")
            return True
        time.sleep(interval)
    raise TimeoutError(f"[ERROR] VM did not reach state '{desired_state}' within {timeout}s.")

def wait_for_vm(ip, port=22, timeout=180):
    print(f"[INFO] Waiting for {ip}:{port} ...")
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection((ip, port), timeout=5):
                print("[INFO] VM is reachable.")
                return True
        except OSError:
            time.sleep(2)
    raise TimeoutError(f"Timeout: {ip}:{port} not reachable.")


if __name__ == "__main__":
    full_restart_mininet()
