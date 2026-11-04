from django.db import migrations, models


def backfill_publication_time(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    Product.objects.using(schema_editor.connection.alias).filter(
        is_active=True, published_at__isnull=True).update(published_at=models.F('created_at'))


class Migration(migrations.Migration):
    dependencies = [('products', '0006_producttexttranslation')]
    operations = [
        migrations.AddField(model_name='product', name='published_at',
            field=models.DateTimeField(blank=True, db_index=True, editable=False, null=True)),
        migrations.RunPython(backfill_publication_time, migrations.RunPython.noop),
    ]
