"""A process's macOS memory, read with proc_pid_rusage (rusage_info_v4): its footprint now and its lifetime peak
footprint (what /usr/bin/time -l calls peak memory footprint), and its resident set. No subprocess, so it can be read
every few hundred milliseconds."""
import ctypes
import ctypes.util

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)


class RusageV4(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(f"f{i}", ctypes.c_uint64) for i in range(40)]


# field order after the uuid (sys/resource.h, rusage_info_v4)
_NAMES = ["user_time", "system_time", "pkg_idle_wkups", "interrupt_wkups", "pageins", "wired_size", "resident_size",
          "phys_footprint", "proc_start_abstime", "proc_exit_abstime", "child_user_time", "child_system_time",
          "child_pkg_idle_wkups", "child_interrupt_wkups", "child_pageins", "child_elapsed_abstime", "diskio_bytesread",
          "diskio_byteswritten", "qos_default", "qos_maintenance", "qos_background", "qos_utility", "qos_legacy",
          "qos_user_initiated", "qos_user_interactive", "billed_system_time", "serviced_system_time", "logical_writes",
          "lifetime_max_phys_footprint", "instructions", "cycles", "billed_energy", "serviced_energy",
          "interval_max_phys_footprint", "runnable_time", "flags"]


def usage(pid: int) -> dict | None:
    info = RusageV4()
    if _libc.proc_pid_rusage(int(pid), 4, ctypes.byref(info)) != 0:
        return None
    return {name: getattr(info, f"f{i}") for i, name in enumerate(_NAMES)}


def mib(pid: int) -> tuple[float, float, float] | None:
    """(footprint now, lifetime peak footprint, resident) in MiB."""
    u = usage(pid)
    if u is None:
        return None
    return u["phys_footprint"] / 2**20, u["lifetime_max_phys_footprint"] / 2**20, u["resident_size"] / 2**20


if __name__ == "__main__":
    import sys
    print(mib(int(sys.argv[1])))
