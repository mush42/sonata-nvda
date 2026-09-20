# coding: utf-8
"""
Tests for helpers.py — port utilities with no NVDA dependency.
"""

import socket
import pytest

from sonata_neural_voices.helpers import is_free_port, find_free_port


class TestIsFreePport:

    def test_returns_true_for_free_port(self):
        port = find_free_port()
        assert is_free_port(port)

    def test_returns_false_for_bound_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("localhost", 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            bound_port = s.getsockname()[1]
            assert not is_free_port(bound_port)


class TestFindFreePort:

    def test_returns_integer(self):
        port = find_free_port()
        assert isinstance(port, int)

    def test_port_in_valid_range(self):
        port = find_free_port()
        assert 1024 <= port <= 65535

    def test_port_is_actually_free(self):
        port = find_free_port()
        assert is_free_port(port)

    def test_successive_calls_return_valid_ports(self):
        for _ in range(5):
            p = find_free_port()
            assert 1024 <= p <= 65535
