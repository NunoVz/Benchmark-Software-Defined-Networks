from scapy.all import sniff, sendp, Ether, IP, UDP, Raw
from scapy.contrib.openflow import *

INTERFACE = "eth0"
TOOL_VM_IP = "11.0.0.11"
TOOL_VM_MAC = "e2:f2:67:5b:26:16"
SRC_MAC = "1a:a8:98:84:5c:ad"
SRC_PORT = 9999
DST_PORT = 9999  # Match this on Tool VM with tcpdump

def is_packet_in(pkt):
    return 'OFPTPacketIn' in pkt.summary()

def handle_packet(pkt):
    print(f"[INFO] Captured: {pkt.summary()}")

    # Encapsulate OpenFlow packet in UDP for easier sniffing
    forward_packet = (
        Ether(src=SRC_MAC, dst=TOOL_VM_MAC) /
        IP(dst=TOOL_VM_IP) /
        UDP(sport=SRC_PORT, dport=DST_PORT) /
        Raw(load=bytes(pkt))
    )

    sendp(forward_packet, iface=INTERFACE, verbose=True)
    print("[INFO] OFPT_PACKET_IN sent to Tool VM.")
    return True

def main():
    print(f"[INFO] Sniffing for OFPT_PACKET_IN...")
    sniff(iface=INTERFACE, filter="tcp", stop_filter=handle_packet)

if __name__ == "__main__":
    main()
