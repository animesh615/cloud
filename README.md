Open a terminal and run python3 server.py.

Open a second terminal and run top -p $(pgrep -f server.py) so you can watch the CPU utilization of the server process.

Open a third terminal and run python3 client.py low, then watch the CPU usage in top.

Run python3 client.py high and confirm the CPU spikes significantly. Adjust the work_units and rps variables in the client until the high mode reliably overwhelms a single CPU core.
