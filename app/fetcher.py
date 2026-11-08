"""Read-only HTTPS fetcher with DNS pinning, bounded bodies, and redirect revalidation."""
import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit, urljoin, urlunsplit
from bs4 import BeautifulSoup


class FetchError(ValueError):
    pass


def public_target(url):
    if len(url) > 2000 or any(ord(c) < 33 for c in url):
        raise FetchError('Invalid URL')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise FetchError('Only credential-free public HTTPS URLs on port 443 are allowed')
    host = parsed.hostname.encode('idna').decode('ascii')
    try:
        records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError('Source DNS lookup failed') from exc
    addresses = list(dict.fromkeys(record[4][0] for record in records))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise FetchError('Private, loopback, reserved, or mixed-address destinations are blocked')
    return parsed, host, addresses[0]


def fetch(url, timeout=20, max_bytes=2 * 1024 * 1024):
    for _ in range(4):
        parsed, host, address = public_target(url)
        connection = http.client.HTTPSConnection(host, timeout=timeout, context=ssl.create_default_context())
        raw = socket.create_connection((address, 443), timeout=timeout)
        try:
            connection.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            path = urlunsplit(('', '', parsed.path or '/', parsed.query, ''))
            connection.request('GET', path, headers={'Host': host, 'User-Agent': 'Cognitrail/0.1 (bounded research reader)',
                                                     'Accept': 'text/html,text/plain,application/pdf', 'Accept-Encoding': 'identity'})
            response = connection.getresponse()
            if response.status in (301,302,303,307,308):
                location = response.getheader('Location')
                if not location:
                    raise FetchError('Invalid redirect')
                url = urljoin(url, location)
                continue
            if response.status != 200:
                raise FetchError(f'Source returned HTTP {response.status}')
            if response.getheader('Content-Encoding', 'identity') != 'identity':
                raise FetchError('Compressed source response rejected')
            kind = response.getheader('Content-Type', '').split(';')[0].strip().lower()
            if kind not in ('text/html','text/plain','application/pdf','application/xhtml+xml'):
                raise FetchError('Unsupported source content type')
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise FetchError('Source exceeds download budget')
            return {'url': url, 'body': body, 'content_type': kind}
        except (OSError, ssl.SSLError, http.client.HTTPException) as exc:
            raise FetchError('Source connection failed') from exc
        finally:
            connection.close()
            raw.close()
    raise FetchError('Redirect limit exceeded')


def parse_html(body, url, max_chars):
    soup = BeautifulSoup(body, 'html.parser')
    title = soup.title.get_text(' ', strip=True)[:200] if soup.title else urlsplit(url).hostname
    published = soup.find('meta', attrs={'property': 'article:published_time'})
    date = published.get('content', '')[:40] if published else None
    for element in soup(['script','style','noscript','nav','footer','form','iframe']):
        element.decompose()
    text = (soup.find('main') or soup.find('article') or soup.body or soup).get_text(' ', strip=True)
    if not text or len(text) > max_chars:
        raise FetchError('Source text is empty or exceeds extraction budget')
    return title, text, date
