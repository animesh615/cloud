import socket
import threading
import json
import time
import sys

# Server registry (will be updated dynamically by the autoscaler later)
servers = [("127.0.0.1", 5000)]
server_index = 0
registry_lock = threading.Lock()

stats = {"completed": 0, "failed": 0, "total_latency": 0.0}
stats_lock = threading.Lock()

def get_next_server():
    global server_index
    with registry_lock:
        server = servers[server_index % len(servers)]
        server_index += 1
        return server

def send_request(request_id, work_units):
    server_ip, server_port = get_next_server()
    try:
        start_time = time.time()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(5.0)
        s.connect((server_ip, server_port))
        
        req = {"request_id": request_id, "work_units": work_units}
        s.sendall(json.dumps(req).encode('utf-8'))
        
        data = s.recv(1024).decode('utf-8')
        latency = time.time() - start_time
        
        with stats_lock:
            stats["completed"] += 1
            stats["total_latency"] += latency
    except Exception as e:
        with stats_lock:
            stats["failed"] += 1
    finally:
        s.close()

def run_load_test(rps, work_units, duration):
    print(f"Sending {rps} req/sec for {duration}s (Work units: {work_units})")
    threads = []
    
    for i in range(rps * duration):
        t = threading.Thread(target=send_request, args=(i, work_units))
        threads.append(t)
        t.start()
        time.sleep(1.0 / rps)
        
    for t in threads:
        t.join()
        
    avg_latency = (stats["total_latency"] / stats["completed"]) if stats["completed"] > 0 else 0
    print(f"\n--- Results ---")
    print(f"Completed: {stats['completed']}")
    print(f"Failed:    {stats['failed']}")
    print(f"Avg Latency: {avg_latency:.3f}s")

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "low"
    
    # Adjust work_units based on how fast your Linux CPU is
    work_units = 50000 
    duration = 10
    
    if mode == "high":
        rps = 10
    else:
        rps = 2
        
    run_load_test(rps, work_units, duration)
