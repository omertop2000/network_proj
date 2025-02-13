# client.py
import socket
import struct
import threading
import time
import logging
import colorama
from colorama import Fore, Style
from typing import Tuple, Optional, Dict
from dataclasses import dataclass
import queue

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


@dataclass
class TransferStats:
    """Data class for storing transfer statistics."""
    transfer_type: str
    transfer_num: int
    total_time: float
    speed: float
    packets_received: Optional[float] = None


def _get_user_input() -> Tuple[int, int, int]:
    """Get test parameters from user.
    Prompts user for:
    - File size in bytes
    - Number of TCP connections
    - Number of UDP connections

    Returns:
        Tuple[int, int, int]: File size, TCP connections, UDP connections

    Raises:
        ValueError: If input values are invalid
    """
    while True:
        try:
            print(f"{Fore.CYAN}Please enter the following parameters:{Style.RESET_ALL}")
            file_size = int(input("Enter file size (in bytes): "))
            tcp_conns = int(input("Enter number of TCP connections: "))
            udp_conns = int(input("Enter number of UDP connections: "))

            if file_size <= 0 or tcp_conns < 0 or udp_conns < 0:
                raise ValueError("Values must be positive")

            if tcp_conns == 0 and udp_conns == 0:
                raise ValueError("Must have at least one connection")

            return file_size, tcp_conns, udp_conns
        except ValueError as e:
            print(f"{Fore.RED}Invalid input: {e}{Style.RESET_ALL}")


class SpeedTestClient:
    MAGIC_COOKIE = 0xabcddcba
    OFFER_MESSAGE_TYPE = 0x2
    REQUEST_MESSAGE_TYPE = 0x3
    PAYLOAD_MESSAGE_TYPE = 0x4

    def __init__(self, team_name, broadcast_port: int = 13117):
        """Initialize a new SpeedTestClient instance.
        Sets up client with statistics tracking, logging, and broadcast port
        for server discovery.

        Args:
        broadcast_port (int): Port to listen for server broadcasts. Defaults to 13117.
        """
        self.team_name = team_name
        self.broadcast_port = broadcast_port
        self.running = False
        self.logger = setup_logger('SpeedTestClient', Fore.MAGENTA)
        self.stats_queue: queue.Queue[TransferStats] = queue.Queue()

    def _handle_tcp_transfer(self, server_address: str, server_port: int,
                             file_size: int, transfer_num: int):
        """Handle single TCP file transfer.
        Creates TCP connection, requests file transfer, measures speed
        and updates statistics.
        Args:
            server_address (str): Server IP address
            server_port (int): Server TCP port
            file_size (int): Requested file size in bytes
            transfer_num (int): Transfer identifier number
        """
        try:
            start_time = time.time()

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                # Set a timeout of 2 seconds for the connection attempt
                sock.settimeout(2)
                try:
                    sock.connect((server_address, server_port))
                except socket.timeout:  # server is down although client is given "valid" server_address and server port
                    self.logger.error(f"Connection to {server_address}:{server_port} timed out.")
                    return
                except socket.error as e:
                    self.logger.error(f"Socket error during connection: {e}")
                    return

                # Send file size request
                sock.send(f"{file_size}\n".encode())

                # Receive data
                bytes_received = 0
                while bytes_received < file_size:
                    chunk = sock.recv(8192)
                    if not chunk:
                        break
                    bytes_received += len(chunk)

            end_time = time.time()
            total_time = end_time - start_time
            speed = (file_size * 8) / total_time  # bits per second

            stats = TransferStats(
                transfer_type="TCP",
                transfer_num=transfer_num,
                total_time=total_time,
                speed=speed
            )
            self.stats_queue.put(stats)

        except Exception as e:
            self.logger.error(f"Error in TCP transfer {transfer_num}: {e}")

    def _handle_udp_transfer(self, server_address: str, server_port: int,
                             file_size: int, transfer_num: int):
        """Handle single UDP file transfer.

        Sends UDP request, receives segmented response, tracks packet loss,
        measures speed and updates statistics.

        Args:
            server_address (str): Server IP address
            server_port (int): Server UDP port
            file_size (int): Requested file size in bytes
            transfer_num (int): Transfer identifier number
        """
        try:
            start_time = time.time()

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65535)
                # Send request
                request = struct.pack('!IbQ',
                                      self.MAGIC_COOKIE,
                                      self.REQUEST_MESSAGE_TYPE,
                                      file_size
                                      )
                sock.sendto(request, (server_address, server_port))

                # Receive data
                received_segments: Dict[int, bytes] = {}
                total_segments = None
                last_packet_time = time.time()

                while time.time() - last_packet_time < 1:  # 1 second timeout
                    try:
                        sock.settimeout(1)
                        data, _ = sock.recvfrom(65535)
                        last_packet_time = time.time()

                        # Parse header
                        header_size = struct.calcsize('!IbQQ')
                        magic_cookie, msg_type, total_segs, current_seg = \
                            struct.unpack('!IbQQ', data[:header_size])

                        if magic_cookie != self.MAGIC_COOKIE or \
                                msg_type != self.PAYLOAD_MESSAGE_TYPE:
                            self.logger.warning("Received corrupted UDP packet payout, ignoring...")
                            continue

                        total_segments = total_segs
                        received_segments[current_seg] = data[header_size:]

                    except socket.timeout:
                        continue

            end_time = time.time()
            total_time = end_time - start_time

            # Calculate statistics
            if total_segments is None:
                raise Exception("Never received total segment count")

            packets_received = (len(received_segments) / total_segments) * 100
            speed = (file_size * 8) / total_time  # bits per second

            stats = TransferStats(
                transfer_type="UDP",
                transfer_num=transfer_num,
                total_time=total_time,
                speed=speed,
                packets_received=packets_received
            )
            self.stats_queue.put(stats)

        except Exception as e:
            self.logger.error(f"Error in UDP transfer {transfer_num}: {e}")

    def _print_transfer_stats(self):
        """Print statistics for completed transfers.
        Outputs formatted statistics including:
        - Transfer type (TCP/UDP)
        - Transfer number
        - Total time
        - Transfer speed
        - Packet loss (UDP only)
        """
        while not self.stats_queue.empty():
            stats = self.stats_queue.get()
            if stats.transfer_type == "TCP":
                self.logger.info(
                    f"TCP transfer #{stats.transfer_num} finished, "
                    f"total time: {stats.total_time:.2f} seconds, "
                    f"total speed: {stats.speed:.1f} bits/second"
                )
            else:
                self.logger.info(
                    f"UDP transfer #{stats.transfer_num} finished, "
                    f"total time: {stats.total_time:.2f} seconds, "
                    f"total speed: {stats.speed:.1f} bits/second, "
                    f"percentage of packets received successfully: "
                    f"{stats.packets_received:.1f}%"
                )

    def start(self):
        """Start the speed test client.
        Main client loop that:
        1. Gets user parameters
        2. Listens for server offers
        3. Initiates concurrent transfers
        4. Reports results
        5. Returns to listening state
        Runs until interrupted.
        """
        self.running = True
        self.logger.info("Client started, listening for offer requests...")
        while self.running:
            try:
                # Get user parameters
                # start up phase
                file_size, tcp_conns, udp_conns = _get_user_input()

                # Listen for server offers
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    try:  # for linux os
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                        sock.bind(('', self.broadcast_port))  # client listen on port 13117 for broadcast messages
                    except Exception as ignore:  # for windows os
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                        sock.bind(('', self.broadcast_port))

                    while self.running:
                        data, (server_addr, _) = sock.recvfrom(1024)

                        # Parse offer message
                        try:
                            magic_cookie, msg_type, udp_port, tcp_port = \
                                struct.unpack('!IbHH', data)

                            if magic_cookie != self.MAGIC_COOKIE or \
                                    msg_type != self.OFFER_MESSAGE_TYPE:
                                self.logger.warning("Received corrupted UDP offer packet, ignoring...")
                                continue

                            self.logger.info(f"Received offer from {server_addr},{self.team_name}")

                            # Start transfer threads
                            threads = []

                            # Start TCP transfers
                            for i in range(tcp_conns):
                                thread = threading.Thread(
                                    target=self._handle_tcp_transfer,
                                    args=(server_addr, tcp_port, file_size, i + 1)
                                )
                                thread.start()
                                threads.append(thread)

                            # Start UDP transfers
                            for i in range(udp_conns):
                                thread = threading.Thread(
                                    target=self._handle_udp_transfer,
                                    args=(server_addr, udp_port, file_size, i + 1)
                                )
                                thread.start()
                                threads.append(thread)

                            # Wait for all transfers to complete
                            for thread in threads:
                                thread.join()

                            # Print transfer statistics
                            self._print_transfer_stats()

                            self.logger.info(
                                "All transfers complete, listening to offer requests"
                            )
                            break

                        except struct.error:
                            self.logger.error("Received malformed offer message")
                            continue
                        except Exception as e:
                            self.logger.error(f"Error handling offer: {e}")
                            continue

            except KeyboardInterrupt:
                break

            except Exception as e:
                self.logger.error(f"Error in client main loop: {e}")


def main():
    client = SpeedTestClient("TheIndigenous_server")
    client.start()


if __name__ == "__main__":
    main()
