
import csv
import json
import time
import urllib.request
import urllib.error
import libvirt
from datetime import datetime

# Configuration
LIBVIRT_URI = "qemu:///system"
VM1_NAME = "ubuntu24.04"
VM2_NAME = "server2"

VM2_URL = "http://192.168.122.237:8000"
CLIENT_NOTIFY_URL = "http://127.0.0.1:9000/add_server"

CPU_THRESHOLD = 80.0
SAMPLE_INTERVAL = 5
REQUIRED_HIGH_SAMPLES = 3
HEALTH_TIMEOUT = 180
CPU_LOG_FILE = "cpu_metrics.csv"


def get_health(url, timeout=2):
    try:
        with urllib.request.urlopen(
            url + "/health", timeout=timeout
        ) as response:
            return response.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def notify_client():
    payload = json.dumps({"url": VM2_URL}).encode()

    request = urllib.request.Request(
        CLIENT_NOTIFY_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=5) as response:
        print("Client notified:", response.read().decode())


def start_vm2(conn):
    vm2 = conn.lookupByName(VM2_NAME)
    state = vm2.info()[0]

    if state != libvirt.VIR_DOMAIN_RUNNING:
        print(f"Starting {VM2_NAME} through the libvirt API...")
        vm2.create()
    else:
        print(f"{VM2_NAME} is already running.")

    deadline = time.monotonic() + HEALTH_TIMEOUT

    while time.monotonic() < deadline:
        if get_health(VM2_URL):
            print("VM2 health check passed.")
            notify_client()
            return

        time.sleep(3)

    raise TimeoutError("VM2 did not become healthy in time.")


def cpu_percent(domain, previous_cpu, previous_time):
    """Return current CPU percentage and updated counters."""
    info = domain.info()
    current_cpu = info[4]
    current_time = time.monotonic()

    wall_delta = current_time - previous_time
    cpu_delta = current_cpu - previous_cpu

    if wall_delta <= 0 or cpu_delta < 0:
        return None, current_cpu, current_time

    # Each VM has exactly one vCPU.
    utilization = (
        (cpu_delta / 1_000_000_000) / wall_delta
    ) * 100.0

    return min(utilization, 100.0), current_cpu, current_time


def main():
    conn = libvirt.open(LIBVIRT_URI)

    if conn is None:
        raise RuntimeError("Could not connect to libvirt.")

    cpu_log = None

    try:
        vm1 = conn.lookupByName(VM1_NAME)
        vm2 = conn.lookupByName(VM2_NAME)

        if vm1.info()[0] != libvirt.VIR_DOMAIN_RUNNING:
            raise RuntimeError(f"{VM1_NAME} must be running.")

        scaled = vm2.info()[0] == libvirt.VIR_DOMAIN_RUNNING

        if scaled:
            print("Warning: VM2 is already running.")

        # Independent CPU counters for each VM.
        previous_cpu = {
            VM1_NAME: vm1.info()[4],
            VM2_NAME: vm2.info()[4] if scaled else None,
        }

        previous_time = {
            VM1_NAME: time.monotonic(),
            VM2_NAME: time.monotonic() if scaled else None,
        }

        high_samples = 0
        monitor_start = time.monotonic()

        cpu_log = open(CPU_LOG_FILE, "w", newline="")
        writer = csv.writer(cpu_log)

        writer.writerow([
            "timestamp",
            "elapsed_seconds",
            "vm1_cpu_percent",
            "vm2_cpu_percent",
            "high_samples",
            "scale_out_event",
        ])
        cpu_log.flush()

        print(f"Monitoring {VM1_NAME} using libvirt API.")
        print(f"Scale-out threshold: {CPU_THRESHOLD}%")
        print("Press Ctrl+C to stop monitoring.")

        while True:
            time.sleep(SAMPLE_INTERVAL)

            if vm1.info()[0] != libvirt.VIR_DOMAIN_RUNNING:
                print("VM1 is not running; stopping monitor.")
                break

            vm1_cpu, previous_cpu[VM1_NAME], previous_time[VM1_NAME] = (
                cpu_percent(
                    vm1,
                    previous_cpu[VM1_NAME],
                    previous_time[VM1_NAME],
                )
            )

            vm2_cpu = None

            if scaled and vm2.info()[0] == libvirt.VIR_DOMAIN_RUNNING:
                (
                    vm2_cpu,
                    previous_cpu[VM2_NAME],
                    previous_time[VM2_NAME],
                ) = cpu_percent(
                    vm2,
                    previous_cpu[VM2_NAME],
                    previous_time[VM2_NAME],
                )

            elapsed = time.monotonic() - monitor_start
            event = ""

            if vm1_cpu is not None:
                print(f"VM1 CPU: {vm1_cpu:.1f}%")

            if vm2_cpu is not None:
                print(f"VM2 CPU: {vm2_cpu:.1f}%")

            if not scaled and vm1_cpu is not None:
                if vm1_cpu >= CPU_THRESHOLD:
                    high_samples += 1
                    print(
                        f"Overload sample {high_samples}/"
                        f"{REQUIRED_HIGH_SAMPLES}"
                    )
                else:
                    high_samples = 0

                if high_samples >= REQUIRED_HIGH_SAMPLES:
                    print("Sustained overload detected.")

                    start_vm2(conn)
                    scaled = True
                    event = "VM2_STARTED"

                    # Initialize VM2's counters after it is healthy.
                    previous_cpu[VM2_NAME] = vm2.info()[4]
                    previous_time[VM2_NAME] = time.monotonic()

                    print("Scale-out completed.")
            elif scaled:
                print("Scale-out active; monitoring both VMs.")

            writer.writerow([
                datetime.now().isoformat(timespec="seconds"),
                round(elapsed, 2),
                "" if vm1_cpu is None else round(vm1_cpu, 2),
                "" if vm2_cpu is None else round(vm2_cpu, 2),
                high_samples,
                event,
            ])
            cpu_log.flush()

    finally:
        if cpu_log is not None and not cpu_log.closed:
            cpu_log.close()

        conn.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAutoscaler stopped.")
    except Exception as exc:
        print(f"Autoscaler error: {exc}")
