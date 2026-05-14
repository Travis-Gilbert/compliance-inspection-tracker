from django.core.management.base import BaseCommand

from tracker.models import EmailTemplate, Program
from tracker.services.compliance_timing import DEFAULT_PROGRAM_RULES


DEFAULT_EMAIL_TEMPLATES = [
    {
        "slug": "monthly-compliance",
        "name": "Monthly Compliance Update",
        "program_keys": ["FeaturedHomes", "Ready4Rehab"],
        "variants": {
            "ATTEMPT_1": {
                "subject": "Compliance check-in for {PropertyAddress}",
                "body": (
                    "Hi {BuyerName},\n\n"
                    "This is a friendly check-in regarding your property at "
                    "{PropertyAddress}.\n\n"
                    "As part of the {ProgramType} program, we need to verify "
                    "your progress. Your compliance update was due on {DueDate}.\n\n"
                    "Please submit your required photos and documents at your "
                    "earliest convenience.\n\n"
                    "Thank you,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "ATTEMPT_2": {
                "subject": "Second request: Compliance update for {PropertyAddress}",
                "body": (
                    "Hi {BuyerName},\n\n"
                    "This is a follow-up regarding the compliance update for "
                    "your property at {PropertyAddress}.\n\n"
                    "We previously reached out and have not yet received your "
                    "submission. Your update is now {DaysOverdue} days overdue.\n\n"
                    "Please submit your photos and documents as soon as possible "
                    "to avoid further enforcement action.\n\n"
                    "Thank you,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "WARNING": {
                "subject": "Action required: Compliance warning for {PropertyAddress}",
                "body": (
                    "Dear {BuyerName},\n\n"
                    "This letter serves as a formal warning regarding the "
                    "property at {PropertyAddress}.\n\n"
                    "Your compliance update is {DaysOverdue} days past due. "
                    "Continued non-compliance may result in default proceedings "
                    "under your {ProgramType} agreement.\n\n"
                    "Please contact our office immediately to discuss your "
                    "compliance status and submit the required documentation.\n\n"
                    "Sincerely,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "DEFAULT_NOTICE": {
                "subject": "Default Notice: {PropertyAddress}",
                "body": (
                    "Dear {BuyerName},\n\n"
                    "NOTICE OF DEFAULT\n\n"
                    "Property: {PropertyAddress}\n"
                    "Program: {ProgramType}\n"
                    "Days Overdue: {DaysOverdue}\n\n"
                    "You are hereby notified that you are in default of your "
                    "compliance obligations under the {ProgramType} program. "
                    "Your required submission was due on {DueDate}.\n\n"
                    "Failure to respond within 10 business days may result in "
                    "legal remedies as outlined in your purchase agreement.\n\n"
                    "Please contact our office immediately.\n\n"
                    "GCLBA Compliance Division"
                ),
            },
        },
    },
    {
        "slug": "demo-compliance",
        "name": "Demolition Compliance",
        "program_keys": ["Demolition"],
        "variants": {
            "ATTEMPT_1": {
                "subject": "Demolition progress update needed: {PropertyAddress}",
                "body": (
                    "Hi {BuyerName},\n\n"
                    "We are checking in on the demolition progress for "
                    "{PropertyAddress}.\n\n"
                    "Per your agreement, documentation was due by {DueDate}. "
                    "Please submit your site photos and contractor documentation.\n\n"
                    "Thank you,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "WARNING": {
                "subject": "Warning: Demolition compliance overdue for {PropertyAddress}",
                "body": (
                    "Dear {BuyerName},\n\n"
                    "Your demolition compliance documentation for "
                    "{PropertyAddress} is now {DaysOverdue} days overdue.\n\n"
                    "Required items include site photos, contractor agreement, "
                    "and disposal receipt.\n\n"
                    "Please submit immediately to avoid default proceedings.\n\n"
                    "Sincerely,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "DEFAULT_NOTICE": {
                "subject": "Default Notice: Demolition non-compliance for {PropertyAddress}",
                "body": (
                    "Dear {BuyerName},\n\n"
                    "NOTICE OF DEFAULT\n"
                    "DEMOLITION PROGRAM\n\n"
                    "Property: {PropertyAddress}\n"
                    "Days Overdue: {DaysOverdue}\n\n"
                    "You are in default of your demolition compliance obligations. "
                    "Required documentation was due on {DueDate}.\n\n"
                    "Immediate action is required. Please contact our office.\n\n"
                    "GCLBA Compliance Division"
                ),
            },
        },
    },
    {
        "slug": "vip-compliance",
        "name": "VIP Quarterly Check-In",
        "program_keys": ["VIP"],
        "variants": {
            "ATTEMPT_1": {
                "subject": "VIP quarterly check-in: {PropertyAddress}",
                "body": (
                    "Hi {BuyerName},\n\n"
                    "It is time for your quarterly VIP compliance check-in for "
                    "{PropertyAddress}.\n\n"
                    "Please submit your exterior photos and current insurance "
                    "documentation by {DueDate}.\n\n"
                    "Thank you,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "ATTEMPT_2": {
                "subject": "Second request: VIP check-in for {PropertyAddress}",
                "body": (
                    "Hi {BuyerName},\n\n"
                    "We have not received your quarterly VIP compliance update "
                    "for {PropertyAddress}. Your submission is now "
                    "{DaysOverdue} days overdue.\n\n"
                    "Please submit your photos and insurance proof as soon as possible.\n\n"
                    "Thank you,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "WARNING": {
                "subject": "Warning: VIP compliance overdue for {PropertyAddress}",
                "body": (
                    "Dear {BuyerName},\n\n"
                    "Your VIP compliance documentation for {PropertyAddress} is "
                    "{DaysOverdue} days past due.\n\n"
                    "Continued non-compliance may result in default proceedings. "
                    "Please contact our office and submit the required "
                    "documentation immediately.\n\n"
                    "Sincerely,\n"
                    "GCLBA Compliance Team"
                ),
            },
            "DEFAULT_NOTICE": {
                "subject": "Default Notice: VIP program for {PropertyAddress}",
                "body": (
                    "Dear {BuyerName},\n\n"
                    "NOTICE OF DEFAULT\n"
                    "VIP PROGRAM\n\n"
                    "Property: {PropertyAddress}\n"
                    "Days Overdue: {DaysOverdue}\n\n"
                    "You are in default of your VIP compliance obligations. "
                    "Documentation was due on {DueDate}.\n\n"
                    "Please contact our office immediately.\n\n"
                    "GCLBA Compliance Division"
                ),
            },
        },
    },
]


class Command(BaseCommand):
    help = "Seed default workflow programs and draft email templates"

    def handle(self, *args, **options):
        program_created = 0
        program_updated = 0
        for rule in DEFAULT_PROGRAM_RULES.values():
            defaults = {
                "label": rule.label,
                "cadence": rule.cadence,
                "schedule": [
                    {"day": step.day, "action": step.action, "level": step.level}
                    for step in rule.schedule
                ],
                "grace_days": rule.grace_days,
                "required_uploads": list(rule.required_uploads),
                "required_docs": list(rule.required_docs),
                "is_active": True,
            }
            _, created = Program.objects.update_or_create(key=rule.key, defaults=defaults)
            if created:
                program_created += 1
            else:
                program_updated += 1

        template_created = 0
        template_updated = 0
        for template in DEFAULT_EMAIL_TEMPLATES:
            defaults = {
                "name": template["name"],
                "program_keys": template["program_keys"],
                "variants": template["variants"],
                "status": "draft",
                "is_active": False,
            }
            _, created = EmailTemplate.objects.update_or_create(
                slug=template["slug"],
                defaults=defaults,
            )
            if created:
                template_created += 1
            else:
                template_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded workflow defaults: "
                f"{program_created} programs created, {program_updated} updated, "
                f"{template_created} templates created, {template_updated} updated"
            )
        )
