"""
Address normalization and geocoding helpers.

Copied verbatim from backend/app/utils/address.py. Pure string processing,
no framework dependencies.
"""
import re
from typing import Optional

# Common Flint/Genesee County suffixes and abbreviations
STREET_ABBREVIATIONS = {
    "st": "St", "street": "St",
    "ave": "Ave", "avenue": "Ave",
    "blvd": "Blvd", "boulevard": "Blvd",
    "dr": "Dr", "drive": "Dr",
    "rd": "Rd", "road": "Rd",
    "ct": "Ct", "court": "Ct",
    "ln": "Ln", "lane": "Ln",
    "pl": "Pl", "place": "Pl",
    "cir": "Cir", "circle": "Cir",
    "pkwy": "Pkwy", "parkway": "Pkwy",
    "ter": "Ter", "terrace": "Ter",
    "way": "Way",
}


def normalize_address(address: str) -> str:
    """
    Normalize an address string for consistent matching.
    Handles common variations in Flint/Genesee County addresses.
    """
    if not address:
        return ""

    addr = address.strip()
    # FileMaker uses \x0b (vertical tab) as line separator within fields
    addr = addr.replace("\x0b", ", ")
    # Remove extra whitespace
    addr = re.sub(r"\s+", " ", addr)
    # Standardize directional prefixes
    addr = re.sub(r"\b(N|n)\.?\s", "N ", addr)
    addr = re.sub(r"\b(S|s)\.?\s", "S ", addr)
    addr = re.sub(r"\b(E|e)\.?\s", "E ", addr)
    addr = re.sub(r"\b(W|w)\.?\s", "W ", addr)
    # Standardize common street suffixes
    for raw_value, standard_value in STREET_ABBREVIATIONS.items():
        addr = re.sub(rf"\b{re.escape(raw_value)}\b", standard_value, addr, flags=re.IGNORECASE)

    return addr


def build_address_key(address: str) -> str:
    """
    Build a normalized lookup key for matching repeated imports.
    """
    normalized = normalize_address(address).lower()
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def build_full_address(address: str, city: str = "Flint", state: str = "MI") -> str:
    """
    Append city/state if not already present.
    Most GCLBA properties are in Flint, but some are elsewhere in Genesee County.
    """
    addr_lower = address.lower()
    if "flint" in addr_lower or "mi" in addr_lower or "michigan" in addr_lower:
        return normalize_address(address)

    # Check for other Genesee County cities
    gc_cities = ["burton", "davison", "fenton", "flushing", "grand blanc",
                 "mt. morris", "mount morris", "swartz creek", "clio", "linden"]
    for c in gc_cities:
        if c in addr_lower:
            return normalize_address(address)

    return normalize_address(f"{address}, {city}, {state}")


def extract_parcel_id(text: str) -> Optional[str]:
    """Extract a Genesee County parcel ID pattern from text."""
    match = re.search(r"\d{2}-\d{2}-\d{3}-\d{3}", text)
    return match.group(0) if match else None
