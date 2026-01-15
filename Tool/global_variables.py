import os
from ControllerMonitor import *

# Global variables for state management
start_time = None
end_time = None
pkt_in_sniff = None
last_time_pkt_in = None
topology_match = False
fail = False
target_links = None
total_packets = 0
count_packets = 0
total_lldp = 0
count_lldp = 0
count_cpu = 0
count_memory = 0

# A single, lazily-initialized instance of the monitor
_controller_monitor_instance = None

def get_controller_monitor():
    """
    Returns a singleton instance of the ControllerMonitor,
    configured from environment variables.
    """
    global _controller_monitor_instance
    if _controller_monitor_instance is None:
        # These variables should be loaded from .env by the main script
        ip = os.getenv("CONTROLLER_MONITOR_IP", "127.0.0.1")
        user = os.getenv("CONTROLLER_MONITOR_USER")
        password = os.getenv("CONTROLLER_MONITOR_PASS")
        
        # Assuming ControllerMonitor can be initialized with None/empty user/pass
        _controller_monitor_instance = ControllerMonitor('java', ip, user, password)
    return _controller_monitor_instance

# For any legacy code that might still be doing `from global_variables import controller_monitor`
# This will print a warning if used. The better way is `get_controller_monitor()`.
class _DeprecatedMonitor:
    def __getattribute__(self, name):
        print("Warning: Direct import of 'controller_monitor' is deprecated. Use 'get_controller_monitor()' instead.")
        monitor = get_controller_monitor()
        return getattr(monitor, name)

controller_monitor = _DeprecatedMonitor()

