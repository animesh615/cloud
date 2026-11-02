
import csv
import statistics
from datetime import datetime
from collections import Counter

CPU_FILE = "cpu_metrics.csv"
CLIENT_FILE = "client_metrics.csv"


def load_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


cpu_rows = load_csv(CPU_FILE)
client_rows = load_csv(CLIENT_FILE)

# Find the timestamp at which the autoscaler logged VM2_STARTED.
event_rows = [
    row for row in cpu_rows
    if row.get("scale_out_event") == "VM2_STARTED"
]

if not event_rows:
    raise RuntimeError(
        "VM2_STARTED not found in cpu_metrics.csv. "
        "Run a successful scale-out experiment first."
    )

scale_time = datetime.fromisoformat(
    event_rows[0]["timestamp"]
).timestamp()

# Keep requests from the current experiment only.
requests = []

for row in client_rows:
    try:
        timestamp = float(row["timestamp"])
        latency = float(row["latency_seconds"])
        compute = float(row["compute_seconds"])
    except (ValueError, KeyError):
        continue

    if not row.get("mode") or row["mode"] not in ("low", "high"):
        continue

    requests.append({
        "timestamp": timestamp,
        "mode": row["mode"],
        "server": row["server"],
        "success": row["success"].strip().lower() == "true",
        "latency": latency,
        "compute": compute,
    })

if not requests:
    raise RuntimeError("No valid client request records found.")

# Split the experiment into phases.
phases = {
    "Low load (before scaling)": [
        r for r in requests
        if r["mode"] == "low" and r["timestamp"] < scale_time
    ],
    "High load (before scaling)": [
        r for r in requests
        if r["mode"] == "high" and r["timestamp"] < scale_time
    ],
    "High load (after scale-out)": [
        r for r in requests
        if r["mode"] == "high" and r["timestamp"] >= scale_time
    ],
}


def report_phase(name, rows):
    print(f"\n{name}")
    print("-" * len(name))

    if not rows:
        print("No requests recorded in this phase.")
        return

    rows.sort(key=lambda r: r["timestamp"])

    total = len(rows)
    successful = sum(r["success"] for r in rows)
    latencies = [r["latency"] for r in rows]
    start = rows[0]["timestamp"]
    end = rows[-1]["timestamp"]

    # Approximate observation duration using request timestamps.
    # The last request's interval is estimated using the median
    # inter-arrival time, avoiding division by zero for short phases.
    intervals = [
        rows[i]["timestamp"] - rows[i - 1]["timestamp"]
        for i in range(1, len(rows))
        if rows[i]["timestamp"] > rows[i - 1]["timestamp"]
    ]

    typical_interval = (
        statistics.median(intervals) if intervals else 0
    )
    duration = max(end - start + typical_interval, typical_interval)

    print(f"Requests:          {total}")
    print(f"Successful:        {successful}")
    print(
        f"Success rate:      "
        f"{100 * successful / total:.2f}%"
    )
    print(
        f"Average latency:   "
        f"{statistics.mean(latencies) * 1000:.2f} ms"
    )
    print(
        f"Median latency:    "
        f"{statistics.median(latencies) * 1000:.2f} ms"
    )
    print(
        f"Throughput:        "
        f"{successful / duration:.2f} successful requests/sec"
    )

    print("Requests by server:")
    for server, count in sorted(
        Counter(r["server"] for r in rows).items()
    ):
        print(f"  {server}: {count}")


print("Autoscaling Performance Analysis")
print(f"Scale-out time: {datetime.fromtimestamp(scale_time)}")

for name, rows in phases.items():
    report_phase(name, rows)
