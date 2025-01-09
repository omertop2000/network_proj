import threading
import time
from speed_test_server import SpeedTestServer
from speed_test_client import SpeedTestClient

stop_event = threading.Event()

#we did main to test our classes



def run_server(team_name):
    server = SpeedTestServer(team_name)
    server.start()


def run_client(team_name, file_size, tcp_conns, udp_conns):
    client = SpeedTestClient(team_name)

    def input_simulator():
        return f"{file_size}\n{tcp_conns}\n{udp_conns}\n"

    client.start()


# Start servers
server_threads = [
    threading.Thread(target=run_server, args=("TheIndigenous_server ",), daemon=True),
    threading.Thread(target=run_server, args=("Team Valor",), daemon=True),
    threading.Thread(target=run_server, args=("123 ",), daemon=True),
    threading.Thread(target=run_server, args=("567",), daemon=True),
]

for thread in server_threads:
    thread.start()
# Give servers time to start
time.sleep(2)

# Start clients
client_threads = [
    threading.Thread(target=run_client, args=("TheIndigenous_client", 1024 * 1024 * 1024, 1, 2), daemon=True),
]

for thread in client_threads:
    thread.start()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down...")

# Signal all threads to stop
stop_event.set()

# Wait for all threads to finish
for thread in server_threads + client_threads:
    thread.join()