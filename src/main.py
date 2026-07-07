"""
Captive Portal

Provide network services needed for a captive wifi portal: access point, DNS, & HTTP.
Each service provides only the bare minimum functionality needed to serve a single
informational HTML page. Authentication and internet connection are not supported.
"""

import machine
import os
import errno
import network
import asyncio
import socket
import time


def apd(ssid):
    """
    Bring up an open (no password) wifi access point with the given name.

    Args:
        ssid (string): The wifi access point name to broadcast.
    Returns:
        string: IP address of access point as a dotted quad string.
    """
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    ap.config(ssid=ssid, authmode=network.AUTH_OPEN)
    server_ip = ap.ifconfig()[0]
    print(f"SSID: {ssid}")
    print(f"IP address: {server_ip}")
    return server_ip


def dns_reply(query_packet, reply_ip, udp_socket, client_address):
    """
    Respond to a DNS lookup giving reply_ip as the result of the query.

    Args:
        query_packet (bytes): Original DNS query packet to include with the reply.
        reply_ip (string): Dotted-quad IPv4 address to send in response to the query.
        udp_socket (socket): DNS listener socket for sending the reply.
        client_address (tuple): IP and port of the client who sent the query.
    """
    reply_ip_bytes = bytes(int(octet) for octet in reply_ip.split("."))
    reply_part = b"\xc0\x0c"  # Use offset to indicate response is for the original name.
    reply_part += b"\x00\x01"  # Reply type is an A record.
    reply_part += b"\x00\x01"  # Reply class is Internet.
    reply_part += (0).to_bytes(4, "big")  # Zero time to live (TTL) avoids poisoning.
    reply_part += b"\x00\x04"  # Length of reply will be 4 octets (IPv4 address.)
    reply_part += reply_ip_bytes  # IPv4 address represented as 4 bytes (octets.)
    reply_packet = bytearray(query_packet)  # DNS includes original for reference.
    reply_packet[2:4] = b"\x81\x00"  # Adjust flags: query answer, no server recusion, no errors.
    reply_packet[6:8] = b"\x00\x01"  # Indicate a single answer follows.
    reply_packet.extend(reply_part)  # Tack on the reply part.
    print(f"DNS response: {reply_packet.hex()}")
    try:
        udp_socket.sendto(reply_packet, client_address)
    except OSError as e:
        print(f"OSError: {e}")
        print("Frankie say: Panic!")
        machine.reset()


async def named(reply_ip):
    """
    A DNS server that responds to all A record queries with the same IPv4 address.

    Args:
        reply_ip (string): Dotted-quad IPv4 address given for all replies.

    References:
        https://courses.cs.duke.edu/fall16/compsci356/DNS/DNS-primer.pdf
        https://github.com/belyalov/tinydns/blob/master/tinydns/dns.py
    """
    sock_address = socket.getaddrinfo(reply_ip, 53)[0][-1]  # Port 53
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # Datagram (UDP)
    sock.bind(sock_address)
    sock.setblocking(False)  # Don't block, because that will hold up asyncio loop.
    print(f"named listening on {sock_address}")

    while True:
        try:
            query_packet, client_addr = sock.recvfrom(1024)
            print(f"DNS query received from {client_addr}: {query_packet.hex()}")
        except OSError as e:
            if e.errno == errno.EAGAIN:  # Means: "no data available, try again"
                pass
            elif e.errno == errno.ETIMEDOUT:
                pass
            else:
                print(f"OSError: {e}")
                print("Frankie say: Panic!")
                machine.reset()
        else:
            # Deconstruct the query packet for validation.
            flags = query_packet[2:4]
            num_questions = query_packet[4:6]
            name_end = query_packet[-5:-4]
            qtype = query_packet[-4:-2]
            qclass = query_packet[-2:]
            # Expecting a standard query for a single Internet A record (ex. connectivitycheck.gstatic.com)
            # though the actual host name is ignored, because the response will always the same.
            if (
                flags == b"\x01\x00"  # Query with recursion
                and num_questions == b"\x00\x01"  # Single host lookup
                and name_end == b"\x00"  # Length field that signals end
                and qtype == b"\x00\x01"  # IPv4 Address (A) record
                and qclass == b"\x00\x01"  # Internet address
            ):
                dns_reply(query_packet, reply_ip, sock, client_addr)

        await asyncio.sleep_ms(100)


def read_file_chunk(file):
    """
    Given a file handle, read the file in small chunks to avoid large buffer requirements.

    Args:
        file (object): The file handle returned by open().

    Returns:
        bytes: A chunk of the file until the file ends, then nothing.
    """
    while True:
        chunk = file.read(512)  # small chunks to avoid out of memory errors
        if chunk:
            yield chunk
        else:  # empty chunk means end of the file
            return


async def http_reply(file_path, redirect_ip, connection):
    """
    Serve HTML files from the local flash if they exist. Reply with a 307 redirect
    to http://redirect_ip/portal.html for any file not found. As a captive portal,
    that's pretty much any page other than portal.html.

    Args:
        redirect_ip (string): Dotted-quad IPv4 address to use for 307 redirects.
        file_path (string): Full path to HTML file being requested.
        connection (socket): The TCP socket to use for sending replies.
    """
    if file_path.endswith("/"):
        file_path += "index.html"
    try:
        size = os.stat(file_path)[6]  # Also determines if file exists.
    except OSError as e:
        print(f"Unable to access file {file_path}: {e}")
        size = None

    if size is None:
        print("Redirecting to portal page.")
        connection.send("HTTP/1.1 307 Temporary Redirect\r\n")
        connection.send(f"Location: http://{redirect_ip}/portal.html\r\n")
        connection.send("Content-Length: 0\r\n")
        connection.send("Content-Type: text/html\r\n")
        connection.send("\r\n")  # Empty line signals end of headers
    else:
        print(f"Sending {file_path}")
        if file_path.endswith(".html"):
            content_type="text/html"
        elif file_path.endswith(".ico"):
            content_type = "image/x-icon"
        else:
            content_type = "text/html"
        connection.send("HTTP/1.1 200 OK\r\n")
        connection.send("Connection: close\r\n")
        connection.send(f"Content-Length: {size}\r\n")
        connection.send(f"Content-Type: {content_type}\r\n")
        connection.send("\r\n")
        try:
            with open(file_path, 'rb') as file:
                for chunk in read_file_chunk(file):
                    connection.send(chunk)
        except OSError as e:
            print(f"Unable to send file {file_path}: {e}")

    connection.close()


async def httpd(server_ip):
    """
    A simple HTTP server to deliver a single HTML document, the captive portal informational page,
    for any GET request.

    Args:
        server_ip (string): IPv4 address in dotted quad notation
    """
    sock_address = socket.getaddrinfo(server_ip, 80)[0][-1]  # Port 80
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP Stream
    sock.bind(sock_address)
    sock.setblocking(False)
    sock.listen(5)
    print(f"httpd listening on {sock_address}")
    while True:
        try:
            connection, client_address = sock.accept()
        except OSError as e:
            if e.errno == errno.EAGAIN:
                pass  # EAGAIN means: "no data available, try again"
            elif e.errno == errno.ETIMEDOUT:
                pass
            else:
                print(f"OSError: {e}")
                print("Frankie say: Panic!")
                machine.reset()
        else:
            print(f"HTTP connection from: {client_address}")
            request_bytes = connection.recv(1024)
            try:
                request_string = request_bytes.decode('utf8')
            except UnicodeError:
                print(f"Bad HTTP request: {e}. Closing connection.")
                connection.close()
            else:
                request_lines = request_string.split('\r\n')
            try:
                method, target, http_version = request_lines[0].split(' ', 2)
            except ValueError as e:
                print(f"Bad HTTP request: {e}. Closing connection.")
                connection.close()
            else:
                print(f"HTTP request: {method} {target}")
                if method == "GET":
                    await http_reply(target, server_ip, connection)

        await asyncio.sleep_ms(100)


async def heartbeat(interval):
    """
    Print an uptime message every so often as proof things are still working.

    Args: interval (int): seconds to wait between heartbeat messages
    """
    while True:
        print(f"Uptime {time.time()} seconds.")
        await asyncio.sleep(interval)


async def captive_portal(portal_ip):
    await asyncio.gather(named(portal_ip), httpd(portal_ip), heartbeat(60))


if __name__ == "__main__":
    portal_ip = apd("Protect Trans Kids")
    asyncio.run(captive_portal(portal_ip))
