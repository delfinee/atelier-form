from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('products', '0004_alter_productimage_image')]
    operations = [migrations.CreateModel(
        name='ProductNameTranslation',
        fields=[
            ('product', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                primary_key=True, related_name='name_translation', serialize=False, to='products.product')),
            ('source_name', models.CharField(max_length=160)),
            ('english', models.CharField(blank=True, max_length=160)),
            ('chinese', models.CharField(blank=True, max_length=160)),
            ('updated_at', models.DateTimeField(auto_now=True)),
        ],
    )]
