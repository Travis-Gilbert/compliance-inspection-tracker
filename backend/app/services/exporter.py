import csv
import io
from datetime import datetime
from typing import Optional

FINDING_LABELS = {
    "visibly_renovated": "Visibly Renovated",
    "occupied_maintained": "Occupied & Maintained",
    "partial_progress": "Partial Progress",
    "appears_vacant": "Appears Vacant",
    "structure_gone": "Structure Gone / Demolished",
    "inconclusive": "Inconclusive / Needs Inspection",
}

DETECTION_LABELS = {
    "likely_occupied": "Likely Occupied",
    "likely_vacant": "Likely Vacant",
    "likely_demolished": "Likely Demolished",
    "no_streetview": "No Street View Available",
    "unprocessed": "Not Yet Processed",
}


def export_properties_csv(properties: list[dict], include_detection: bool = True) -> str:
    """
    Export properties to CSV format suitable for FileMaker import.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    headers = [
        "Address",
        "Parcel ID",
        "Buyer Name",
        "Program",
        "Closing Date",
        "Commitment",
        "Finding",
        "Notes",
        "Reviewed Date",
    ]
    if include_detection:
        headers.extend([
            "Detection Label",
            "Detection Score",
            "Street View Available",
            "Street View Date",
        ])

    writer.writerow(headers)

    for prop in properties:
        row = [
            prop.get("address", ""),
            prop.get("parcel_id", ""),
            prop.get("buyer_name", ""),
            prop.get("program", ""),
            prop.get("closing_date", ""),
            prop.get("commitment", ""),
            FINDING_LABELS.get(prop.get("finding", ""), ""),
            prop.get("notes", "").replace("\n", " "),
            prop.get("reviewed_at", ""),
        ]
        if include_detection:
            row.extend([
                DETECTION_LABELS.get(prop.get("detection_label", ""), ""),
                prop.get("detection_score", ""),
                "Yes" if prop.get("streetview_available") else "No",
                prop.get("streetview_date", ""),
            ])

        writer.writerow(row)

    return output.getvalue()


def export_inspection_list_csv(properties: list[dict]) -> str:
    """
    Export only properties flagged for physical inspection.
    Formatted for field use: address, last known info, what to look for.
    """
    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Address",
        "Parcel ID",
        "Buyer Name",
        "Program",
        "Detection Notes",
        "Staff Notes",
        "Inspection Result",
        "Inspection Date",
    ])

    for prop in properties:
        finding = prop.get("finding", "")
        detection = prop.get("detection_label", "")
        if finding == "inconclusive" or detection in ("likely_vacant", "likely_demolished"):
            writer.writerow([
                prop.get("address", ""),
                prop.get("parcel_id", ""),
                prop.get("buyer_name", ""),
                prop.get("program", ""),
                DETECTION_LABELS.get(detection, ""),
                prop.get("notes", "").replace("\n", " "),
                "",  # To be filled in the field
                "",  # To be filled in the field
            ])

    return output.getvalue()


def generate_summary_report(stats: dict) -> str:
    """
    Generate a text summary report for leadership.
    """
    now = datetime.now().strftime("%B %d, %Y")
    total = stats.get("total", 0)
    reviewed = stats.get("reviewed", 0)
    resolved = stats.get("resolved", 0)
    needs_inspection = stats.get("needs_inspection", 0)
    unreviewed = stats.get("unreviewed", 0)

    lines = [
        f"GCLBA Compliance Inspection Tracker",
        f"Summary Report: {now}",
        f"",
        f"Total properties in tracker: {total}",
        f"Reviewed via desk research: {reviewed}",
        f"  Resolved without site visit: {resolved}",
        f"  Flagged for physical inspection: {needs_inspection}",
        f"Remaining to review: {unreviewed}",
        f"",
    ]

    if total > 0:
        lines.append(f"Progress: {round(reviewed/total*100)}% of properties reviewed")
        if resolved > 0:
            lines.append(f"Desk resolution rate: {round(resolved/max(reviewed,1)*100)}% of reviewed properties resolved without visit")

    by_finding = stats.get("by_finding", {})
    if by_finding:
        lines.extend(["", "Findings breakdown:"])
        for finding, count in sorted(by_finding.items(), key=lambda x: -x[1]):
            label = FINDING_LABELS.get(finding, finding)
            lines.append(f"  {label}: {count}")

    by_program = stats.get("by_program", {})
    if by_program:
        lines.extend(["", "By program:"])
        for program, count in sorted(by_program.items(), key=lambda x: -x[1]):
            lines.append(f"  {program or 'Unknown'}: {count}")

    return "\n".join(lines)
