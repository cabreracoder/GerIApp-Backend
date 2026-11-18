from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE historia_clinicas '
                        'ADD COLUMN IF NOT EXISTS rangos_vitales_json jsonb;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE historia_clinicas '
                        'DROP COLUMN IF EXISTS rangos_vitales_json;'
                    ),
                ),
                migrations.RunSQL(
                    sql=(
                        'ALTER TABLE signos_vitales '
                        'ADD COLUMN IF NOT EXISTS alerta_generada text;'
                    ),
                    reverse_sql=(
                        'ALTER TABLE signos_vitales '
                        'DROP COLUMN IF EXISTS alerta_generada;'
                    ),
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name='historiaclinicas',
                    name='rangos_vitales_json',
                    field=models.JSONField(blank=True, null=True),
                ),
                migrations.AddField(
                    model_name='signosvitales',
                    name='alerta_generada',
                    field=models.TextField(blank=True, null=True),
                ),
            ],
        ),
    ]
