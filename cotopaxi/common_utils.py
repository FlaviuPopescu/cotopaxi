# -*- coding: utf-8 -*-
"""Set of common utils used by different Cotopaxi tools."""
#
#    Copyright (C) 2020 Samsung Electronics. All Rights Reserved.
#       Authors: Jakub Botwicz (Samsung R&D Poland),
#                Michał Radwański (Samsung R&D Poland)
#
#    This file is part of Cotopaxi.
#
#    Cotopaxi is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 2 of the License, or
#    (at your option) any later version.
#
#    Cotopaxi is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Cotopaxi.  If not, see <http://www.gnu.org/licenses/>.
#

import random
import socket
import ssl
import sys
from enum import Enum

from scapy.all import DNS, IP, TCP, UDP, IPv6, Raw, sr1
from scapy.layers.http import HTTPRequest
from scapy.contrib.coap import CoAP
from scapy.contrib.mqtt import MQTT
from scapy_ssl_tls.ssl_tls import DTLSRecord as DTLS

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO

# Default size of input buffer
INPUT_BUFFER_SIZE = 10000

# IPv4 address used for SSDP multicast communication
SSDP_MULTICAST_IPV4 = "239.255.255.250"

# Minimum number of private (ephemeral or high) port for TCP and UDP protocols
NET_MIN_HIGH_PORT = 49152

# Maximal number of port for TCP and UDP protocols
NET_MAX_PORT = 65535


def get_local_ip():
    """Returns IP address of local node."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.connect(("1.255.255.255", 80))
    local_ip = sock.getsockname()[0]
    sock.close()
    return local_ip


def get_local_ipv6_address():
    """Returns IPv6 address of local node."""
    sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
    sock.connect(("::1", 80))
    local_ip = sock.getsockname()[0]
    sock.close()
    return local_ip


def get_random_high_port():
    """Returns random value for private (ephemeral or high) TCP or UDP port."""
    return random.randint(NET_MIN_HIGH_PORT, NET_MAX_PORT)


def print_verbose(test_params, message):
    """Prints messages displayed only in the verbose/debug mode."""
    if test_params.verbose:
        print (message)


def show_verbose(test_params, packet, protocol=None):
    """Parses response packet and scraps response from stdout."""
    if protocol:
        try:
            proto_handler = proto_mapping_request(protocol)
            packet = proto_handler(packet)
        except KeyError:
            return "Response is not parsable!"
    parsed_response = ""
    if test_params.verbose:
        capture = StringIO()
        save_stdout, sys.stdout = sys.stdout, capture
        packet.show()
        sys.stdout = save_stdout
        parsed_response = capture.getvalue()
    return parsed_response


def scrap_packet(packet):
    """Parses response packet and scraps response from stdout."""
    capture = StringIO()
    save_stdout, sys.stdout = sys.stdout, capture
    packet.show()
    sys.stdout = save_stdout
    parsed_response = capture.getvalue()
    return parsed_response


class Protocol(Enum):
    """Enumeration of protocols supported by Cotopaxi"""

    ALL = 0
    UDP = 1
    TCP = 2
    CoAP = 3
    MQTT = 4
    DTLS = 5
    mDNS = 6
    SSDP = 7
    HTCPCP = 8
    RTSP = 9
    HTTP = 10
    FTP = 11
    QUIC = 12


def proto_mapping_request(protocol):
    """Provides mapping of enum values to implementation classes."""
    return {
        Protocol.ALL: IP,
        Protocol.UDP: UDP,
        Protocol.TCP: TCP,
        Protocol.CoAP: CoAP,
        Protocol.mDNS: DNS,
        Protocol.MQTT: MQTT,
        Protocol.DTLS: DTLS,
        Protocol.QUIC: UDP,
        Protocol.RTSP: HTTPRequest,
        Protocol.SSDP: HTTPRequest,
        Protocol.HTCPCP: HTTPRequest,
        Protocol.HTTP: HTTPRequest,
    }[protocol]


def tcp_sr1(test_params, test_packet):
    """Sends test message to server using TCP protocol and parses response."""
    in_data = None
    connect_handler = None
    sent_time = test_params.report_sent_packet()

    sock_ip = {4: socket.AF_INET, 6: socket.AF_INET6}
    connect_args = {
        4: (test_params.dst_endpoint.ip_addr, test_params.dst_endpoint.port),
        6: (test_params.dst_endpoint.ip_addr, test_params.dst_endpoint.port, 0, 0),
    }
    try:
        connect_handler = socket.socket(
            sock_ip[test_params.ip_version], socket.SOCK_STREAM
        )
        connect_handler.settimeout(test_params.timeout_sec)
        connect_handler.connect(connect_args[test_params.ip_version])
        connect_handler.send(str(test_packet))

        in_data = connect_handler.recv(INPUT_BUFFER_SIZE)
        if in_data:
            test_params.report_received_packet(sent_time)
    except (socket.timeout, socket.error) as exc:
        if test_params.verbose:
            print ("TCP exception: {}".format(exc))
            # traceback.print_exc()
    finally:
        if connect_handler is not None:
            connect_handler.close()
    return in_data


def udp_sr1(test_params, udp_test, dtls_wrap=False):
    """Sends UDP test message to server using UDP protocol and parses response."""
    response = None
    sent_time = test_params.report_sent_packet()
    if not dtls_wrap:
        if test_params.ip_version == 4:
            udp_test_packet = IP() / UDP() / Raw(udp_test)
            udp_test_packet[IP].src = test_params.src_endpoint.ip_addr
            udp_test_packet[IP].dst = test_params.dst_endpoint.ip_addr
        elif test_params.ip_version == 6:
            udp_test_packet = IPv6() / UDP() / Raw(udp_test)
            udp_test_packet[IPv6].src = test_params.src_endpoint.ipv6_addr
            udp_test_packet[IPv6].dst = test_params.dst_endpoint.ip_addr
        udp_test_packet[UDP].sport = test_params.src_endpoint.port
        udp_test_packet[UDP].dport = test_params.dst_endpoint.port
        del udp_test_packet[UDP].chksum
        # if test_params.verbose:
        #     udp_test_packet.show()
        if test_params.timeout_sec == 0:
            test_params.timeout_sec = 0.0001
        response = sr1(
            udp_test_packet,
            verbose=test_params.verbose,
            timeout=test_params.timeout_sec,
            retry=test_params.nr_retries,
        )
        if response:
            print_verbose(
                test_params, "Received response - size: {}".format(len(response))
            )
            test_params.report_received_packet(sent_time)
    else:
        # do_patch()
        if test_params.ip_version == 4:
            sock = ssl.wrap_socket(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
            sock.connect(
                (test_params.dst_endpoint.ip_addr, test_params.dst_endpoint.port)
            )
            sock.send(udp_test)
            response = IP() / UDP() / Raw(sock.recv())
            if response:
                test_params.report_sent_packet(sent_time)

    #            sock.close()
    return response


def udp_sr1_file(test_params, test_filename):
    """Reads UDP test message from given file, sends this message to server and parses response"""
    with open(test_filename, "r") as file_handle:
        test_data = file_handle.read()
    return udp_sr1(test_params, test_data)


def ssdp_send_query(test_params, query):
    """Sends SSDP query to normal and multicast address."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    if test_params.ip_version == 4:
        sock.sendto(str(query), (SSDP_MULTICAST_IPV4, test_params.dst_endpoint.port))
        sent_time = test_params.report_sent_packet()
        sock.settimeout(test_params.timeout_sec)
        try:
            while True:
                data, addr = sock.recvfrom(INPUT_BUFFER_SIZE)
                print_verbose(
                    test_params,
                    "Received response from {} - content:\n{}\n-----".format(
                        addr, data
                    ),
                )
                if (
                    test_params.dst_endpoint.ip_addr,
                    test_params.dst_endpoint.port,
                ) == addr:
                    print_verbose(
                        test_params, "This is the response that we was waiting for!"
                    )
                    test_params.report_received_packet(sent_time)
                    return data
                else:
                    print_verbose(
                        test_params, "Received response from another host (not target)!"
                    )
        except socket.timeout:
            print_verbose(test_params, "Received no response!")

    elif test_params.ip_version == 6:
        print ("IPv6 is not supported for SSDP")
    return None


def prepare_names(name_filepath):
    """Loads names (URLs or services) from filepath taken from command line
    into sorted list of unique names.

        Args:
            name_filepath (str): Path to file with names.

        Returns:
            list: Sorted list of unique names.
    """

    try:
        with open(name_filepath, "r") as file_handle:
            names_list = {name.strip() for name in file_handle}
    except (IOError, OSError) as file_error:
        exit("Cannot load names: {}".format(file_error))
    test_names = sorted(names_list)
    return test_names


def amplification_factor(input_size, output_size):
    """Calculates network traffic amplification factor for specific node
    Args:
        input_size(int): Size of traffic incoming to examined node.
        output_size(int): Size of traffic outgoing from examined node.

    Returns:
        int: Calculated amplification factor in percent
            (0 means that traffic incoming and outgoing are equal in size,
            100 means that outgoing traffic is two times larger than incoming)
    """
    if input_size != 0:
        return (100 * output_size / input_size) - 100
    return 0
