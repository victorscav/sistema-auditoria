from django.db import models
from processos.models import TipoBeneficio


class Instituto(models.Model):
    nome = models.CharField(max_length=200, verbose_name='Nome')
    cnpj = models.CharField(max_length=18, blank=True, verbose_name='CNPJ')
    estado = models.CharField(max_length=2, verbose_name='Estado (UF)')
    municipio = models.CharField(max_length=100, verbose_name='Município')
    lei_organica = models.CharField(max_length=200, blank=True, verbose_name='Lei Orgânica')
    ativo = models.BooleanField(default=True, verbose_name='Ativo')
    aderiu_ec103_2019 = models.BooleanField(
        default=False,
        verbose_name='Aderiu à Reforma da EC 103/2019',
        help_text='Marque se o município promulgou lei própria de reforma previdenciária com base na EC 103/2019, revogando as regras constitucionais anteriores.',
    )
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    class Meta:
        verbose_name = 'Instituto RPPS'
        verbose_name_plural = 'Institutos RPPS'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.municipio}/{self.estado})'


class RegraAposentadoria(models.Model):
    instituto = models.ForeignKey(Instituto, on_delete=models.CASCADE, related_name='regras', verbose_name='Instituto')
    tipo_beneficio = models.CharField(max_length=30, choices=TipoBeneficio.choices, verbose_name='Tipo de Benefício')
    norma_base = models.CharField(max_length=300, verbose_name='Norma Base')
    vigente_desde = models.DateField(verbose_name='Vigente Desde')
    vigente_ate = models.DateField(null=True, blank=True, verbose_name='Vigente Até')
    ativa = models.BooleanField(default=True, verbose_name='Ativa')

    # Elegibilidade
    idade_minima_homem = models.IntegerField(null=True, blank=True, verbose_name='Idade Mínima (Homem)')
    idade_minima_mulher = models.IntegerField(null=True, blank=True, verbose_name='Idade Mínima (Mulher)')
    tempo_contribuicao_homem = models.IntegerField(null=True, blank=True, verbose_name='Tempo de Contribuição - Homem (anos)')
    tempo_contribuicao_mulher = models.IntegerField(null=True, blank=True, verbose_name='Tempo de Contribuição - Mulher (anos)')
    tempo_servico_publico = models.IntegerField(null=True, blank=True, verbose_name='Tempo de Serviço Público (anos)')
    tempo_carreira = models.IntegerField(null=True, blank=True, verbose_name='Tempo de Carreira (anos)')
    tempo_no_cargo = models.IntegerField(null=True, blank=True, verbose_name='Tempo no Cargo (anos)')

    # Cálculo
    integralidade = models.BooleanField(null=True, blank=True, verbose_name='Integralidade')
    proporcionalidade_formula = models.CharField(max_length=200, blank=True, verbose_name='Fórmula de Proporcionalidade')
    teto_remuneratorio = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Teto Remuneratório (R$)')
    criterio_reajuste = models.CharField(max_length=50, blank=True, verbose_name='Critério de Reajuste')

    # Pensão por morte
    cota_inicial_percentual = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Cota Inicial (%)')
    cota_por_dependente_percentual = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name='Cota por Dependente (%)')
    reversibilidade = models.BooleanField(null=True, blank=True, verbose_name='Reversibilidade')

    norma_federal = models.BooleanField(
        default=False,
        verbose_name='Norma Federal/Constitucional',
        help_text='Regras oriundas da CF/88, EC 41/2003, EC 47/2005, EC 70/2012 — exibidas em todos os institutos que não aderiram à EC 103/2019.',
    )
    observacoes = models.TextField(blank=True, verbose_name='Observações')

    class Meta:
        verbose_name = 'Regra de Aposentadoria'
        verbose_name_plural = 'Regras de Aposentadoria'
        ordering = ['tipo_beneficio', '-vigente_desde']

    def __str__(self):
        return f'{self.get_tipo_beneficio_display()} — {self.norma_base} ({self.instituto})'
