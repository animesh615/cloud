
import argparse
import csv
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

parser = argparse.ArgumentParser()
parser.add_argument("--server", default="http://192.168.122.236:8000")
args = parser.parse_args()

lock = threading.Lock()
servers = [args.server.rstrip("/")]
mode = "stopped"
shutdown = threading.Event()

LOW_RATE = 1       # requests per second
HIGH_RATE = 8      # requests per second
MAX_WORKERS = 16
COMPUTE_N = 100000

csv_lock = threading.Lock()
csv_file = open("client_metrics.csv", "w", newline="")
writer = csv.writer(csv_file)
writer.writerow([
    "timestamp", "server", "success",
    "latency_seconds", "compute_seconds"
])
csv_file.flush()


def send_request(url):
    started = time.perf_counter()
    success = False
    compute_seconds = ""
    server_name = url

    try:
        request_url = f"{url}/compute?n={COMPUTE_N}"
        with urlopen(request_url, timeout=60) as response:
            data = json.loads(response.read().decode())

        server_name = data.get("hostname", url)
        compute_seconds = data.get("compute_seconds", "")
        success = True

    except (URLError, HTTPError, TimeoutError, ValueError, OSError) as exc:
        print(f"\nRequest to {url} failed: {exc}")

    latency = time.perf_counter() - started

    with csv_lock:
        writer.writerow([
            time.time(), server_name, success,
            round(latency, 4), compute_seconds
        ])
        csv_file.flush()

    return success, latency, server_name


class ControlHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/add_server":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            url = payload["url"].rstrip("/")
            parsed = urlparse(url)

            # Accept only HTTP endpoints on the libvirt NAT subnet.
            if (parsed.scheme != "http"
                    or parsed.hostname is None
                    or not parsed.hostname.startswith("192.168.122.")
                    or parsed.port != 8000
                    or parsed.path not in ("", "/")):
                self.send_error(400, "Invalid server URL")
                return

            with lock:
                if url not in servers:
                    servers.append(url)

            body = json.dumps({"servers": servers}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            print(f"\nNew server registered: {url}")

        except Exception as exc:
            self.send_error(400, str(exc))

    def log_message(self, fmt, *args):
        pass


def start_control_server():
    server = ThreadingHTTPServer(("127.0.0.1", 9000), ControlHandler)
    server.timeout = 1

    while not shutdown.is_set():
        server.handle_request()

    server.server_close()


def load_generator():
    executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)
    pending = set()

    try:
        while not shutdown.is_set():
            # Collect completed requests without blocking submission.
            completed = {f for f in pending if f.done()}
            for future in completed:
                pending.remove(future)
                try:
                    ok, latency, hostname = future.result()
                    if ok:
                        pass
                            
                            
                            
                            
                        
                except Exception as exc:
                    print(f"\nWorker error: {exc}")

            with lock:
                current_mode = mode
                current_servers = list(servers)

            if current_mode == "stopped":
                time.sleep(0.1)
                continue

            rate = LOW_RATE if current_mode == "low" else HIGH_RATE
            interval = 1.0 / rate
            started = time.monotonic()

            if len(pending) < MAX_WORKERS:
                # Round-robin distribution across registered servers.
                with lock:
                    index = load_generator.server_index % len(servers)
                    url = servers[index]
                    load_generator.server_index += 1

                pending.add(executor.submit(send_request, url))

            elapsed = time.monotonic() - started
            shutdown.wait(max(0, interval - elapsed))

    finally:
        executor.shutdown(wait=False, cancel_futures=True)


load_generator.server_index = 0

threading.Thread(target=start_control_server, daemon=True).start()
threading.Thread(target=load_generator, daemon=True).start()

print("Client ready. Control endpoint: http://127.0.0.1:9000")
print("Commands: low, high, stop, status, quit")

try:
    while True:
        command = input("> ").strip().lower()

        if command in ("low", "high", "stop"):
            with lock:
                mode = "stopped" if command == "stop" else command
            print(f"Load mode: {mode}")

        elif command == "status":
            with lock:
                print(f"Mode: {mode}")
                print(f"Servers: {servers}")

        elif command == "quit":
            break

        else:
            print("Enter low, high, stop, status, or quit.")

finally:
    shutdown.set()
    csv_file.close()
