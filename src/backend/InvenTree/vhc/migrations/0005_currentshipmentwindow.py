from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('vhc', '0004_boxitem_expiry_label'),
    ]

    operations = [
        migrations.CreateModel(
            name='CurrentShipmentWindow',
            fields=[
                (
                    'id',
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                ('start_date', models.DateField(verbose_name='Start date')),
                ('end_date', models.DateField(verbose_name='End date')),
                ('updated', models.DateTimeField(auto_now=True)),
                (
                    'shipment',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='current_windows',
                        to='vhc.shipment',
                        verbose_name='Shipment',
                    ),
                ),
                (
                    'updated_by',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name='vhc_current_shipment_updates',
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                'verbose_name': 'VHC Current Shipment Window',
                'verbose_name_plural': 'VHC Current Shipment Windows',
                'ordering': ['-updated', '-pk'],
            },
        ),
    ]
