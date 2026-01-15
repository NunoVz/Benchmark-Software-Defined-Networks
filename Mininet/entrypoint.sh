#!/usr/bin/env bash
set -euo pipefail

# Optional: auto-install/upgrade deps from bind-mounted repo
if [ -f /opt/Mininet/requirements.txt ]; then
  /opt/venv/bin/pip install --no-cache-dir -r /opt/Mininet/requirements.txt >/dev/null 2>&1 || true
fi

# Optional: regenerate gRPC stubs
if [ -f /opt/Mininet/mininet_control.proto ]; then
  python -m grpc_tools.protoc \
    -I /opt/Mininet \
    --python_out=/opt/Mininet \
    --grpc_python_out=/opt/Mininet \
    /opt/Mininet/mininet_control.proto || true
fi

# ---- OVS startup (container-internal OVS, not host) ----
mkdir -p /var/run/openvswitch /etc/openvswitch
rm -f /var/run/openvswitch/ovsdb-server.pid /var/run/openvswitch/ovs-vswitchd.pid || true

# Force a brand-new DB if requested (not needed when you always recreate; harmless otherwise)
if [ "${RESET_OVS_DB:-1}" = "1" ] || [ ! -f /etc/openvswitch/conf.db ]; then
  rm -f /etc/openvswitch/conf.db || true
  ovsdb-tool create /etc/openvswitch/conf.db /usr/share/openvswitch/vswitch.ovsschema
fi

ovsdb-server --remote=punix:/var/run/openvswitch/db.sock \
             --remote=db:Open_vSwitch,Open_vSwitch,manager_options \
             --pidfile --detach
ovs-vsctl --no-wait init
ovs-vswitchd --pidfile --detach

# --- graceful shutdown trap ---
cleanup() {
  echo "[INFO] Graceful shutdown…"
  ovs-appctl -t ovs-vswitchd exit || true
  ovs-appctl -t ovsdb-server exit || true
  if [ -n "${APP_PID-}" ]; then
    kill -TERM "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
  fi
}
trap cleanup TERM INT

# Serve mode: run your gRPC server in background so trap can execute
if [ "${1:-}" = "serve" ]; then
  shift
  python /opt/Mininet/mininet_server.py "$@" &
  APP_PID=$!
  wait "$APP_PID"
  exit $?
fi

# Otherwise run what was requested
"$@"
