# Network Speed Test Client-Server Application

A client-server application for testing network speeds by comparing UDP and TCP downloads over shared networks.

## Overview

This application implements a speed test system where servers broadcast their availability and clients can request and measure file transfers using both TCP and UDP protocols simultaneously. The system measures transfer speeds, packet loss rates for UDP, and allows multiple concurrent connections.

## Architecture

### Server
- Multi-threaded design with three main components:
  - Offer broadcaster: Continuously sends UDP broadcast messages advertising server availability
  - TCP handler: Accepts connections and serves requested file sizes
  - UDP handler: Processes requests and sends segmented data packets
- Supports multiple simultaneous client connections
- Implements error handling for network failures and invalid requests

### Client
- Multi-threaded implementation with three states:
  - Startup: Parameter collection from user
  - Server discovery: Listening for broadcast offers
  - Speed test: Managing concurrent TCP/UDP transfers
- Measures and reports transfer speeds and packet loss statistics
- Supports multiple simultaneous connections to servers

## Protocol Specification

### Message Types
1. Offer Message (Server → Client)
   - Magic cookie (4 bytes): 0xabcddcba
   - Message type (1 byte): 0x2
   - Server UDP port (2 bytes)
   - Server TCP port (2 bytes)

2. Request Message (Client → Server)
   - Magic cookie (4 bytes): 0xabcddcba
   - Message type (1 byte): 0x3
   - File size (8 bytes)

3. Payload Message (Server → Client)
   - Magic cookie (4 bytes): 0xabcddcba
   - Message type (1 byte): 0x4
   - Total segment count (8 bytes)
   - Current segment count (8 bytes)
   - Payload data (variable size)

### TCP Protocol
- Client sends requested file size as string followed by "\n"
- Server responds with continuous data stream

## Key Features

- Dynamic server discovery via UDP broadcast
- Concurrent TCP and UDP transfers
- Real-time speed measurements
- Packet loss tracking for UDP transfers
- ANSI color-coded console output
- Comprehensive error handling
- Cross-platform compatibility

## Requirements

- Python 3.x
- Required packages:
  - colorama (for cross-platform ANSI color support)
- Network access with UDP broadcast capability
- Support for socket SO_REUSEPORT option

## Usage

### Server
```python
from speed_test_server import SpeedTestServer

server = SpeedTestServer()
server.start()
```

### Client
```python
from speed_test_client import SpeedTestClient

client = SpeedTestClient()
client.start()
```

## Error Handling

- Invalid packet detection using magic cookie
- Timeout handling for UDP transfers
- Socket reuse for multiple instances
- Network failure recovery
- Input validation for user parameters

## Performance Considerations

- No busy-waiting loops
- Efficient thread management
- Proper socket cleanup
- Memory-efficient data transfer
