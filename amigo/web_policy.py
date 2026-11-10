"""Public-web address validation shared by the proxy and browser capability broker."""
import ipaddress
import socket
from urllib.parse import urlsplit,unquote
from .policy import Denied

LOCAL_SUFFIXES=('.localhost','.localdomain','.local','.internal','.lan','.home','.onion')

def public_ip(value):
    try:
        address=ipaddress.ip_address(value.split('%',1)[0])
        if getattr(address,'ipv4_mapped',None):address=address.ipv4_mapped
        return address.is_global and not address.is_multicast and not address.is_unspecified
    except ValueError:return False

def parse_url(value):
    if not isinstance(value,str) or len(value)>8192 or any(ord(c)<33 or ord(c)==127 for c in value) or '\\' in value:
        raise Denied('Invalid web URL')
    try:
        parsed=urlsplit(value)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username is not None or parsed.password is not None:
            raise Denied('Only public HTTP(S) URLs without credentials are permitted')
        host=parsed.hostname.rstrip('.').lower()
        port=parsed.port or (443 if parsed.scheme=='https' else 80)
        if port not in (80,443):raise Denied('Only web ports 80 and 443 are permitted')
        if host=='localhost' or host.endswith(LOCAL_SUFFIXES) or '%' in host:raise Denied('Local destinations are blocked')
        try:address=ipaddress.ip_address(host)
        except ValueError:
            host=host.encode('idna').decode('ascii')
            if '.' not in host or any(not label or len(label)>63 for label in host.split('.')):raise Denied('Invalid public hostname')
        else:
            if not public_ip(str(address)):raise Denied('Private, loopback and reserved destinations are blocked')
        return parsed,host,port
    except (ValueError,UnicodeError) as error:raise Denied('Invalid or disallowed web URL') from error

def resolve_public(host,port):
    """Validate every returned address; callers connect to these numeric addresses only."""
    records=socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    if not records or any(not public_ip(record[4][0]) for record in records):
        raise Denied('DNS returned a private or reserved destination')
    unique=[]
    for record in records:
        if record not in unique:unique.append(record)
    return unique

def browsing_url(value):
    parsed,host,port=parse_url(value)
    # This initial browser does not operate accounts, checkout or administrative forms.
    decoded=parsed.path
    for _ in range(4):
        expanded=unquote(decoded)
        if expanded==decoded:break
        decoded=expanded
    if '%' in decoded or '\\' in decoded:raise Denied('Ambiguous encoded URL path')
    segments={part.lower().split(';',1)[0] for part in decoded.split('/')}
    if segments & {'login','signin','sign-in','signup','sign-up','logout','checkout','cart','purchase','oauth','admin','delete','account'}:
        raise Denied('Accounts, purchases and publishing are outside this browser version')
    return value
