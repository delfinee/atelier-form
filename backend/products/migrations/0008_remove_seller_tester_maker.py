from django.db import migrations, models


def deactivate_seller_tester(apps, schema_editor):
    Maker = apps.get_model("products", "Maker")
    Maker.objects.filter(
        models.Q(name__icontains="seller tester")
        | models.Q(discipline__icontains="seller tester")
        | models.Q(slug__icontains="seller-tester")
        | models.Q(slug__startswith="acceptance-shop")
    ).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0007_product_published_at"),
    ]

    operations = [
        migrations.RunPython(deactivate_seller_tester, migrations.RunPython.noop),
    ]
