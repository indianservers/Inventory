import re


GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
HSN_RE = re.compile(r"^[0-9]{4,8}$")
TRN_RE = re.compile(r"^[0-9]{15}$")
GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def is_valid_pan(value):
    return not value or bool(PAN_RE.match(value.strip().upper()))


def is_valid_hsn(value):
    return not value or bool(HSN_RE.match(value.strip()))


def is_valid_trn(value):
    return not value or bool(TRN_RE.match(value.strip()))


def is_valid_gstin(value):
    value = (value or "").strip().upper()
    if not value:
        return True
    if not GSTIN_RE.match(value):
        return False
    return gstin_checksum(value[:-1]) == value[-1]


def gstin_checksum(first_14):
    factor = 2
    total = 0
    mod = len(GST_CHARS)
    for char in reversed(first_14):
        code = GST_CHARS.index(char)
        addend = factor * code
        factor = 1 if factor == 2 else 2
        addend = (addend // mod) + (addend % mod)
        total += addend
    return GST_CHARS[(mod - (total % mod)) % mod]
