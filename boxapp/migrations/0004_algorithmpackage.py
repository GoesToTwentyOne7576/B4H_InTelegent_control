from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('boxapp', '0003_logview'),
    ]

    operations = [
        migrations.CreateModel(
            name='AlgorithmPackage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'verbose_name': 'algorithm package',
                'verbose_name_plural': 'Algorithms',
                'abstract': False,
                'managed': False,
                'default_permissions': ('view',),
            },
        ),
    ]
