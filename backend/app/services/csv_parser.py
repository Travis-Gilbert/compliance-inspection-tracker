import csv
import io
import re
import uuid
from typing import Optional
from app.models.property import PropertyCreate
from app.utils.address import normalize_address


# Column name patterns for auto-detection
# Patterns are checked with exact match first, then substring match,
# to avoid false positives (e.g., "name" matching "filename").
COLUMN_PATTERNS = {
    "address": {
        "exact": ["address", "street_address", "property_address", "prop_addr", "street_addr"],
        "contains": ["address", "street"],
    },
    "parcel_id": {
        "exact": ["parcel_id", "parcelid", "parcel_number", "parcel_no", "pin", "apn", "folio", "tax_id"],
        "contains": ["parcel"],
    },
    "city_state_zip": {
        "exact": ["city_state_zip", "citystatezip", "city_state", "city_zip", "city"],
        "contains": ["city_state_zip", "city_state", "city_zip"],
    },
    "buyer_name": {
        "exact": ["buyer_name", "buyer", "purchaser", "owner_name", "full_name"],
        "contains": ["buyer", "purchaser"],
    },
    "program": {
        "exact": ["program", "program_type", "sale_type", "category"],
        "contains": ["program"],
    },
    "closing_date": {
        "exact": ["closing_date", "close_date", "sale_date", "date_sold", "closed", "closing"],
        "contains": ["closing", "close_date", "sale_date"],
    },
    "commitment": {
        "exact": ["commitment", "investment", "committed", "rehab_cost", "committed_investment"],
        "contains": ["commitment", "invest", "rehab_cost"],
    },
    "email": {
        "exact": ["email", "email_address", "e-mail", "e_mail"],
        "contains": ["email", "e-mail"],
    },
    "organization": {
        "exact": ["organization", "org", "company", "entity", "org_name"],
        "contains": ["organization", "company"],
    },
    "purchase_type": {
        "exact": ["purchase_type", "purchaser_type", "buyer_type", "type"],
        "contains": ["purchase_type", "buyer_type", "purchaser_type"],
    },
    "compliance_1st_attempt": {
        "exact": [
            "compliance_1st_attempt", "first_attempt", "1st_attempt",
            "compliance_first_attempt", "compliance_attempt_1",
        ],
        "contains": ["1st_attempt", "first_attempt", "compliance_1", "attempt_1"],
    },
    "compliance_2nd_attempt": {
        "exact": [
            "compliance_2nd_attempt", "second_attempt", "2nd_attempt",
            "compliance_second_attempt", "compliance_attempt_2",
        ],
        "contains": ["2nd_attempt", "second_attempt", "compliance_2", "attempt_2"],
    },
    "streetview_historical_path": {
        "exact": ["streetview_historical_path", "historical_streetview_path"],
        "contains": ["streetview_historical_path", "historical_streetview_path"],
    },
    "streetview_historical_date": {
        "exact": ["streetview_historical_date", "historical_streetview_date"],
        "contains": ["streetview_historical_date", "historical_streetview_date"],
    },
}

PARCEL_PATTERN = re.compile(r"\d{2}-\d{2}-\d{3}-\d{3}")


def detect_delimiter(sample: str) -> str:
    """Detect whether the file uses commas, tabs, or pipes."""
    lines = sample.split("\n")[:5]
    text = "\n".join(lines)

    counts = {
        ",": text.count(","),
        "\t": text.count("\t"),
        "|": text.count("|"),
    }
    return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def detect_columns(headers: list[str]) -> dict[str, Optional[int]]:
    """
    Match header names to our expected fields.
    Returns a mapping of field_name -> column_index.

    Uses two-pass matching: exact match first, then substring fallback.
    This prevents false positives like "name" matching a generic column.
    """
    mapping = {}
    headers_lower = [h.strip().lower().replace(" ", "_").replace("-", "_") for h in headers]
    used_indices = set()

    # Pass 1: Exact matches
    for field, patterns in COLUMN_PATTERNS.items():
        for i, header in enumerate(headers_lower):
            if i in used_indices:
                continue
            if header in patterns["exact"]:
                mapping[field] = i
                used_indices.add(i)
                break

    # Pass 2: Substring matches for fields not yet mapped
    for field, patterns in COLUMN_PATTERNS.items():
        if field in mapping:
            continue
        for i, header in enumerate(headers_lower):
            if i in used_indices:
                continue
            if any(p in header for p in patterns["contains"]):
                mapping[field] = i
                used_indices.add(i)
                break

    return mapping


def has_header_row(first_line: str, delimiter: str) -> bool:
    """Guess whether the first row is a header based on content."""
    cols = first_line.split(delimiter)
    first_lower = " ".join(c.strip().lower() for c in cols)
    header_indicators = ["address", "parcel", "buyer", "program", "date", "owner", "property"]
    return any(h in first_lower for h in header_indicators)


def strip_bom(text: str) -> str:
    """Remove UTF-8 BOM if present."""
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def combine_address(address: str, city_state_zip: str = "") -> str:
    """Combine split address fields from FileMaker-style exports."""
    street = normalize_address(address)
    locality = normalize_address(city_state_zip)

    if not locality:
        return street
    if locality.lower() in street.lower():
        return street
    return normalize_address(f"{street}, {locality}")


def parse_csv_text(text: str, filename: str = "") -> tuple[list[PropertyCreate], list[str], str]:
    """
    Parse CSV/TSV text into PropertyCreate objects.

    Returns:
        (properties, errors, batch_id)
    """
    text = strip_bom(text)

    if not text.strip():
        return [], ["Empty input"], ""

    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # FileMaker uses \x0b (vertical tab) as a line separator within fields.
    # Replace with comma+space so multi-line addresses become "307 Mason St, Flint MI"
    text = text.replace("\x0b", ", ")

    batch_id = str(uuid.uuid4())[:8]
    delimiter = detect_delimiter(text)
    lines = text.strip().split("\n")

    # Detect header
    has_header = has_header_row(lines[0], delimiter)

    if has_header:
        reader = csv.reader(io.StringIO(text.strip()), delimiter=delimiter)
        headers = next(reader)
        column_map = detect_columns(headers)
        data_lines = list(reader)
    else:
        # No header: try positional mapping
        # Assume: address is first column
        column_map = {"address": 0}
        reader = csv.reader(io.StringIO(text.strip()), delimiter=delimiter)
        data_lines = list(reader)

        # Try to detect parcel IDs by scanning first data row
        if data_lines and len(data_lines[0]) > 1:
            for i, col in enumerate(data_lines[0]):
                if PARCEL_PATTERN.match(col.strip()):
                    column_map["parcel_id"] = i
                    break

    if "address" not in column_map:
        return [], ["Could not detect an address column. Ensure your CSV has an 'address' header or addresses in the first column."], ""

    properties = []
    errors = []

    for row_num, row in enumerate(data_lines, start=2 if has_header else 1):
        if not row or all(c.strip() == "" for c in row):
            continue

        try:
            def get_col(field: str) -> str:
                idx = column_map.get(field)
                if idx is not None and idx < len(row):
                    val = row[idx].strip().strip('"').strip("'")
                    return val
                return ""

            address = combine_address(
                get_col("address"),
                get_col("city_state_zip"),
            )
            if not address:
                errors.append(f"Row {row_num}: no address found, skipping")
                continue

            prop = PropertyCreate(
                address=address,
                parcel_id=get_col("parcel_id"),
                buyer_name=get_col("buyer_name"),
                program=get_col("program"),
                closing_date=get_col("closing_date"),
                commitment=get_col("commitment"),
                email=get_col("email"),
                organization=get_col("organization"),
                purchase_type=get_col("purchase_type"),
                compliance_1st_attempt=get_col("compliance_1st_attempt"),
                compliance_2nd_attempt=get_col("compliance_2nd_attempt"),
                streetview_historical_path=get_col("streetview_historical_path"),
                streetview_historical_date=get_col("streetview_historical_date"),
            )
            properties.append(prop)

        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    return properties, errors, batch_id
