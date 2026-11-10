import socket
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from amigo.policy import Denied
from amigo.web_policy import parse_url,resolve_public,public_ip,browsing_url
from amigo.web_proxy import PublicProxy

class WebPolicyTests(unittest.TestCase):
    def test_local_and_non_web_addresses_rejected(self):
        for url in ['file:///etc/passwd','http://127.0.0.1','http://localhost','https://localhost.localdomain','http://[::1]',
                    'http://169.254.169.254','http://192.168.1.1','http://10.0.0.1','http://[::ffff:127.0.0.1]',
                    'http://[fe80::1%25eth0]','http://example.com:22','http://user:password@example.com','http://example.com\r\nHost:evil',
                    'http://router.local','ftp://example.com/file','http://[64:ff9b::7f00:1]','http://[2002:7f00:1::]']:
            with self.subTest(url=url):
                with self.assertRaises(Denied):parse_url(url)
    def test_mixed_dns_and_rebinding_addresses_rejected(self):
        records=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443)),(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',443))]
        with patch('socket.getaddrinfo',return_value=records):
            with self.assertRaises(Denied):resolve_public('example.com',443)
    def test_globally_numbered_host_address_is_not_public_destination(self):
        records=[(socket.AF_INET6,socket.SOCK_STREAM,6,'',('2606:4700:4700::1111',443,0,0))]
        with patch('socket.getaddrinfo',return_value=records),patch('amigo.web_policy.local_addresses',return_value={'2606:4700:4700::1111'}):
            with self.assertRaises(Denied):resolve_public('example.com',443)
    def test_numeric_addresses_are_pinned(self):
        records=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',443))]
        with patch('socket.getaddrinfo',return_value=records):self.assertEqual(resolve_public('example.com',443),records)
    def test_browser_scope(self):
        self.assertEqual(browsing_url('https://example.com/docs'), 'https://example.com/docs')
        for path in ('login','account','checkout','oauth','delete','%61ccount','%2561ccount','login;ignored','x%2faccount'):
            with self.assertRaises(Denied):browsing_url('https://example.com/'+path)
    def test_real_proxy_refuses_local_connect_and_post(self):
        with tempfile.TemporaryDirectory() as directory:
            proxy=PublicProxy(Path(directory)/'proxy.sock').start()
            try:
                for request in (b'CONNECT 127.0.0.1:443 HTTP/1.1\r\n\r\n',b'GET http://192.168.1.1/ HTTP/1.1\r\n\r\n',b'POST http://example.com/ HTTP/1.1\r\n\r\n'):
                    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as connection:
                        connection.connect(str(proxy.path));connection.sendall(request);reply=connection.recv(4096)
                        self.assertTrue(reply.startswith(b'HTTP/1.1 403'),reply)
                self.assertEqual(proxy.path.stat().st_mode&0o777,0o600)
            finally:proxy.close()

if __name__=='__main__':unittest.main()
