# DupPackets.py  (Mininet VM) — robust iface/route version
import logging
import os
import queue
import struct
import time
import subprocess
import shlex

from threading import Thread

from scapy.all import (
    sniff, IP, UDP, Raw, raw, TCP,
    sendp, Ether, getmacbyip, conf
)
from scapy.contrib.openflow3 import OpenFlow3

# ----------------- Config -----------------
os.makedirs("output/logs", exist_ok=True)
logging.basicConfig(
    filename="output/logs/mininet_forwarder.log",
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

TOOL_VM_IP = "11.0.0.11"
UDP_PORT   = 9999
MARKER     = b"OFP3"

# Set to True to forward any TCP payload that matches (ctrl_ip, ctrl_port),
# even if OpenFlow3() parsing fails. Useful for debugging end-to-end first.
FORWARD_ANY_TCP = False

# Fallback if iface auto-detect fails (e.g., "ens3"); leave as None to force log+return
DEFAULT_IFACE = None

packet_queue = queue.Queue()


# ----------------- Helpers -----------------
def _route_tuple(dst_ip: str):
    """
    Return (gw, iface) using Scapy (handles 3/4 tuple) or 'ip route get' fallback.
    Some Scapy versions return (dst, gw, iface) or (dst, gw, iface, src),
    but 'iface' may incorrectly be a src IP string; detect that and fall back.
    """
    gw, iface = None, None
    try:
        rt = conf.route.route(dst_ip)
        if len(rt) == 4:
            _, gw, iface, _src = rt
        else:
            _, gw, iface = rt
        # Some versions put src IP in 'iface'; detect by presence of dots
        if iface and iface.count(".") == 3:
            iface = None
    except Exception:
        gw, iface = None, None

    if iface is None:
        # Use system route as reliable fallback
        try:
            out = subprocess.check_output(shlex.split(f"ip route get {dst_ip}")).decode()
            toks = out.split()
            iface = toks[toks.index("dev")+1] if "dev" in toks else iface
            gw = toks[toks.index("via")+1] if "via" in toks else gw
        except Exception:
            pass

    if iface is None:
        iface = DEFAULT_IFACE

    return gw, iface


def _nexthop_and_mac(dst_ip: str):
    """
    Compute next-hop IP (gw or dst), resolve its MAC (ARP), and infer egress iface.
    """
    gw, iface = _route_tuple(dst_ip)
    nexthop = dst_ip if not gw or gw in ("0.0.0.0", "::") else gw
    mac = getmacbyip(nexthop) or "ff:ff:ff:ff:ff:ff"
    return nexthop, mac, iface


# ----------------- Sender -----------------
def packet_sender():
    """
    Dequeues framed payloads and sends them as UDP/TOOL_VM_IP:UDP_PORT via L2,
    honoring the actual egress interface and next-hop MAC.
    """
    nexthop_ip, dst_mac, send_iface = _nexthop_and_mac(TOOL_VM_IP)
    if not send_iface:
        logging.error("[sender] No egress interface found to reach Tool VM IP.")
        return

    logging.info(f"[sender] egress={send_iface} nexthop={nexthop_ip} mac={dst_mac}")

    while True:
        payload = packet_queue.get()
        try:
            sendp(
                Ether(dst=dst_mac) /
                IP(dst=TOOL_VM_IP) /
                UDP(sport=UDP_PORT, dport=UDP_PORT) /
                Raw(load=payload),
                iface=send_iface, verbose=False
            )
        except Exception as e:
            logging.error(f"[sender] sendp() error: {e}")


# ----------------- Sniffer/Forwarder -----------------
def forward_openflow_packets(controller_ip, controller_port, stop_event):
    """
    Sniffs TCP to/from (controller_ip, controller_port) on the iface that reaches the controller,
    extracts OpenFlow payloads (or any TCP payload if FORWARD_ANY_TCP=True),
    frames them with [ts][dir][MARKER], and enqueues for sender.
    """
    logging.info("Sniffing OpenFlow and forwarding to Tool VM...")

    # Pick sniff interface based on route to the controller
    _gw, sniff_iface = _route_tuple(controller_ip)
    if not sniff_iface:
        logging.error("[sniffer] No sniff interface found to reach Controller IP.")
        return

    logging.info(f"[sniffer] iface={sniff_iface} ctrl={controller_ip}:{controller_port}")

    Thread(target=packet_sender, daemon=True).start()

    def process(pkt):
        try:
            if TCP not in pkt or not pkt[TCP].payload:
                return

            payload = raw(pkt[TCP].payload)

            # Direction: 1 = IN (switch->controller), 2 = OUT (controller->switch)
            if IP in pkt:
                if pkt[IP].dst == controller_ip:
                    direction = 1
                elif pkt[IP].src == controller_ip:
                    direction = 2
                else:
                    return
            else:
                return

            # Validate OpenFlow 1.3 unless debugging is enabled
            if not FORWARD_ANY_TCP:
                try:
                    _ = OpenFlow3(payload)
                except Exception as e:
                    logging.debug(f"[sniffer] Non-OpenFlow3: {e}")
                    return

            ts = time.time()
            # [8B ts big-endian][1B dir][4B 'OFP3'][OF or raw payload...]
            header = struct.pack("!dB", ts, direction) + MARKER
            packet_queue.put(header + payload)

        except Exception as e:
            logging.error(f"[sniffer] process() error: {e}")

    def should_stop(_): 
        return stop_event.is_set()

    try:
        sniff(
            iface=sniff_iface,
            filter=f"tcp port {controller_port}",
            prn=process,
            stop_filter=should_stop,
            store=0
        )
    except Exception as e:
        logging.error(f"[sniffer] sniff() error: {e}")

    logging.info("Sniffer thread stopped.")
