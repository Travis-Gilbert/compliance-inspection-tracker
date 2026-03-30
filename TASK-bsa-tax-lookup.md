# Task: BSA Delinquent Tax Lookup (Public Endpoint, No Auth)

## Context

The Genesee County BSA Online delinquent tax search is publicly accessible at:
`https://bsaonline.com/OnlinePayment/OnlinePaymentSearch?PaymentApplicationType=5&uid=304`

No login required. Searches by parcel number, address, or owner name.

If a parcel appears in the delinquent tax database, the property has unpaid taxes.
If it does not appear, taxes are current (at the county level). This gives us a
binary signal that answers Christina's core question: "Are they paying their taxes?"

## Strategy

Build a Django management command that queries this public endpoint for each
property in the compliance tracker, extracts delinquent tax status and amounts,
and updates the Property model.

## Technical Approach

BSA Online is an ASP.NET MVC application. The search page loads via JavaScript
and makes AJAX calls to fetch results. The implementation needs to:

1. Inspect the network requests the search page makes (use browser dev tools
   or Firecrawl to identify the actual API endpoint the JavaScript calls)
2. Replicate those requests with httpx
3. Parse the response (likely HTML fragments or JSON)

### Known BSA URL Patterns (from other municipalities)

Search results for tax/delinquent records follow patterns like:
```
/Tax_OnlinePayment/OnlinePaymentDetails?
  SearchCategory=Parcel%20Number
  &SearchText={parcel_id}
  &SearchFocus=All%20Records
  &uid=304
  &PaymentApplicationType=5
```

The `uid=304` is Genesee County's identifier in the BSA system.
`PaymentApplicationType=5` is delinquent tax (vs. 4 for current tax).

### Parcel ID Format

Genesee County parcel IDs in our system: `XX-XX-XXX-XXX` (e.g., `41-06-538-004`)
BSA may expect: `XXXXXXXXXX` (no dashes, 10 digits)

The management command should strip dashes before querying.

## Management Command

```python
# backend-django/tracker/management/commands/import_tax_data.py

from django.core.management.base import BaseCommand
import httpx
import time

class Command(BaseCommand):
    help = "Check delinquent tax status for all properties via public BSA Online"

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Limit number of properties to check (0 = all)"
        )
        parser.add_argument(
            "--delay", type=float, default=2.0,
            help="Seconds between requests (be polite)"
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print results without updating the database"
        )

    def handle(self, *args, **options):
        from tracker.models import Property

        properties = Property.objects.exclude(parcel_id="")
        if options["limit"]:
            properties = properties[:options["limit"]]

        total = properties.count()
        delinquent_count = 0
        current_count = 0
        error_count = 0

        self.stdout.write(f"Checking {total} properties against BSA delinquent tax database...")

        for i, prop in enumerate(properties.iterator(), 1):
            parcel_clean = prop.parcel_id.replace("-", "")

            try:
                is_delinquent, amount_owed = self.check_bsa(parcel_clean, options["delay"])

                if is_delinquent:
                    delinquent_count += 1
                    if not options["dry_run"]:
                        Property.objects.filter(pk=prop.pk).update(
                            tax_status="delinquent",
                            tax_amount_owed=amount_owed,
                        )
                    self.stdout.write(
                        self.style.WARNING(f"  [{i}/{total}] {prop.address}: DELINQUENT (${amount_owed})")
                    )
                else:
                    current_count += 1
                    if not options["dry_run"]:
                        Property.objects.filter(pk=prop.pk).update(
                            tax_status="current",
                            tax_amount_owed=None,
                        )
                    self.stdout.write(f"  [{i}/{total}] {prop.address}: current")

            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f"  [{i}/{total}] {prop.address}: ERROR ({e})")
                )

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. {current_count} current, {delinquent_count} delinquent, {error_count} errors."
        ))

    def check_bsa(self, parcel_number: str, delay: float) -> tuple[bool, float | None]:
        """
        Query the public BSA Online delinquent tax search for Genesee County.

        Returns (is_delinquent, amount_owed).
        If the parcel appears in results, it is delinquent.
        If no results, it is current.

        IMPLEMENTATION NOTE FOR CLAUDE CODE:
        The exact AJAX endpoint needs to be discovered by inspecting the
        network requests that the BSA search page makes. Steps:

        1. Open the BSA search page in a browser with dev tools
        2. Search for a known parcel number
        3. Observe the XHR/fetch request in the Network tab
        4. Replicate that request with httpx

        The request will likely be a POST to a URL like:
        /OnlinePayment/OnlinePaymentSearchResults
        or
        /SearchService/Search

        with form data including:
        - SearchText: parcel_number
        - SearchCategory: "Parcel Number"
        - PaymentApplicationType: 5 (delinquent)
        - uid: 304 (Genesee County)

        The response will be HTML fragments or JSON with the search results.
        Parse for: parcel match, tax year, amount owed.
        """
        time.sleep(delay)

        # Placeholder: Claude Code will implement the actual HTTP request
        # after discovering the BSA AJAX endpoint
        raise NotImplementedError(
            "Implement after discovering BSA AJAX endpoint. "
            "See IMPLEMENTATION NOTE above."
        )
```

## Data Flow

```
Property.parcel_id (e.g., "41-06-538-004")
    |
    v
Strip dashes -> "4106538004"
    |
    v
Query BSA public endpoint (no auth)
    |
    v
Parse response:
  - Found in delinquent DB -> tax_status = "delinquent", extract amount
  - Not found             -> tax_status = "current"
  - Error/timeout         -> tax_status unchanged, log error
    |
    v
Update Property model
```

## Rate Limiting

- Default: 2-second delay between requests
- 648 properties at 2s each = ~22 minutes
- Run monthly or quarterly as a cron job
- This pace is indistinguishable from a person searching manually

## What This Tells Us

For Christina's compliance endgame, this data answers:

| BSA Result | Compliance Signal | Next Step |
|---|---|---|
| Not delinquent | Positive (paying taxes = some engagement) | Check images, may be compliant |
| Delinquent < 1 year | Warning (behind but not yet in forfeiture) | Outreach: remind about tax payment |
| Delinquent > 1 year | Serious (approaching forfeiture/foreclosure) | Urgent outreach or initiate reconveyance |
| Delinquent + vacant imagery | Critical (abandoned, taxes unpaid) | Recommend foreclosure/reconveyance |

## Frontend Display

The TaxInfoCard component (already in the v2 unified spec) displays this data:
- Green left-border + "Current" badge if tax_status = "current"
- Red left-border + "Delinquent" badge + amount owed if tax_status = "delinquent"
- Gray if tax_status = "unknown" (not yet checked)

## Dependencies

```
httpx          # Already in requirements (used by geocoder, imagery services)
beautifulsoup4 # Add if BSA returns HTML fragments to parse
```

## Verification

- [ ] Management command runs against a known delinquent parcel (find one on the public site first)
- [ ] Management command runs against a known current parcel (no results returned)
- [ ] Dry run mode prints results without database changes
- [ ] Rate limiting respects the delay parameter
- [ ] Parcel ID dashes are stripped correctly
- [ ] Error handling catches timeouts and bad responses gracefully
- [ ] Results visible in Django admin and frontend TaxInfoCard
