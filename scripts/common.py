"""
common.py - Shared configuration and helpers for the FoodBridge data pipeline.

Contains:
  * global configuration (random seed, data snapshot time, paths)
  * text normalisation helpers for names, addresses, ZIP codes, phones
  * a small entity-resolution (ER) routine (blocking + similarity + union-find)
    used both for the real Philadelphia food-site data and for the
    synthetic donor/recipient registry.
"""

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
SEED = 20261019                                   # same seed as the proposal
AS_OF = pd.Timestamp("2026-11-10 12:00:00")       # "now" of the data snapshot
START = pd.Timestamp("2025-01-01 00:00:00")       # first day of simulated activity
CITY = "Philadelphia"

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
SYN_RAW_DIR = RAW_DIR / "synthetic"
INTERIM_DIR = ROOT / "data" / "interim"
FINAL_DIR = ROOT / "data" / "processed"
REPORT_DIR = ROOT / "reports"
for d in (SYN_RAW_DIR, INTERIM_DIR, FINAL_DIR, REPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

PHILLY_RAW = RAW_DIR / "philly_free_food_sites_raw_2026-11-10.csv"

# Residential / general Philadelphia ZIP codes (19109 & 19112 are excluded:
# single-building / Navy Yard ZIPs).
PHILLY_ZIPS = [
    "19102", "19103", "19104", "19106", "19107", "19111", "19114", "19115",
    "19116", "19118", "19119", "19120", "19121", "19122", "19123", "19124",
    "19125", "19126", "19127", "19128", "19129", "19130", "19131", "19132",
    "19133", "19134", "19135", "19136", "19137", "19138", "19139", "19140",
    "19141", "19142", "19143", "19144", "19145", "19146", "19147", "19148",
    "19149", "19150", "19151", "19152", "19153", "19154",
]

# --------------------------------------------------------------------------
# Normalisation helpers
# --------------------------------------------------------------------------
_ADDR_TOKENS = {
    "street": "st", "str": "st", "avenue": "ave", "av": "ave",
    "boulevard": "blvd", "parkway": "pkwy", "pky": "pkwy", "road": "rd",
    "drive": "dr", "lane": "ln", "place": "pl", "terrace": "ter",
    "court": "ct", "square": "sq", "highway": "hwy",
    "north": "n", "south": "s", "east": "e", "west": "w", "so": "s", "no": "n",
}
# trailing unit / floor / door designators that do not identify a different site
_UNIT_RE = re.compile(
    r"\b(suite|ste|unit|apt|floor|fl|room|rm|door( number)?|bldg|building)\b.*$"
    r"|#\s*\w+|\b\d+(st|nd|rd|th) floor\b.*$"
)
_NAME_DROP = {"inc", "incorporated", "llc", "corp", "corporation", "co", "ltd",
              "the", "of", "at", "and", "for", "a"}
_NAME_TOKENS = {"saint": "st", "&": "and", "ctr": "center", "centre": "center"}


def ascii_fold(s: str) -> str:
    """Convert curly quotes / accents to plain ASCII."""
    s = s.replace("’", "'").replace("‘", "'")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def clean_text(s) -> str | None:
    """Trim whitespace (incl. embedded newlines); return None for blanks."""
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s or None


def norm_address(addr) -> str:
    """Canonical key for an address: lower case, no punctuation, standard
    abbreviations, unit/floor designators removed."""
    if not addr:
        return ""
    s = ascii_fold(str(addr)).lower()
    s = _UNIT_RE.sub("", s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [_ADDR_TOKENS.get(t, t) for t in s.split()]
    return " ".join(toks)


def norm_name_tokens(name) -> list[str]:
    if not name:
        return []
    s = ascii_fold(str(name)).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    toks = [_NAME_TOKENS.get(t, t) for t in s.split()]
    return [t for t in toks if t not in _NAME_DROP]


def norm_name(name) -> str:
    return " ".join(norm_name_tokens(name))


def name_similarity(a: str, b: str) -> float:
    """Max of (a) character-level SequenceMatcher ratio and (b) token
    containment of the shorter name inside the longer one."""
    ta, tb = norm_name_tokens(a), norm_name_tokens(b)
    if not ta or not tb:
        return 0.0
    seq = SequenceMatcher(None, " ".join(ta), " ".join(tb)).ratio()
    sa, sb = set(ta), set(tb)
    small, big = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    contain = len(small & big) / len(small)
    return max(seq, contain)


def norm_zip(z) -> str | None:
    """'19103-2201' / ' 19103' / '19103.0' -> '19103'; invalid -> None."""
    if z is None or (isinstance(z, float) and pd.isna(z)):
        return None
    m = re.search(r"\b(19\d{3})", str(z))
    return m.group(1) if m else None


_PHONE_RE = re.compile(
    r"\(?(\d{3})\)?[\s.\-]*(\d{3})[\s.\-]*(\d{4})(?:\s*,?\s*(?:ext\.?|x)\s*(\d+))?",
    re.I)
_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")


def parse_contact(raw) -> tuple[str | None, str | None]:
    """Split a free-text contact field into (phone, email)."""
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None, None
    s = str(raw)
    phone = email = None
    m = _PHONE_RE.search(s)
    if m:
        phone = f"({m.group(1)}) {m.group(2)}-{m.group(3)}"
        if m.group(4):
            phone += f" ext. {m.group(4)}"
    e = _EMAIL_RE.search(s)
    if e:
        email = e.group(0).lower()
    return phone, email


def contact_string(phone, email, limit=100) -> str | None:
    parts = [p for p in (phone, email) if p]
    return "; ".join(parts)[:limit] if parts else None


def norm_status(s) -> str | None:
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return None
    s = str(s).strip().lower()
    if s in {"active", "open", "a", "y", "yes"}:
        return "active"
    if s in {"inactive", "closed", "permanently closed", "n", "no"}:
        return "inactive"
    return None


# --------------------------------------------------------------------------
# Entity resolution
# --------------------------------------------------------------------------
class UnionFind:
    def __init__(self, items):
        self.p = {i: i for i in items}

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def resolve_entities(df: pd.DataFrame, id_col: str, name_col: str,
                     addr_col: str, threshold: float = 0.6) -> pd.Series:
    """Cluster records that refer to the same real-world organisation.

    Blocking key  : normalised address (records at different addresses are
                    treated as different sites, e.g. Bethesda Project runs
                    four separate locations).
    Match rule    : inside a block, two records match when
                    name_similarity >= threshold.
    Transitivity  : union-find, so A~B and B~C put A, B, C in one cluster.

    Returns a Series mapping each record id -> cluster id (smallest member id).
    """
    uf = UnionFind(df[id_col].tolist())
    blocks = df.assign(_k=df[addr_col].map(norm_address)).groupby("_k")
    for key, g in blocks:
        if not key or len(g) < 2:
            continue
        rows = g[[id_col, name_col]].values.tolist()
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                if name_similarity(rows[i][1], rows[j][1]) >= threshold:
                    uf.union(rows[i][0], rows[j][0])
    return df[id_col].map(uf.find)
