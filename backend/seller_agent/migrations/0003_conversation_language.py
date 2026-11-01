from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('seller_agent', '0002_providersecret')]
    operations = [
        # Keep old mixed-language history intact, outside new language-specific threads.
        migrations.AddField(model_name='conversation', name='language',
                            field=models.CharField(max_length=16, default='legacy'), preserve_default=False),
        migrations.AlterField(model_name='conversation', name='language',
                              field=models.CharField(max_length=16, default='en')),
    ]
