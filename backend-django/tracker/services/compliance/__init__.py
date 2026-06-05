"""
Compliance-atlas services (GCLBA PLAN 6-5 Phase 4).

Layers on top of the existing ActionItem / Communication / compliance_timing
surfaces rather than duplicating them:

- cases.py    case creation, status transitions, and the manual activity logger
              (record_case_event) that writes the category_tag the report needs
- report.py   the auto-generated weekly report (group tagged activity by category,
              render Freeman's template to text/HTML, optional PDF)

ComplianceCase.status is a separate lifecycle axis from ActionItem (the actionable
queue); the deadline engine (later slice) maps compliance_timing -> status and does
not touch ActionItem rows.
"""
