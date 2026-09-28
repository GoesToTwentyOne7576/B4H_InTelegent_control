from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boxapp', '0002_liveview'),
    ]

    operations = [
        migrations.CreateModel(
            name='LogView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'verbose_name': 'log',
                'verbose_name_plural': 'Logs',
                'abstract': False,
                'managed': False,
                'default_permissions': ('view',),
            },
        ),
    ]
