import os
import pandas as pd
import matplotlib.pyplot as plt

CPU_FILE = "cpu_metrics.csv"
OUTPUT_DIR = "graphs"

os.makedirs(OUTPUT_DIR, exist_ok=True)

df = pd.read_csv(CPU_FILE)

required = {
    "elapsed_seconds",
    "vm1_cpu_percent",
    "vm2_cpu_percent",
    "scale_out_event",
}

missing = required - set(df.columns)
if missing:
    raise ValueError(f"Missing CSV columns: {sorted(missing)}")

df["elapsed_seconds"] = pd.to_numeric(
    df["elapsed_seconds"], errors="coerce"
)
df["vm1_cpu_percent"] = pd.to_numeric(
    df["vm1_cpu_percent"], errors="coerce"
)
df["vm2_cpu_percent"] = pd.to_numeric(
    df["vm2_cpu_percent"], errors="coerce"
)
df["scale_out_event"] = df["scale_out_event"].fillna("").astype(str)

fig, ax = plt.subplots(figsize=(12, 6))

ax.plot(
    df["elapsed_seconds"],
    df["vm1_cpu_percent"],
    marker="o",
    markersize=3,
    label="VM1 CPU utilization",
)

ax.plot(
    df["elapsed_seconds"],
    df["vm2_cpu_percent"],
    marker="o",
    markersize=3,
    label="VM2 CPU utilization",
)

events = df[df["scale_out_event"].str.contains(
    "VM2_STARTED", regex=False
)]

for i, event in events.iterrows():
    x = event["elapsed_seconds"]
    ax.axvline(x=x, linestyle="--", label="Scale-out: VM2 started")
    ax.annotate(
        "VM2 started",
        xy=(x, 95),
        xytext=(6, -5),
        textcoords="offset points",
        rotation=90,
        va="top",
    )

ax.set_title("CPU Utilization During Automatic Scale-Out")
ax.set_xlabel("Elapsed time (seconds)")
ax.set_ylabel("CPU utilization (%)")
ax.set_ylim(0, 105)
ax.grid(True, alpha=0.3)
ax.legend()
fig.tight_layout()

output_path = os.path.join(OUTPUT_DIR, "cpu_utilization.png")
fig.savefig(output_path, dpi=200)
plt.close(fig)

print(f"Saved CPU graph to {output_path}")
