import unicodedata

KEYWORDS = [
    "tecnologia da informacao",
    "telefonia ip",
    "pabx",
    "sip trunk",
    "stfc",
    "firewall",
    "next generation firewall",
    "ngfw",
    "firewall de proxima geracao",
]


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def matches_scope(objeto: str) -> bool:
    if not objeto:
        return False
    haystack = _strip_accents(objeto).lower()
    return any(keyword in haystack for keyword in KEYWORDS)
