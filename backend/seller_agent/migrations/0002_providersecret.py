from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('seller_agent', '0001_initial')]
    operations = [migrations.CreateModel(
        name='ProviderSecret',
        fields=[
            ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ('updated_at', models.DateTimeField(auto_now=True)),
            ('provider', models.CharField(max_length=32, primary_key=True, serialize=False)),
            ('encrypted_key', models.TextField()),
        ],
    )]
