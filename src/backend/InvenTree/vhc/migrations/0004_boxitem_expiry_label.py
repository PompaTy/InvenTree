from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('vhc', '0003_boxitem_expiry_date_boxitem_size_boxitem_sterile'), ('stock', '0121_stockitem_expiry_label')]
    operations = [migrations.AddField(
        model_name='boxitem', name='expiry_label',
        field=models.CharField(blank=True, default='', max_length=3, choices=[('ER', 'ER'), ('N/A', 'N/A')]),
    )]
