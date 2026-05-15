from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('institutos', '0003_add_tempo_carreira'),
    ]

    operations = [
        migrations.AddField(
            model_name='instituto',
            name='subsidio_prefeito',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text='Teto remuneratório dos servidores e pensionistas do RPPS (art. 37, XI CF/88). Exceção: procuradores municipais possuem teto próprio.',
                max_digits=12,
                null=True,
                verbose_name='Subsídio do Prefeito (R$)',
            ),
        ),
    ]
