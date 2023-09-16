import abc
import hashlib
import os
import re
import time
from collections.abc import Callable, MutableMapping
from typing import Required, TypedDict
from urllib.request import parse_http_list

from aiohttp import ClientResponse
from yarl import URL


class Challenge(TypedDict, total=False):
    realm: Required[str]
    nonce: Required[str]
    qop: str
    algorithm: str
    opaque: str


class AuthHandler(abc.ABC):
    @abc.abstractmethod
    def apply_to_headers(
        self, *, method: str, url: URL, headers: MutableMapping[str, str]
    ) -> None:
        ...

    @abc.abstractmethod
    def handle_401(self, resp: ClientResponse) -> bool:
        ...


# based on requests implementation: <https://github.com/psf/requests/blob/881281250f74549f560408e5546d95a8cd73ce28/src/requests/auth.py#L107>
class HttpDigestAuth(AuthHandler):
    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password

        self._challenge: Challenge = Challenge(realm="", nonce="")
        self._last_nonce: str = ""
        self._nonce_count: int = 0

    def build_digest_header(self, method: str, url: URL) -> str | None:
        realm = self._challenge["realm"]
        nonce = self._challenge["nonce"]
        qop = self._challenge.get("qop")
        algorithm = self._challenge.get("algorithm")
        opaque = self._challenge.get("opaque")
        hash_utf8: Callable[[str], str] | None = None

        if algorithm is None:
            _algorithm = "MD5"
        else:
            _algorithm = algorithm.upper()
        # lambdas assume digest modules are imported at the top level
        if _algorithm == "MD5" or _algorithm == "MD5-SESS":

            def md5_utf8(x: str) -> str:
                return hashlib.md5(x.encode("utf-8")).hexdigest()

            hash_utf8 = md5_utf8
        elif _algorithm == "SHA":

            def sha_utf8(x: str) -> str:
                return hashlib.sha1(x.encode("utf-8")).hexdigest()

            hash_utf8 = sha_utf8
        elif _algorithm == "SHA-256":

            def sha256_utf8(x: str) -> str:
                return hashlib.sha256(x.encode("utf-8")).hexdigest()

            hash_utf8 = sha256_utf8
        elif _algorithm == "SHA-512":

            def sha512_utf8(x: str) -> str:
                return hashlib.sha512(x.encode("utf-8")).hexdigest()

            hash_utf8 = sha512_utf8

        if hash_utf8 is None:
            return None

        def kd(s: str, d: str) -> str:
            return hash_utf8(f"{s}:{d}")

        # XXX not implemented yet
        entdig = None

        a1 = f"{self._username}:{realm}:{self._password}"
        a2 = f"{method.upper()}:{url.path_qs}"

        ha1 = hash_utf8(a1)
        ha2 = hash_utf8(a2)

        if nonce == self._last_nonce:
            self._nonce_count += 1
        else:
            self._nonce_count = 1
        ncvalue = f"{self._nonce_count:08x}"
        s = str(self._nonce_count).encode("utf-8")
        s += nonce.encode("utf-8")
        s += time.ctime().encode("utf-8")
        s += os.urandom(8)

        cnonce = hashlib.sha1(s).hexdigest()[:16]
        if _algorithm == "MD5-SESS":
            ha1 = hash_utf8(f"{ha1}:{nonce}:{cnonce}")

        if not qop:
            respdig = kd(ha1, f"{nonce}:{ha2}")
        elif qop == "auth" or "auth" in qop.split(","):
            noncebit = f"{nonce}:{ncvalue}:{cnonce}:auth:{ha2}"
            respdig = kd(ha1, noncebit)
        else:
            # XXX handle auth-int.
            return None

        self._last_nonce = nonce

        base = (
            f'username="{self._username}", realm="{realm}", nonce="{nonce}", '
            f'uri="{url.path_qs}", response="{respdig}"'
        )
        if opaque:
            base += f', opaque="{opaque}"'
        if algorithm:
            base += f', algorithm="{algorithm}"'
        if entdig:
            base += f', digest="{entdig}"'
        if qop:
            base += f', qop="auth", nc={ncvalue}, cnonce="{cnonce}"'
        return f"Digest {base}"

    def apply_to_headers(
        self, *, method: str, url: URL, headers: MutableMapping[str, str]
    ) -> None:
        if value := self.build_digest_header(method, url):
            headers["Authorization"] = value

    def handle_401(self, resp: ClientResponse) -> bool:
        s_auth = resp.headers.get("www-authenticate", "")
        if "digest" not in s_auth.lower():
            return False
        pat = re.compile(r"digest ", flags=re.IGNORECASE)
        raw_challenge = parse_dict_header(pat.sub("", s_auth, count=1))
        self._challenge = Challenge(
            **{key: value for key, value in raw_challenge.items() if value is not None}
        )
        return True


# From mitsuhiko/werkzeug (used with permission).
def parse_dict_header(value: str) -> dict[str, str | None]:
    """Parse lists of key, value pairs as described by RFC 2068 Section 2 and
    convert them into a python dict:

    >>> d = parse_dict_header('foo="is a fish", bar="as well"')
    >>> type(d) is dict
    True
    >>> sorted(d.items())
    [('bar', 'as well'), ('foo', 'is a fish')]

    If there is no value for a key it will be `None`:

    >>> parse_dict_header('key_without_value')
    {'key_without_value': None}

    To create a header from the :class:`dict` again, use the
    :func:`dump_header` function.

    :param value: a string with a dict header.
    :return: :class:`dict`
    :rtype: dict
    """
    result: dict[str, str | None] = {}
    for item in parse_http_list(value):
        if "=" not in item:
            result[item] = None
            continue
        name, value = item.split("=", 1)
        if value[:1] == value[-1:] == '"':
            value = unquote_header_value(value[1:-1])
        result[name] = value
    return result


# From mitsuhiko/werkzeug (used with permission).
def unquote_header_value(value: str, is_filename: bool = False) -> str:
    """Unquotes a header value.  (Reversal of :func:`quote_header_value`).
    This does not use the real unquoting but what browsers are actually
    using for quoting.

    :param value: the header value to unquote.
    :rtype: str
    """
    if value and value[0] == value[-1] == '"':
        # this is not the real unquoting, but fixing this so that the
        # RFC is met will result in bugs with internet explorer and
        # probably some other browsers as well.  IE for example is
        # uploading files with "C:\foo\bar.txt" as filename
        value = value[1:-1]

        # if this is a filename and the starting characters look like
        # a UNC path, then just return the value without quotes.  Using the
        # replace sequence below on a UNC path has the effect of turning
        # the leading double slash into a single slash and then
        # _fix_ie_filename() doesn't work correctly.  See #458.
        if not is_filename or value[:2] != "\\\\":
            return value.replace("\\\\", "\\").replace('\\"', '"')
    return value
