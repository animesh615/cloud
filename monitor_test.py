
import time
import libvirt

URI = "qemu:///system"
VM_NAME = "ubuntu24.04"
INTERVAL = 5

conn = libvirt.open(URI)
if conn is None:
    raise RuntimeError(f"Could not connect to libvirt: {URI}")

try:
    domain = conn.lookupByName(VM_NAME)

    print(f"Monitoring VM: {VM_NAME}")
    print("Press Ctrl+C to stop.")

    previous_cpu = domain.info()[4]
    previous_time = time.monotonic()

    while True:
        time.sleep(INTERVAL)

        info = domain.info()
        current_cpu = info[4]
        current_time = time.monotonic()

        cpu_delta = current_cpu - previous_cpu
        wall_delta = current_time - previous_time

        if wall_delta > 0 and cpu_delta >= 0:
            # CPU time is in nanoseconds; convert it to seconds.
            cpu_seconds = cpu_delta / 1_000_000_000
            utilization = 100.0 * cpu_seconds / wall_delta

            print(
                f"CPU utilization: {utilization:.1f}% | "
                f"CPU time delta: {cpu_seconds:.3f}s | "
                f"Interval: {wall_delta:.2f}s"
            )

        previous_cpu = current_cpu
        previous_time = current_time

finally:
    conn.close()
