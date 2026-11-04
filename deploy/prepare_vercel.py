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
# migrate a database. Production may create the seller tables and the additive
# product-name translation table. Other catalogue schema changes stay manual.
if os.environ.get("VERCEL_ENV") == "production":
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s)", [74132026])
        executor = MigrationExecutor(connection)
        targets = executor.loader.graph.leaf_nodes("seller_agent") + [('products', '0007_product_published_at')]
        plan = executor.migration_plan(targets)
        if any(backwards or not (migration.app_label == "seller_agent" or
                               (migration.app_label == 'products' and migration.name in {'0005_productnametranslation', '0006_producttexttranslation', '0007_product_published_at'}))
               for migration, backwards in plan):
            raise RuntimeError("Apply prerequisite schema migrations separately before deploying seller AI.")
        print("Pending additive migrations:", [(migration.app_label, migration.name) for migration, _ in plan])
        call_command("migrate", "products", "0007_product_published_at", interactive=False)
        call_command("migrate", "seller_agent", interactive=False)
        from accounts.demo import sync_demo_seller_name
        sync_demo_seller_name()

call_command("collectstatic", interactive=False, verbosity=1)
