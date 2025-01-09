import threading
import time
from speed_test_server import SpeedTestServer
from speed_test_client import SpeedTestClient


def run_server(team_name):
    server = SpeedTestServer()
    print(f"{team_name} server started")
    server.start()


def run_client(team_name, file_size, tcp_conns, udp_conns):
    client = SpeedTestClient()
    print(f"{team_name} client started")

    def input_simulator():
        return f"{file_size}\n{tcp_conns}\n{udp_conns}\n"

    client.start()


# Start servers
threading.Thread(target=run_server, args=("Team Mystic",), daemon=True).start()
# threading.Thread(target=run_server, args=("Team Valor",), daemon=True).start()

# Give servers time to start
time.sleep(2)

# Start clients
client_threads = [
    threading.Thread(target=run_client, args=("Team Instinct", 1024 * 1024 * 1024, 1, 2), daemon=True),
    # threading.Thread(target=run_client, args=("Team Rocket", 1024 * 1024 * 1024, 1, 1), daemon=True),
    # threading.Thread(target=run_client, args=("Team Beitar", 1024 * 1024 * 1024, 2, 1), daemon=True),
    # threading.Thread(target=run_client, args=("Team Katamon", 1024 * 1024 * 1024, 1, 2), daemon=True)
]

for thread in client_threads:
    thread.start()

# Let the test run for a while
test_duration = 60  # seconds
print(f"Test running for {test_duration} seconds...")
time.sleep(test_duration)

print("Test complete. Check the console output for results.")
