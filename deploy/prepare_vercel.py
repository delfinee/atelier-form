"""Prepare static assets and the seller assistant's additive production schema."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.core.management import call_command
from django.db import connection, transaction
from django.db.migrations.executor import MigrationExecutor

# Preview builds may share production environment variables. They must not
# migrate a database. The production deploy only applies the existing seller
# assistant migration, which creates new tables without changing products.
if os.environ.get("VERCEL_ENV") == "production":
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [74132026])
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes("seller_agent")
        plan = executor.migration_plan(targets)
        if any(backwards or migration.app_label != "seller_agent"
               for migration, backwards in plan):
            raise RuntimeError("Apply prerequisite schema migrations separately before deploying seller AI.")
        print("Pending seller assistant migrations:", [migration.name for migration, _ in plan])
        call_command("migrate", "seller_agent", interactive=False)

call_command("collectstatic", interactive=False, verbosity=1)
