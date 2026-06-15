from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from processos.models import Processo, RegimeReajuste


class ResultadoAnalise(models.TextChoices):
    CONFORME = 'CONFORME', 'Conforme'
    RESSALVAS = 'RESSALVAS', 'Conforme com Ressalvas'
    NAO_CONFORME = 'NAO_CONFORME', 'Não Conforme'
    INDETERMINADO = 'INDETERMINADO', 'Indeterminado'


class AnaliseElegibilidade(models.Model):
    processo = models.OneToOneField(Processo, on_delete=models.CASCADE, related_name='analiseelegibilidade', verbose_name='Processo')

    enquadramento_correto = models.BooleanField(null=True, blank=True, verbose_name='Enquadramento correto')
    enquadramento_obs = models.TextField(blank=True, verbose_name='Observações - Enquadramento')

    requisitos_idade = models.BooleanField(null=True, blank=True, verbose_name='Requisitos de idade atendidos')
    requisitos_idade_obs = models.TextField(blank=True, verbose_name='Observações - Requisitos de Idade')

    tempo_contribuicao_ok = models.BooleanField(null=True, blank=True, verbose_name='Tempo de contribuição verificado')
    tempo_contribuicao_obs = models.TextField(blank=True, verbose_name='Observações - Tempo de Contribuição')

    tempo_servico_publico_ok = models.BooleanField(null=True, blank=True, verbose_name='Tempo de serviço público verificado')
    tempo_servico_publico_obs = models.TextField(blank=True, verbose_name='Observações - Tempo de Serviço Público')

    condicao_dependente_ok = models.BooleanField(null=True, blank=True, verbose_name='Condição de dependente verificada')
    condicao_dependente_obs = models.TextField(blank=True, verbose_name='Observações - Condição de Dependente')

    normas_vigentes_epoca_ok = models.BooleanField(null=True, blank=True, verbose_name='Normas vigentes à época aplicadas')
    normas_vigentes_epoca_obs = models.TextField(blank=True, verbose_name='Observações - Normas Vigentes')

    carreira_cargo_ok = models.BooleanField(null=True, blank=True, verbose_name='Carreira e cargo verificados')
    carreira_cargo_obs = models.TextField(blank=True, verbose_name='Observações - Carreira e Cargo')

    tempo_carreira_ok = models.BooleanField(null=True, blank=True, verbose_name='Tempo de carreira verificado')
    tempo_carreira_obs = models.TextField(blank=True, verbose_name='Observações - Tempo de Carreira')

    tempo_no_cargo_ok = models.BooleanField(null=True, blank=True, verbose_name='Tempo no cargo verificado')
    tempo_no_cargo_obs = models.TextField(blank=True, verbose_name='Observações - Tempo no Cargo')

    marco_temporal_ok = models.BooleanField(null=True, blank=True, verbose_name='Marco temporal de ingresso verificado')
    marco_temporal_obs = models.TextField(blank=True, verbose_name='Observações - Marco Temporal')

    resultado = models.CharField(max_length=20, choices=ResultadoAnalise.choices, default=ResultadoAnalise.INDETERMINADO, verbose_name='Resultado')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Auditor')
    data_analise = models.DateTimeField(default=timezone.now, verbose_name='Data da Análise')

    class Meta:
        verbose_name = 'Análise de Elegibilidade'
        verbose_name_plural = 'Análises de Elegibilidade'

    def __str__(self):
        return f'Elegibilidade - {self.processo}'


class AnaliseCalculo(models.Model):
    processo = models.OneToOneField(Processo, on_delete=models.CASCADE, related_name='analisecalculo', verbose_name='Processo')

    base_calculo_ok = models.BooleanField(null=True, blank=True, verbose_name='Base de cálculo correta')
    base_calculo_obs = models.TextField(blank=True, verbose_name='Observações - Base de Cálculo')

    composicao_remuneracao_ok = models.BooleanField(null=True, blank=True, verbose_name='Composição da remuneração correta')
    composicao_remuneracao_obs = models.TextField(blank=True, verbose_name='Observações - Composição da Remuneração')

    media_integralidade_ok = models.BooleanField(null=True, blank=True, verbose_name='Média/integralidade correta')
    media_integralidade_obs = models.TextField(blank=True, verbose_name='Observações - Média/Integralidade')

    cotas_familiares_ok = models.BooleanField(null=True, blank=True, verbose_name='Cotas familiares corretas')
    cotas_familiares_obs = models.TextField(blank=True, verbose_name='Observações - Cotas Familiares')

    teto_acumulacao_ok = models.BooleanField(null=True, blank=True, verbose_name='Teto/acumulação verificado')
    teto_acumulacao_obs = models.TextField(blank=True, verbose_name='Observações - Teto/Acumulação')

    reajuste_ok = models.BooleanField(null=True, blank=True, verbose_name='Reajuste correto')
    reajuste_obs = models.TextField(blank=True, verbose_name='Observações - Reajuste')
    valor_base_reajuste = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor Base para Verificação de Reajuste (R$)')
    ano_base_reajuste = models.IntegerField(null=True, blank=True, verbose_name='Ano Base do Reajuste')

    redutor_ok = models.BooleanField(null=True, blank=True, verbose_name='Redutor aplicado corretamente')
    redutor_obs = models.TextField(blank=True, verbose_name='Observações - Redutor')

    # Campos de reconstrução do benefício (PARIDADE e MÉDIA)
    metodo_reajuste_aplicado = models.CharField(
        max_length=30, blank=True, verbose_name='Método de Reajuste Aplicado',
        help_text='PARIDADE_MUNICIPAL ou INDICE_INSS'
    )
    lei_municipal_aplicada = models.CharField(max_length=300, blank=True, verbose_name='Lei Municipal Aplicada')
    indice_inss_aplicado = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        verbose_name='Índice INSS Aplicado (%)'
    )
    valor_reconstruido_ano = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor Reconstruído (R$)'
    )
    valor_devido_mes_corrente = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor Devido no Mês Corrente (R$)'
    )
    diferenca_folha = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Diferença Apurada vs Folha (R$)'
    )

    # Situação do instituidor — exclusivo para PENSAO_MORTE
    SITUACAO_INSTITUIDOR_CHOICES = [
        ('EM_ATIVIDADE', 'Servidor falecido em atividade'),
        ('APOSENTADO', 'Aposentado falecido'),
    ]
    situacao_instituidor_pensao = models.CharField(
        max_length=20,
        choices=SITUACAO_INSTITUIDOR_CHOICES,
        blank=True,
        verbose_name='Situação do Instituidor (Pensão por Morte)',
        help_text='Para pensão por morte: indica se o instituidor era servidor ativo ou aposentado.'
    )

    # ── Acumulação de benefícios (Art. 24 EC 103/2019) ───────────────────────
    houve_acumulacao = models.BooleanField(
        null=True, blank=True,
        verbose_name='Houve acumulação de benefícios?',
        help_text='Indica se o beneficiário acumula este benefício com outro (RPPS, RGPS ou cargo ativo).'
    )
    acumulacao_cargos_acumulaveis = models.BooleanField(
        null=True, blank=True,
        verbose_name='Cargos/benefícios acumuláveis (art. 37, XVI CF/88)?',
        help_text='Verdadeiro se os cargos de origem são acumuláveis por força constitucional (professor+técnico-científico, dois médicos, etc.).'
    )
    acumulacao_valor_total = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor total acumulado (R$)',
        help_text='Soma de todos os benefícios acumulados.'
    )
    acumulacao_regular = models.BooleanField(
        null=True, blank=True,
        verbose_name='Acumulação regular?',
        help_text='True = regular, False = irregular (vedada ou supera o teto).'
    )
    acumulacao_obs = models.TextField(
        blank=True,
        verbose_name='Observações — Acumulação'
    )

    # Trava de consistência: regime x método
    regime_compativel = models.BooleanField(
        null=True, blank=True,
        verbose_name='Regime de reajuste compatível com método aplicado'
    )
    regime_compativel_obs = models.TextField(
        blank=True,
        verbose_name='Obs - Compatibilidade de Regime'
    )

    resultado = models.CharField(max_length=20, choices=ResultadoAnalise.choices, default=ResultadoAnalise.INDETERMINADO, verbose_name='Resultado')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Auditor')
    data_analise = models.DateTimeField(default=timezone.now, verbose_name='Data da Análise')

    class Meta:
        verbose_name = 'Análise de Cálculo'
        verbose_name_plural = 'Análises de Cálculo'

    def clean(self):
        """Trava lógica: impede uso de método incompatível com o regime do benefício."""
        dados = getattr(self.processo, 'dados_beneficio', None)
        if not dados or not self.metodo_reajuste_aplicado:
            return
        regime = dados.regime_reajuste
        metodo = self.metodo_reajuste_aplicado
        if regime == RegimeReajuste.PARIDADE and metodo == 'INDICE_INSS':
            raise ValidationError(
                'Método de reajuste incompatível com o regime jurídico do benefício. '
                'Benefício com PARIDADE não pode usar tabela de índice INSS.'
            )
        if regime == RegimeReajuste.MEDIA and metodo == 'PARIDADE_MUNICIPAL':
            raise ValidationError(
                'Método de reajuste incompatível com o regime jurídico do benefício. '
                'Benefício calculado pela MÉDIA não pode ser vinculado ao cargo paradigma.'
            )

    def save(self, *args, **kwargs):
        # Aplica trava e registra resultado de compatibilidade automaticamente
        dados = getattr(self.processo, 'dados_beneficio', None)
        if dados and self.metodo_reajuste_aplicado:
            regime = dados.regime_reajuste
            metodo = self.metodo_reajuste_aplicado
            incompativel = (
                (regime == RegimeReajuste.PARIDADE and metodo == 'INDICE_INSS') or
                (regime == RegimeReajuste.MEDIA and metodo == 'PARIDADE_MUNICIPAL')
            )
            if incompativel:
                self.regime_compativel = False
                self.regime_compativel_obs = (
                    'Método de reajuste incompatível com o regime jurídico do benefício.'
                )
            else:
                self.regime_compativel = True
                self.regime_compativel_obs = ''
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Cálculo - {self.processo}'


class ConferenciaFolha(models.Model):
    class TipoDivergencia(models.TextChoices):
        SEM_DIVERGENCIA  = 'SEM_DIVERGENCIA',  'Sem Divergência'
        PAGAMENTO_MAIOR  = 'PAGAMENTO_MAIOR',  'Pagamento Maior que o Concedido'
        PAGAMENTO_MENOR  = 'PAGAMENTO_MENOR',  'Pagamento Menor que o Concedido'
        COM_DIVERGENCIAS = 'COM_DIVERGENCIAS', 'Com Divergências (maior e menor)'

    processo = models.OneToOneField(Processo, on_delete=models.CASCADE, related_name='conferenciafolha', verbose_name='Processo')

    valor_concedido = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor Concedido (R$)')
    valor_pago_folha = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor Pago na Folha (R$)')

    rubricas_ok = models.BooleanField(null=True, blank=True, verbose_name='Rubricas corretas')
    rubricas_obs = models.TextField(blank=True, verbose_name='Observações - Rubricas')

    reajuste_aplicado_ok = models.BooleanField(null=True, blank=True, verbose_name='Reajuste aplicado corretamente')
    reajuste_aplicado_obs = models.TextField(blank=True, verbose_name='Observações - Reajuste Aplicado')

    teto_constitucional_ok = models.BooleanField(null=True, blank=True, verbose_name='Teto constitucional observado')
    teto_constitucional_obs = models.TextField(blank=True, verbose_name='Observações - Teto Constitucional')

    # Valor esperado calculado automaticamente (valor_concedido + reajustes)
    valor_esperado = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor Esperado após Reajustes (R$)'
    )

    tipo_divergencia = models.CharField(max_length=20, choices=TipoDivergencia.choices, default=TipoDivergencia.SEM_DIVERGENCIA, verbose_name='Tipo de Divergência')
    impacto_financeiro_estimado = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name='Impacto Financeiro Estimado (R$)')

    observacoes = models.TextField(blank=True, verbose_name='Observações')

    resultado = models.CharField(max_length=20, choices=ResultadoAnalise.choices, default=ResultadoAnalise.INDETERMINADO, verbose_name='Resultado')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Auditor')
    data_analise = models.DateTimeField(default=timezone.now, verbose_name='Data da Análise')

    class Meta:
        verbose_name = 'Conferência de Folha'
        verbose_name_plural = 'Conferências de Folha'

    def __str__(self):
        return f'Folha - {self.processo}'

    @property
    def divergencia_valor(self):
        if self.valor_pago_folha is not None and self.valor_esperado is not None:
            return self.valor_pago_folha - self.valor_esperado
        return None


class DivergenciaFolha(models.Model):
    class Tipo(models.TextChoices):
        TRIENIO_MAIOR    = 'TRIENIO_MAIOR',    'Triênio calculado a maior'
        REAJUSTE_MENOR   = 'REAJUSTE_MENOR',   'Reajuste aplicado a menor'
        REAJUSTE_MAIOR   = 'REAJUSTE_MAIOR',   'Reajuste aplicado a maior'
        RUBRICA_INDEVIDA = 'RUBRICA_INDEVIDA', 'Rubrica indevida'
        OUTRO_MAIOR      = 'OUTRO_MAIOR',      'Pagamento a maior (outro)'
        OUTRO_MENOR      = 'OUTRO_MENOR',      'Pagamento a menor (outro)'

    class Impacto(models.TextChoices):
        MAIOR = 'MAIOR', 'Pagamento a maior'
        MENOR = 'MENOR', 'Pagamento a menor'

    conferencia = models.ForeignKey(
        ConferenciaFolha, on_delete=models.CASCADE,
        related_name='divergencias', verbose_name='Conferência'
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices, verbose_name='Tipo')
    impacto = models.CharField(max_length=5, choices=Impacto.choices, verbose_name='Impacto')
    valor = models.DecimalField(max_digits=12, decimal_places=2, verbose_name='Valor (R$)')
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    base_legal = models.TextField(blank=True, verbose_name='Base Legal')
    detectado_automaticamente = models.BooleanField(default=False)
    achado_gerado = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Divergência de Folha'
        verbose_name_plural = 'Divergências de Folha'
        ordering = ['tipo']

    def __str__(self):
        return f'{self.get_tipo_display()} — R$ {self.valor}'


class AchadoAuditoria(models.Model):
    class Classificacao(models.TextChoices):
        CONFORME = 'CONFORME', 'Conforme'
        CONFORME_RESSALVAS = 'CONFORME_RESSALVAS', 'Conforme com Ressalvas'
        NAO_CONFORME = 'NAO_CONFORME', 'Não Conforme'
        INDETERMINADO = 'INDETERMINADO', 'Indeterminado'

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name='achados', verbose_name='Processo')
    classificacao = models.CharField(max_length=20, choices=Classificacao.choices, verbose_name='Classificação')
    descricao = models.TextField(verbose_name='Descrição do Achado')
    normas_aplicaveis = models.TextField(blank=True, verbose_name='Normas Aplicáveis')
    impacto_financeiro = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True, verbose_name='Impacto Financeiro (R$)')
    recomendacao = models.TextField(blank=True, verbose_name='Recomendação')
    data_registro = models.DateTimeField(default=timezone.now, verbose_name='Data de Registro')

    class Meta:
        verbose_name = 'Achado de Auditoria'
        verbose_name_plural = 'Achados de Auditoria'
        ordering = ['-data_registro']

    def __str__(self):
        return f'Achado - {self.processo} ({self.get_classificacao_display()})'


class NotaTecnica(models.Model):
    processo = models.OneToOneField(Processo, on_delete=models.CASCADE, related_name='nota_tecnica', verbose_name='Processo')
    texto = models.TextField(verbose_name='Texto da Nota Técnica')
    limitacao_documental = models.TextField(blank=True, verbose_name='Limitações Documentais')
    auditor = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Auditor')
    data_registro = models.DateTimeField(default=timezone.now, verbose_name='Data de Registro')
    data_atualizacao = models.DateTimeField(auto_now=True, verbose_name='Última Atualização')

    class Meta:
        verbose_name = 'Nota Técnica'
        verbose_name_plural = 'Notas Técnicas'

    def __str__(self):
        return f'Nota Técnica - {self.processo}'
