from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analise', '0005_add_situacao_instituidor_pensao'),
    ]

    operations = [
        migrations.AddField(
            model_name='analisecalculo',
            name='houve_acumulacao',
            field=models.BooleanField(
                blank=True, null=True,
                verbose_name='Houve acumulação de benefícios?',
            ),
        ),
        migrations.AddField(
            model_name='analisecalculo',
            name='acumulacao_cargos_acumulaveis',
            field=models.BooleanField(
                blank=True, null=True,
                verbose_name='Cargos/benefícios acumuláveis (art. 37, XVI CF/88)?',
            ),
        ),
        migrations.AddField(
            model_name='analisecalculo',
            name='acumulacao_valor_total',
            field=models.DecimalField(
                blank=True, null=True,
                max_digits=12, decimal_places=2,
                verbose_name='Valor total acumulado (R$)',
            ),
        ),
        migrations.AddField(
            model_name='analisecalculo',
            name='acumulacao_regular',
            field=models.BooleanField(
                blank=True, null=True,
                verbose_name='Acumulação regular?',
            ),
        ),
        migrations.AddField(
            model_name='analisecalculo',
            name='acumulacao_obs',
            field=models.TextField(
                blank=True,
                verbose_name='Observações — Acumulação',
            ),
        ),
    ]
