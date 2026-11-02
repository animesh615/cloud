from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import math
import socket
import time


def count_primes(n):
    """CPU-intensive computation: count primes up to n."""
    count = 0

    for x in range(2, n + 1):
        is_prime = True

        for d in range(2, math.isqrt(x) + 1):
            if x % d == 0:
                is_prime = False
                break

        if is_prime:
            count += 1

    return count


class Handler(BaseHTTPRequestHandler):
    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self.send_json(200, {
                "status": "ok",
                "hostname": socket.gethostname()
            })
            return

        if parsed.path == "/compute":
            params = parse_qs(parsed.query)

            try:
                n = int(params.get("n", ["50000"])[0])
                if not 2 <= n <= 500000:
                    raise ValueError()
            except ValueError:
                self.send_json(400, {"error": "n must be between 2 and 500000"})
                return

            start = time.perf_counter()
            result = count_primes(n)
            elapsed = time.perf_counter() - start

            self.send_json(200, {
                "hostname": socket.gethostname(),
                "n": n,
                "primes": result,
                "compute_seconds": round(elapsed, 4)
            })
            return

        self.send_json(404, {"error": "not found"})

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} - {fmt % args}", flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    print("Server listening on port 8000", flush=True)
    server.serve_forever()
