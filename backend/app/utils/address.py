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
    # Remove extra whitespace
    addr = re.sub(r"\s+", " ", addr)
    # Standardize directional prefixes
    addr = re.sub(r"\b(N|n)\.?\s", "N ", addr)
    addr = re.sub(r"\b(S|s)\.?\s", "S ", addr)
    addr = re.sub(r"\b(E|e)\.?\s", "E ", addr)
    addr = re.sub(r"\b(W|w)\.?\s", "W ", addr)

    return addr


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
