from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from tracker.services.twenty_schema import TwentySchemaError, bootstrap_twenty_schema


class Command(BaseCommand):
    help = "Create or verify the GCLBA Twenty CRM schema, views, navigation, and read-only role."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="print planned schema actions without changing the Twenty workspace",
        )
        parser.add_argument(
            "--schema-only",
            action="store_true",
            help="create objects and fields but skip views, navigation, and roles",
        )
        parser.add_argument(
            "--keep-default-nav",
            action="store_true",
            help="leave default Companies and Opportunities navigation items visible",
        )
        parser.add_argument(
            "--show-actions",
            action="store_true",
            help="print each schema action after the summary",
        )

    def handle(self, *args, **opts):
        try:
            result = bootstrap_twenty_schema(
                dry_run=opts["dry_run"],
                include_workspace_polish=not opts["schema_only"],
                hide_default_noise=not opts["keep_default_nav"],
            )
        except (ValueError, TwentySchemaError) as exc:
            raise CommandError(str(exc)) from exc

        prefix = "dry-run " if opts["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}twenty schema objects created={result.objects_created} "
                f"existing={result.objects_existing} fields created={result.fields_created} "
                f"existing={result.fields_existing} updated={result.fields_updated} "
                f"views created={result.views_created} "
                f"existing={result.views_existing} nav created={result.navigation_created} "
                f"existing={result.navigation_existing} nav hidden={result.navigation_hidden} "
                f"roles created={result.roles_created} existing={result.roles_existing}"
            )
        )
        if opts["show_actions"]:
            for action in result.actions:
                self.stdout.write(f"- {action}")
