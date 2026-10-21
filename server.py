import socket
import threading
import json
import time
import math

def cpu_intensive_task(work_units):
    """Calculates primes up to work_units to generate CPU load."""
    primes = 0
    for num in range(2, work_units):
        is_prime = True
        for i in range(2, int(math.sqrt(num)) + 1):
            if num % i == 0:
                is_prime = False
                break
        if is_prime:
            primes += 1
    return primes

def handle_client(conn, addr):
    try:
        data = conn.recv(1024).decode('utf-8')
        if not data: return
        request = json.loads(data)
        
        start_time = time.time()
        result = cpu_intensive_task(request.get("work_units", 10000))
        duration_ms = int((time.time() - start_time) * 1000)
        
        response = {
            "request_id": request.get("request_id", 0),
            "server_id": "server-local",
            "result": result,
            "processing_time_ms": duration_ms
        }
        conn.sendall((json.dumps(response) + "\n").encode('utf-8'))
    except Exception as e:
        pass
    finally:
        conn.close()

def start_server(port=5000):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Bind to 0.0.0.0 so it is reachable from outside the VM later
    server.bind(('0.0.0.0', port))
    server.listen(100)
    print(f"Server listening on 0.0.0.0:{port}...")
    
    while True:
        conn, addr = server.accept()
        thread = threading.Thread(target=handle_client, args=(conn, addr))
        thread.start()

if __name__ == "__main__":
    start_server()
