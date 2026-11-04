from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('products', '0005_productnametranslation')]
    operations = [migrations.CreateModel(
        name='ProductTextTranslation',
        fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('field', models.CharField(max_length=32)),
            ('source_text', models.TextField()),
            ('english', models.TextField(blank=True)),
            ('chinese', models.TextField(blank=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                related_name='text_translations', to='products.product')),
        ],
        options={'constraints': [models.UniqueConstraint(fields=('product', 'field'), name='product_text_translation_once')]},
    )]
