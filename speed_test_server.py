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


class SpeedTestServer:
    MAGIC_COOKIE = 0xabcddcba
    OFFER_MESSAGE_TYPE = 0x2
    REQUEST_MESSAGE_TYPE = 0x3
    PAYLOAD_MESSAGE_TYPE = 0x4

    def __init__(self, team_name,broadcast_port: int = 13117):
        """Initialize the speed test server."""
        self.team_name = team_name
        self.broadcast_port = broadcast_port
        self.tcp_port = self._get_random_port()
        self.udp_port = self._get_random_port()
        self.running = False
        self.logger = setup_logger('SpeedTestServer', Fore.CYAN)

    def _get_random_port(self) -> int:
        """Get a random available port."""
        with socket.socket() as s:
            s.bind(('', 0))
            return s.getsockname()[1]

    def _create_offer_message(self) -> bytes:
        """Create an offer message according to the specified format."""
        return struct.pack('!IbHH',
                           self.MAGIC_COOKIE,
                           self.OFFER_MESSAGE_TYPE,
                           self.udp_port,
                           self.tcp_port
                           )

    def _broadcast_offers(self):
        """Continuously broadcast offer messages."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            while self.running:
                try:
                    sock.sendto(self._create_offer_message(),
                                ('<broadcast>', self.broadcast_port))
                    time.sleep(1)
                except Exception as e:
                    self.logger.error(f"Error broadcasting offer: {e}")

    def _handle_tcp_client(self, client_socket: socket.socket,
                           address: Tuple[str, int]):
        """Handle TCP client connections."""
        try:
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
                f"Completed TCP transfer of {file_size} bytes to {address},{self.team_name}"
            )

        except Exception as e:
            self.logger.error(f"Error handling TCP client {address}: {e}")
        finally:
            client_socket.close()

    def _handle_udp_client(self, request: bytes, address: Tuple[str, int]):
        """Handle UDP client requests."""
        try:
            # Parse request
            magic_cookie, msg_type, file_size = struct.unpack('!IbQ', request)

            if magic_cookie != self.MAGIC_COOKIE or msg_type != self.REQUEST_MESSAGE_TYPE:
                self.logger.warning("Received request corrupted UDP packet, ignoring...")
                return

            # Calculate total segments
            segment_size = 1024
            total_segments = (file_size + segment_size - 1) // segment_size

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                for segment in range(total_segments):
                    remaining = file_size - (segment * segment_size)
                    current_chunk = min(segment_size, remaining)

                    # Create payload packet
                    header = struct.pack('!IbQQ',
                                         self.MAGIC_COOKIE,
                                         self.PAYLOAD_MESSAGE_TYPE,
                                         total_segments,
                                         segment
                                         )

                    payload = random.randbytes(current_chunk)
                    packet = header + payload

                    sock.sendto(packet, address)
                    time.sleep(0.001)  # Small delay to prevent overwhelming the network

            self.logger.info(
                f"Completed UDP transfer of {file_size} bytes to {address}"
            )

        except Exception as e:
            self.logger.error(f"Error handling UDP client {address}: {e}")

    def _start_tcp_server(self):
        """Start TCP server to handle client connections."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(('', self.tcp_port))
            sock.listen(5)

            while self.running:
                try:
                    client_socket, address = sock.accept()
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
        """Start UDP server to handle client requests."""
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
        """Start the speed test server."""
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

        # Get local IP address
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)
        #change this print later
        self.logger.info(f"Server started, listening on IP address {ip_address},{self.team_name}")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            return

