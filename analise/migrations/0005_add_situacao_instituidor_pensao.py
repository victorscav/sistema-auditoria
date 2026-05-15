from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analise', '0004_add_elegibilidade_calculo_novos_campos'),
    ]

    operations = [
        migrations.AddField(
            model_name='analisecalculo',
            name='situacao_instituidor_pensao',
            field=models.CharField(
                blank=True,
                choices=[('EM_ATIVIDADE', 'Servidor falecido em atividade'), ('APOSENTADO', 'Aposentado falecido')],
                help_text='Para pensão por morte: indica se o instituidor era servidor ativo ou aposentado.',
                max_length=20,
                verbose_name='Situação do Instituidor (Pensão por Morte)',
            ),
        ),
    ]
