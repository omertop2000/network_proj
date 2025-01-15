# server.py
import socket
import struct
import threading
import time
import random
import logging
import colorama
from colorama import Fore, Style
from typing import Tuple

# Initialize colorama for cross-platform ANSI color support
colorama.init()


def setup_logger(name: str, color: str) -> logging.Logger:
    """Set up a colored logger with the specified name and color."""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Check if the logger already has handlers to prevent duplicate handlers
    if not logger.hasHandlers():
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            f'{color}%(asctime)s - %(levelname)s - %(message)s{Style.RESET_ALL}'
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger


def get_server_ip():
    hostname = socket.gethostname()
    ip_address = socket.gethostbyname(hostname)
    return ip_address


def _get_random_port() -> int:
    """Get an available random port number.

    Returns:
        int: An available port number that can be used for TCP or UDP connections.
    """
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class SpeedTestServer:
    MAGIC_COOKIE = 0xabcddcba
    OFFER_MESSAGE_TYPE = 0x2
    REQUEST_MESSAGE_TYPE = 0x3
    PAYLOAD_MESSAGE_TYPE = 0x4

    def __init__(self, team_name, broadcast_port: int = 13117):
        """Initialize a new SpeedTestServer instance.

        Sets up the server with random TCP and UDP ports, initializes logging,
        and sets the broadcast port for server discovery.

        Args:
            broadcast_port (int): Port number for broadcasting server offers. Defaults to 13117.
        """
        self.team_name = team_name
        self.ip_address = get_server_ip()
        self.broadcast_port = broadcast_port
        self.tcp_port = _get_random_port()
        self.udp_port = _get_random_port()
        self.running = False
        self.logger = setup_logger('SpeedTestServer', Fore.CYAN)

    def _create_offer_message(self) -> bytes:
        """Create a formatted offer message for broadcasting.

        Creates a binary message containing:
        - Magic cookie (4 bytes)
        - Message type (1 byte)
        - UDP port (2 bytes)
        - TCP port (2 bytes)

        Returns:
            bytes: Formatted binary offer message ready for broadcasting.
        """
        return struct.pack('!IbHH',
                           self.MAGIC_COOKIE,
                           self.OFFER_MESSAGE_TYPE,
                           self.udp_port,
                           self.tcp_port
                           )

    def _broadcast_offers(self):
        """Continuously broadcast server offers over UDP.

        Runs in a separate thread, sending offer messages every second until
        server is stopped. Uses UDP broadcast to reach all potential clients
        on the network.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while self.running:
                try:
                    self.logger.info(f"Server started, listening on IP address {self.ip_address}")
                    sock.sendto(self._create_offer_message(),
                                ('<broadcast>', self.broadcast_port))  # broadcast_port is destination port for broadcasting which the client listens on
                    time.sleep(1)
                except Exception as e:
                    self.logger.error(f"Error broadcasting offer: {e}")

    def _handle_tcp_client(self, client_socket: socket.socket,
                           address: Tuple[str, int]):
        """Handle individual TCP client connections.

        Receives requested file size from client and streams random data
        in response.

        Args:
            client_socket (socket.socket): Connected client socket
            address (Tuple[str, int]): Client's address and port

        Notes:
            Closes client socket when transfer is complete or on error.
        """
        try:
            client_socket.settimeout(2)
            # Receive the requested file size
            size_str = client_socket.recv(1024).decode().strip()
            file_size = int(size_str)

            # Generate and send random data
            bytes_sent = 0
            chunk_size = 8192

            while bytes_sent < file_size:
                remaining = file_size - bytes_sent
                current_chunk = min(chunk_size, remaining)
                data = random.randbytes(current_chunk)
                client_socket.sendall(data)
                bytes_sent += current_chunk

            self.logger.info(
                f"Completed TCP transfer of {file_size} bytes to {address},{self.team_name}")

        except Exception as e:
            self.logger.error(f"Error handling TCP client {address}: {e}")
        except socket.timeout:
            self.logger.error(f"Client {address} timed out due to inactivity.")
        finally:
            client_socket.close()

    def _handle_udp_client(self, request: bytes, address: Tuple[str, int]):
        """Handle individual UDP client requests with optimized segment size."""
        try:
            # Parse request
            magic_cookie, msg_type, file_size = struct.unpack('!IbQ', request)

            if magic_cookie != self.MAGIC_COOKIE or msg_type != self.REQUEST_MESSAGE_TYPE:
                self.logger.warning("Received request corrupted UDP packet, ignoring...")
                return

            # Set maximum feasible segment size
            segment_size = 64000  # Close to UDP max size (65,535 bytes - headers)
            total_segments = (file_size + segment_size - 1) // segment_size

            # Pre-generate a payload of max size for efficiency
            payload = b'\x00' * segment_size

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                # Increase socket buffer size for large packets
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65535)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65535)

                header_base = struct.pack('!IbQ', self.MAGIC_COOKIE, self.PAYLOAD_MESSAGE_TYPE, total_segments)

                for segment in range(total_segments):
                    remaining = file_size - (segment * segment_size)
                    current_chunk_size = min(segment_size, remaining)

                    # Trim payload to the current chunk size
                    packet_payload = payload[:current_chunk_size]

                    # Create packet with header and payload
                    header = header_base + struct.pack('!Q', segment)
                    packet = header + packet_payload

                    # Send the packet
                    sock.sendto(packet, address)

            self.logger.info(f"Completed UDP transfer of {file_size} bytes to {address}, {self.team_name}")

        except Exception as e:
            self.logger.error(f"Error handling UDP client {address}: {e}")

    def _start_tcp_server(self):
        """Start TCP server to handle client connections.

            Listens for incoming TCP connections and spawns handler thread
            for each new client. Runs until server is stopped.
            """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('', self.tcp_port))
            sock.listen(5)

            while self.running:
                try:
                    client_socket, address = sock.accept()  # thread is sleeping until client initiates connection
                    thread = threading.Thread(
                        target=self._handle_tcp_client,
                        args=(client_socket, address)
                    )
                    thread.daemon = True
                    thread.start()
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error accepting TCP connection: {e}")

    def _start_udp_server(self):
        """Start UDP server to handle client requests.

        Listens for incoming UDP requests and spawns handler thread
        for each new client. Runs until server is stopped.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.bind(('', self.udp_port))

            while self.running:
                try:
                    data, address = sock.recvfrom(1024)  # listening to client's udp requests at this channel
                    thread = threading.Thread(  # initiating a new thread to handle multiple clients simultaneously
                        target=self._handle_udp_client,
                        args=(data, address)
                        # data is the client's request message, address is referring to the client connected to the socket
                    )
                    thread.daemon = True
                    thread.start()
                except Exception as e:
                    if self.running:
                        self.logger.error(f"Error handling UDP request: {e}")

    def start(self):
        """Start the speed test server.

        Launches three daemon threads:
        - Broadcast thread for sending offers
        - TCP server thread for handling TCP connections
        - UDP server thread for handling UDP requests

        Displays server IP address and runs until interrupted.
        """
        self.running = True

        # Start broadcast thread
        broadcast_thread = threading.Thread(target=self._broadcast_offers)
        broadcast_thread.daemon = True
        broadcast_thread.start()

        # Start TCP server thread
        tcp_thread = threading.Thread(target=self._start_tcp_server)
        tcp_thread.daemon = True
        tcp_thread.start()

        # Start UDP server thread
        udp_thread = threading.Thread(target=self._start_udp_server)
        udp_thread.daemon = True
        udp_thread.start()


        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return


def main():
    server = SpeedTestServer("TheIndigenous_server")
    server.start()


if __name__ == "__main__":
    main()
