from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('stock', '0120_stockitem_size_stockitem_sterile')]
    operations = [migrations.AddField(
        model_name='stockitem', name='expiry_label',
        field=models.CharField(blank=True, default='', max_length=3, choices=[('ER', 'ER'), ('N/A', 'N/A')]),
    )]
