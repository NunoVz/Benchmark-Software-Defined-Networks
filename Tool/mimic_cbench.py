import os, csv, struct, time, hashlib
from scapy.all import sniff, Raw
from scapy.contrib.openflow3 import OFPTPacketIn, OFPTPacketOut, OFPTFlowMod, OpenFlow3
from arguments_parser import parser

# -------------------- Logging --------------------
os.makedirs("output/logs", exist_ok=True)
logf = open("output/logs/mimic_cbench.log", "w")
def log(msg, lvl="DEBUG"):
    line = f"[{lvl}] {msg}"
    print(line); logf.write(line + "\n"); logf.flush()

# -------------------- Aux outputs --------------------
rtt_aux = "output/mimic_cbench_rtt.csv"
thr_aux = "output/mimic_cbench_throughput.csv"
os.makedirs("output", exist_ok=True)
open(rtt_aux, "w").close()
open(thr_aux, "w").close()

MARKER   = b"OFP3"
UDP_PORT = 9999

# -------------------- State --------------------
recent_in_times = []      # list of (t_in_fw, key) for fallback-by-time (forwarder clock)
syn_timestamps  = {}      # key -> t_in_fw
packet_in_count = 0
packet_out_count = 0
matched_in_this_bucket = 0
start_bucket = time.time()
WIN_SEC = 3.0             # fallback pairing window (seconds)

# -------------------- Helpers --------------------
def ofp_key(pkt):
    """Prefer buffer_id (when != NO_BUFFER), else hash carried data."""
    try:
        for layer in (OFPTPacketIn, OFPTPacketOut, OFPTFlowMod):
            if pkt.haslayer(layer):
                node = pkt[layer]
                bid = getattr(node, "buffer_id", None)
                if bid is not None and bid != 0xffffffff:
                    return ("buf", bid)
                data = getattr(node, "data", b"")
                try:
                    b = bytes(data) if data else b""
                except Exception:
                    b = b""
                if b:
                    return ("hash", hashlib.sha1(b).hexdigest()[:16])
    except Exception:
        return None
    return None

def gc_recent(now_fw):
    """Drop stale INs outside the fallback window (use forwarder time)."""
    while recent_in_times and now_fw - recent_in_times[0][0] > WIN_SEC:
        recent_in_times.pop(0)

# -------------------- Packet handling --------------------
def packet_callback(pkt):
    global packet_in_count, packet_out_count, matched_in_this_bucket, start_bucket

    try:
        if not pkt.haslayer(Raw):
            return
        buf = pkt[Raw].load
        if len(buf) < 13:  # [8B ts_fw][1B dir][4B MARKER]
            return

        ts_fw    = struct.unpack("!d", buf[:8])[0]  # forwarder capture time
        direction = buf[8]                          # 1=IN(switch->ctrl), 2=OUT(ctrl->switch)
        marker   = buf[9:13]
        if marker != MARKER:
            log(f"Bad marker {marker}", "WARNING"); return

        payload = buf[13:]
        try:
            ofp = OpenFlow3(payload)
        except Exception as e:
            log(f"OpenFlow3 parse fail: {e}", "WARNING"); return

        now_tool = time.time()  # only for logging (forward path delay)
        gc_recent(ts_fw)
        k = ofp_key(ofp)

        # -------- IN (request) --------
        if direction == 1:
            packet_in_count += 1
            if k:
                syn_timestamps[k] = ts_fw
            recent_in_times.append((ts_fw, k))
            log(f"PacketIn (dir=IN) | fwd_delay={now_tool - ts_fw:.6f}")

        # -------- OUT (response) --------
        elif direction == 2:
            which = "PacketOut" if ofp.haslayer(OFPTPacketOut) else ("FlowMod" if ofp.haslayer(OFPTFlowMod) else "Other")
            matched = False

            # 1) Key-based match (buffer_id / data-hash)
            if k and k in syn_timestamps:
                t_in_fw = syn_timestamps.pop(k)
                rtt = ts_fw - t_in_fw
                if rtt >= 0:
                    with open(rtt_aux, "a", newline="") as f:
                        csv.writer(f).writerow([rtt])
                    packet_out_count += 1
                    matched_in_this_bucket += 1
                    matched = True
                    log(f"RTT recorded ({which}) via key: {rtt:.6f}")

            # 2) Fallback: newest IN within window (both on forwarder clock)
            if not matched and recent_in_times:
                # search from newest to oldest for something within the window
                for i in range(len(recent_in_times) - 1, -1, -1):
                    t_in_fw, _ = recent_in_times[i]
                    dt = ts_fw - t_in_fw
                    if 0.0 <= dt <= WIN_SEC:
                        rtt = dt
                        # consume this IN so we don't reuse it
                        del recent_in_times[i]
                        with open(rtt_aux, "a", newline="") as f:
                            csv.writer(f).writerow([rtt])
                        packet_out_count += 1
                        matched_in_this_bucket += 1
                        matched = True
                        log(f"RTT recorded ({which}) via time: {rtt:.6f}")
                        break

            if not matched:
                log(f"{which} with no matching IN")

        # -------- Throughput bucket (matched completions/s) --------
        if now_tool - start_bucket >= 1.0:
            duration = now_tool - start_bucket
            thr = matched_in_this_bucket / duration
            with open(thr_aux, "a", newline="") as f:
                csv.writer(f).writerow([thr])
            log(f"Throughput recorded: {thr:.2f}")

            # reset per-bucket counters
            packet_in_count = 0
            packet_out_count = 0
            matched_in_this_bucket = 0
            start_bucket = now_tool

    except Exception as e:
        log(f"Packet processing failed: {e}", "ERROR")

# -------------------- Aggregators for benchmark.py --------------------
def initialize_csv(controller_name, approach, topology, folder, request_time, throughput):
    if not (throughput or request_time):
        print("Select throughput or request time to save the results")
        return
    prefix = "pppt" if approach == "P" else "rppt"
    files = []
    if throughput:
        fn = f"output/{folder}/{controller_name}_{topology}_{prefix}_throughput.csv"
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "w", newline="") as f:
            csv.writer(f).writerow(["num_switches", "throughput"])
        files.append((fn, None))
    if request_time:
        fn = f"output/{folder}/{controller_name}_{topology}_{prefix}_rtt.csv"
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "w", newline="") as f:
            csv.writer(f).writerow(["num_switches", "min_value", "avg_value", "max_value", "mdev_value"])
        files.append((fn, None))
    return files

def calculate(path):
    try:
        with open(path, "r") as f:
            vals = [float(r[0]) for r in csv.reader(f)]
        if not vals:
            return None, None, None, None
        mn, mx = min(vals), max(vals)
        avg = sum(vals)/len(vals)
        mdev = sum(abs(x - avg) for x in vals)/len(vals)
        return mn, avg, mx, mdev
    except Exception as e:
        log(f"Failed to process {path}: {e}", "ERROR")
        return None, None, None, None

def results(size, controller_name, topology, approach, folder, request_time, throughput):
    time.sleep(5)  # cool-down so last bucket flushes
    rtt_min, rtt_avg, rtt_max, rtt_mdev = calculate(rtt_aux)
    thr_min, thr_avg, thr_max, thr_mdev = calculate(thr_aux)
    print("(", rtt_avg, ",", thr_avg, ")")

    prefix = "pppt" if approach == "P" else "rppt"
    if throughput:
        fn = f"output/{folder}/{controller_name}_{topology}_{prefix}_throughput.csv"
        with open(fn, "a", newline="") as f:
            csv.writer(f).writerow([str(size), str(thr_avg)])
    if request_time:
        fn = f"output/{folder}/{controller_name}_{topology}_{prefix}_rtt.csv"
        with open(fn, "a", newline="") as f:
            csv.writer(f).writerow([str(size), str(rtt_min), str(rtt_avg), str(rtt_max), str(rtt_mdev)])

# -------------------- Main --------------------
if __name__ == "__main__":
    args = parser("mimic_cbench")
    log(f"Starting packet sniffing on UDP port {UDP_PORT}...")
    sniff(prn=packet_callback, iface=args.iface, filter=f"udp and port {UDP_PORT}", store=0)
