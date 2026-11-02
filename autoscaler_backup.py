
import time
import json
import csv
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
    state, _, _, _, _ = vm2.info()

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
            return True

        time.sleep(3)

    raise TimeoutError("VM2 did not become healthy in time.")


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

        if vm2.info()[0] == libvirt.VIR_DOMAIN_RUNNING:
            print("Warning: VM2 is already running.")

        previous_cpu = vm1.info()[4]
        previous_time = time.monotonic()

        # Create the CPU metrics CSV.
        cpu_log = open(CPU_LOG_FILE, "w", newline="")
        cpu_writer = csv.writer(cpu_log)

        cpu_writer.writerow([
            "timestamp",
            "elapsed_seconds",
            "vm1_cpu_percent",
            "high_samples",
            "scale_out_event",
        ])
        cpu_log.flush()

        monitor_start = time.time()
        high_samples = 0
        scaled = False

        print(f"Monitoring {VM1_NAME} using libvirt API.")
        print(f"Scale-out threshold: {CPU_THRESHOLD}%")
        print(
            f"Required consecutive high samples: "
            f"{REQUIRED_HIGH_SAMPLES}"
        )
        print("Waiting for sustained overload...")

        while not scaled:
            time.sleep(SAMPLE_INTERVAL)

            if vm1.info()[0] != libvirt.VIR_DOMAIN_RUNNING:
                print("VM1 is not running; stopping monitor.")
                break

            current_cpu = vm1.info()[4]
            current_time = time.monotonic()

            wall_delta = current_time - previous_time
            cpu_delta = current_cpu - previous_cpu

            previous_cpu = current_cpu
            previous_time = current_time

            if wall_delta <= 0 or cpu_delta < 0:
                continue

            # VM1 has exactly one vCPU.
            utilization = (
                (cpu_delta / 1_000_000_000) / wall_delta
            ) * 100.0

            # Update consecutive overload count.
            if utilization >= CPU_THRESHOLD:
                high_samples += 1
            else:
                high_samples = 0

            elapsed = time.time() - monitor_start

            print(f"VM1 CPU: {utilization:.1f}%")

            if utilization >= CPU_THRESHOLD:
                print(
                    f"Overload sample {high_samples}/"
                    f"{REQUIRED_HIGH_SAMPLES}"
                )

            # Record this CPU sample.
            cpu_writer.writerow([
                datetime.now().isoformat(timespec="seconds"),
                round(elapsed, 2),
                round(utilization, 2),
                high_samples,
                "",
            ])
            cpu_log.flush()

            # Scale out after sustained overload.
            if high_samples >= REQUIRED_HIGH_SAMPLES:
                print("Sustained overload detected.")

                start_vm2(conn)

                elapsed = time.time() - monitor_start

                cpu_writer.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    round(elapsed, 2),
                    "",
                    high_samples,
                    "VM2_STARTED",
                ])
                cpu_log.flush()

                scaled = True
                print("Scale-out completed.")

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
