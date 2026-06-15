from django.db import models
from django.utils import timezone
from processos.models import TipoBeneficio


class EmpresaAuditora(models.Model):
    nome = models.CharField(max_length=200, verbose_name='Nome')
    sigla = models.CharField(max_length=20, blank=True, verbose_name='Sigla')
    cnpj = models.CharField(max_length=18, blank=True, verbose_name='CNPJ')
    logo = models.ImageField(upload_to='empresas/logos/', blank=True, null=True, verbose_name='Logo')
    ativa = models.BooleanField(default=True, verbose_name='Ativa')

    class Meta:
        verbose_name = 'Empresa Auditora'
        verbose_name_plural = 'Empresas Auditoras'
        ordering = ['nome']

    def __str__(self):
        return self.sigla or self.nome


class Instituto(models.Model):
    empresa_auditora = models.ForeignKey(
        EmpresaAuditora, on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name='Empresa Auditora',
        related_name='institutos',
    )
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
    subsidio_prefeito = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Subsídio do Prefeito (R$)',
        help_text='Teto remuneratório dos servidores e pensionistas do RPPS (art. 37, XI CF/88). Exceção: procuradores municipais possuem teto próprio.',
    )

    # ── Adicional por Tempo de Serviço (Triênio) ──────────────────────────
    norma_trienio = models.CharField(
        max_length=300, blank=True,
        verbose_name='Base Legal do Triênio',
        help_text='Ex: Art. 71 da Lei nº 05/1991',
    )
    trienio_primeiro_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name='1º Triênio (%)',
        help_text='Percentual do primeiro triênio. Calculado sobre o vencimento base.',
    )
    trienio_demais_percentual = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        verbose_name='Demais Triênios (%)',
        help_text='Percentual de cada triênio a partir do 2º. Calculado sobre o vencimento base.',
    )
    trienio_limite_periodos = models.IntegerField(
        null=True, blank=True,
        verbose_name='Limite de Triênios',
        help_text='Número máximo de triênios passíveis de acumulação.',
    )

    observacoes = models.TextField(blank=True, verbose_name='Observações')

    def percentual_trienio_para(self, n_trienios):
        """
        Retorna o percentual total de triênio para N períodos completos.
        Fórmula (Art. 71 Lei 05/1991): 1º = trienio_primeiro_percentual,
        demais = trienio_demais_percentual cada, limitado a trienio_limite_periodos.
        """
        if not n_trienios or not self.trienio_primeiro_percentual:
            return None
        from decimal import Decimal
        limite = self.trienio_limite_periodos or 99
        n = min(int(n_trienios), limite)
        if n <= 0:
            return Decimal('0')
        primeiro = self.trienio_primeiro_percentual
        demais = self.trienio_demais_percentual or Decimal('0')
        return primeiro + demais * (n - 1)

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


class LeiMunicipalReajuste(models.Model):
    """Lei municipal que concede reajuste aos servidores ativos e/ou inativos."""
    instituto       = models.ForeignKey(Instituto, on_delete=models.CASCADE,
                                        related_name='leis_reajuste', verbose_name='Instituto')
    numero          = models.CharField(max_length=50, verbose_name='Número da Lei',
                                       help_text='Ex: 1.582/2025')
    descricao       = models.CharField(max_length=300, blank=True, verbose_name='Ementa')
    data_publicacao = models.DateField(verbose_name='Data de Publicação')
    data_vigencia   = models.DateField(verbose_name='Data de Vigência (efeitos financeiros)')
    percentual      = models.DecimalField(max_digits=7, decimal_places=4,
                                          verbose_name='Percentual de Reajuste (%)')
    base_indice     = models.CharField(max_length=100, blank=True, verbose_name='Índice de Referência',
                                       help_text='Ex: IPCA 2024, IPC-A, INPC')
    base_legal      = models.TextField(blank=True, verbose_name='Fundamento Legal')
    aplica_inativos = models.BooleanField(default=True,
                                          verbose_name='Aplica-se a proventos de inatividade')
    aplica_pensoes  = models.BooleanField(default=True,
                                          verbose_name='Aplica-se a pensões')
    arquivo         = models.FileField(upload_to='leis_municipais/', blank=True,
                                       verbose_name='Arquivo PDF')
    observacoes     = models.TextField(blank=True, verbose_name='Observações')
    data_cadastro   = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name          = 'Lei Municipal de Reajuste'
        verbose_name_plural   = 'Leis Municipais de Reajuste'
        ordering              = ['data_vigencia']
        unique_together       = [('instituto', 'numero')]

    def __str__(self):
        return f'Lei nº {self.numero} — {self.percentual}% ({self.instituto.municipio})'
