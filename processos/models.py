from django.db import models
from django.utils import timezone


# ── Helpers de tempo previdenciário ──────────────────────────────────────────

def _dias(anos, meses, dias):
    """Converte anos/meses/dias em total de dias (padrão RPPS: 1 ano=365, 1 mês=30)."""
    return int(anos or 0) * 365 + int(meses or 0) * 30 + int(dias or 0)


def _dias_para_amd(total_dias):
    """Converte dias totais de volta para (anos, meses, dias)."""
    anos  = total_dias // 365
    resto = total_dias % 365
    meses = resto // 30
    dias  = resto % 30
    return anos, meses, dias


def _fmt_amd(anos, meses, dias):
    partes = []
    if anos:  partes.append(f'{anos} ano{"s" if anos != 1 else ""}')
    if meses: partes.append(f'{meses} {"mês" if meses == 1 else "meses"}')
    if dias:  partes.append(f'{dias} dia{"s" if dias != 1 else ""}')
    return ', '.join(partes) if partes else '0 dias'


class RegimeReajuste(models.TextChoices):
    PARIDADE = 'PARIDADE', 'Paridade (vinculado ao cargo ativo)'
    MEDIA = 'MEDIA', 'Média (índice INSS)'
    NAO_DEFINIDO = 'NAO_DEFINIDO', 'Não Definido'


class TipoBeneficio(models.TextChoices):
    APOS_VOLUNTARIA           = 'APOS_VOLUNTARIA',           'Aposentadoria Voluntária por Idade e Tempo de Contribuição (Integral)'
    APOS_VOLUNTARIA_PROP      = 'APOS_VOLUNTARIA_PROP',      'Aposentadoria Voluntária por Idade e Tempo de Contribuição (Proporcional)'
    APOS_VOLUNTARIA_POR_IDADE = 'APOS_VOLUNTARIA_POR_IDADE', 'Aposentadoria Voluntária por Idade'
    APOS_VOLUNTARIA_PROP_IDADE= 'APOS_VOLUNTARIA_PROP_IDADE','Aposentadoria Voluntária por Idade com Proventos Proporcionais'
    APOS_VOLUNTARIA_IDADE_TC  = 'APOS_VOLUNTARIA_IDADE_TC',  'Aposentadoria Voluntária por Idade e Tempo de Contribuição'
    APOS_INCAPACIDADE         = 'APOS_INCAPACIDADE',         'Aposentadoria por Invalidez Permanente (Integral)'
    APOS_INVALIDEZ_PERMANENTE = 'APOS_INVALIDEZ_PERMANENTE', 'Aposentadoria por Invalidez Permanente (Proporcional)'
    APOS_COMPULSORIA          = 'APOS_COMPULSORIA',          'Aposentadoria Compulsória'
    APOS_ESPECIAL_MAGISTERIO  = 'APOS_ESPECIAL_MAGISTERIO',  'Aposentadoria Especial do Magistério'
    PENSAO_MORTE              = 'PENSAO_MORTE',              'Pensão por Morte'
    REVISAO_REENQUADRAMENTO   = 'REVISAO_REENQUADRAMENTO',   'Revisão/Reenquadramento'


class StatusProcesso(models.TextChoices):
    PENDENTE = 'PENDENTE', 'Pendente'
    EM_ANALISE = 'EM_ANALISE', 'Em Análise'
    CONCLUIDO = 'CONCLUIDO', 'Concluído'
    ARQUIVADO = 'ARQUIVADO', 'Arquivado'


class StatusLote(models.TextChoices):
    ABERTO = 'ABERTO', 'Aberto'
    EM_ANDAMENTO = 'EM_ANDAMENTO', 'Em Andamento'
    CONCLUIDO = 'CONCLUIDO', 'Concluído'


class Lote(models.Model):
    numero = models.CharField(max_length=50, unique=True, verbose_name='Número do Lote')
    descricao = models.TextField(blank=True, verbose_name='Descrição')
    data_criacao = models.DateTimeField(default=timezone.now, verbose_name='Data de Criação')
    status = models.CharField(max_length=20, choices=StatusLote.choices, default=StatusLote.ABERTO, verbose_name='Status')

    class Meta:
        verbose_name = 'Lote'
        verbose_name_plural = 'Lotes'
        ordering = ['-data_criacao']

    def __str__(self):
        return f'Lote {self.numero}'

    @property
    def total_processos(self):
        return self.processo_set.count()

    @property
    def processos_concluidos(self):
        return self.processo_set.filter(status_processo=StatusProcesso.CONCLUIDO).count()

    @property
    def percentual_conclusao(self):
        total = self.total_processos
        if total == 0:
            return 0
        return round((self.processos_concluidos / total) * 100)


class Beneficiario(models.Model):
    nome = models.CharField(max_length=255, verbose_name='Nome Completo')
    cpf = models.CharField(max_length=14, unique=True, verbose_name='CPF')
    matricula = models.CharField(max_length=50, blank=True, verbose_name='Matrícula')
    municipio = models.CharField(max_length=100, blank=True, verbose_name='Município')
    cargo = models.CharField(max_length=200, blank=True, verbose_name='Cargo/Função')
    carreira = models.CharField(max_length=200, blank=True, verbose_name='Carreira')

    class Meta:
        verbose_name = 'Beneficiário'
        verbose_name_plural = 'Beneficiários'
        ordering = ['nome']

    def __str__(self):
        return f'{self.nome} ({self.cpf})'


class Processo(models.Model):
    numero = models.CharField(max_length=100, unique=True, verbose_name='Número do Processo')
    beneficiario = models.ForeignKey(Beneficiario, on_delete=models.PROTECT, verbose_name='Beneficiário')
    tipo_beneficio = models.CharField(max_length=50, choices=TipoBeneficio.choices, verbose_name='Tipo de Benefício')
    status_processo = models.CharField(max_length=20, choices=StatusProcesso.choices, default=StatusProcesso.PENDENTE, verbose_name='Status')
    data_concessao = models.DateField(null=True, blank=True, verbose_name='Data de Concessão')
    data_publicacao = models.DateField(null=True, blank=True, verbose_name='Data de Publicação')
    lote = models.ForeignKey(Lote, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Lote')
    instituto = models.ForeignKey('institutos.Instituto', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Instituto RPPS')
    observacoes = models.TextField(blank=True, verbose_name='Observações')
    limitacao_tecnica = models.TextField(blank=True, verbose_name='Limitações Técnicas', help_text='Registre aqui a ausência ou insuficiência de documentos essenciais (cf. cláusula 12.4)')
    data_cadastro = models.DateTimeField(default=timezone.now, verbose_name='Data de Cadastro')

    class Meta:
        verbose_name = 'Processo'
        verbose_name_plural = 'Processos'
        ordering = ['-data_cadastro']

    def __str__(self):
        return f'Processo {self.numero} - {self.beneficiario.nome}'

    def tempo_averbado_total_dias(self):
        """Soma dos dias averbuláveis de todas as certidões (já deduzindo concomitâncias)."""
        return sum(c.dias_averbar for c in self.certidoes_tempo.all())

    def tempo_averbado_display(self):
        return _fmt_amd(*_dias_para_amd(self.tempo_averbado_total_dias()))

    # ── Média de contribuições (regime MÉDIA) ─────────────────────────────
    def media_contribuicoes_simples(self):
        """Média simples de todos os salários de contribuição registrados."""
        from decimal import Decimal
        qs = self.contribuicoes.all()
        if not qs.exists():
            return None
        valores = [c.valor_efetivo for c in qs]
        return (sum(valores) / Decimal(len(valores))).quantize(Decimal('0.01'))

    def media_contribuicoes_80(self):
        """
        Média dos 80% maiores salários de contribuição (regra da Lei 10.887/2004).
        Descarta os 20% menores e calcula a média dos restantes.
        """
        from decimal import Decimal
        qs = self.contribuicoes.all()
        if not qs.exists():
            return None
        valores = sorted([c.valor_efetivo for c in qs], reverse=True)
        n_80 = max(1, round(len(valores) * 0.8))
        top = valores[:n_80]
        return (sum(top) / Decimal(len(top))).quantize(Decimal('0.01'))

    def get_resultado_analise(self):
        resultados = []
        try:
            resultados.append(self.analiseelegibilidade.resultado)
        except Exception:
            pass
        try:
            resultados.append(self.analisecalculo.resultado)
        except Exception:
            pass
        try:
            resultados.append(self.conferenciafolha.resultado)
        except Exception:
            pass

        if not resultados:
            return None
        if 'NAO_CONFORME' in resultados:
            return 'NAO_CONFORME'
        if 'RESSALVAS' in resultados:
            return 'RESSALVAS'
        if all(r == 'CONFORME' for r in resultados):
            return 'CONFORME'
        return 'INDETERMINADO'


class ReajusteINSS(models.Model):
    ano = models.IntegerField(unique=True, verbose_name='Ano')
    vigencia = models.DateField(verbose_name='Vigência')
    percentual_acima_minimo = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='% Reajuste (acima do mínimo)')
    percentual_piso = models.DecimalField(max_digits=5, decimal_places=2, verbose_name='% Reajuste (benefícios no piso)')
    salario_minimo = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Salário Mínimo (R$)')
    teto_inss = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='Teto INSS (R$)')
    base_legal = models.CharField(max_length=200, blank=True, verbose_name='Base Legal')
    fatores_pro_rata = models.JSONField(
        default=dict, blank=True,
        verbose_name='Fatores Pro-Rata por Mês de Concessão',
        help_text=(
            'Para benefícios concedidos no ano anterior ao reajuste. '
            'Chave: mês de concessão (1–12). Valor: percentual de reajuste. '
            'Ex: {"1": 3.90, "2": 3.90, "3": 2.38, ...}'
        ),
    )

    class Meta:
        verbose_name = 'Reajuste INSS'
        verbose_name_plural = 'Reajustes INSS'
        ordering = ['-ano']

    def __str__(self):
        return f'Reajuste INSS {self.ano} ({self.percentual_acima_minimo}%)'

    def percentual_para(self, data_concessao):
        """
        Retorna o percentual correto de reajuste considerando pro-rata.
        - Benefícios do ano anterior (ano - 1): busca pelo mês de concessão.
        - Benefícios de anos anteriores (< ano - 1): busca pela chave "0"
          (esses já receberam um pro-rata parcial no reajuste anterior e agora
          recebem o fator equivalente a "até janeiro" do ano corrente).
        """
        from decimal import Decimal as _D
        if not data_concessao or not self.fatores_pro_rata:
            return self.percentual_acima_minimo
        if data_concessao.year == self.ano - 1:
            chave = str(data_concessao.month)
            if chave in self.fatores_pro_rata:
                return _D(str(self.fatores_pro_rata[chave]))
        elif data_concessao.year < self.ano - 1:
            if '0' in self.fatores_pro_rata:
                return _D(str(self.fatores_pro_rata['0']))
        return self.percentual_acima_minimo


class DadosBeneficio(models.Model):
    processo = models.OneToOneField(Processo, on_delete=models.CASCADE, related_name='dados_beneficio', verbose_name='Processo')
    base_calculo = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Base de Cálculo (R$)')
    valor_concedido = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor Concedido (R$)')
    valor_pago_folha = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, verbose_name='Valor Pago na Folha (R$)')
    tempo_contribuicao = models.CharField(max_length=50, blank=True, verbose_name='Tempo de Contribuição')
    tempo_servico_publico = models.CharField(max_length=50, blank=True, verbose_name='Tempo de Serviço Público')
    idade_concessao = models.IntegerField(null=True, blank=True, verbose_name='Idade na Concessão')
    regra_aplicada = models.CharField(max_length=200, blank=True, verbose_name='Regra Aplicada')
    integralidade = models.BooleanField(null=True, blank=True, verbose_name='Integralidade')
    proporcionalidade = models.CharField(max_length=50, blank=True, verbose_name='Proporcionalidade')
    teto_constitucional_observado = models.BooleanField(null=True, blank=True, verbose_name='Teto Constitucional Observado')
    criterio_reajuste = models.CharField(max_length=200, blank=True, verbose_name='Critério de Reajuste')
    regime_reajuste = models.CharField(
        max_length=20, choices=RegimeReajuste.choices,
        default=RegimeReajuste.NAO_DEFINIDO, verbose_name='Regime de Reajuste'
    )

    # Cargo paradigma (para benefícios com PARIDADE)
    cargo_paradigma = models.CharField(max_length=200, blank=True, verbose_name='Cargo Paradigma')
    classe_paradigma = models.CharField(max_length=100, blank=True, verbose_name='Classe do Cargo Paradigma')
    nivel_paradigma = models.CharField(max_length=100, blank=True, verbose_name='Nível do Cargo Paradigma')
    referencia_paradigma = models.CharField(max_length=100, blank=True, verbose_name='Referência do Cargo Paradigma')

    # Média das contribuições previdenciárias (regime MÉDIA — importada da planilha)
    media_contribuicoes = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Média das Contribuições (R$)',
        help_text='Média das contribuições previdenciárias apurada para cálculo do benefício (regime MÉDIA).'
    )

    # Proporcionalidade (regime proventos proporcionais)
    proporcionalidade_percentual = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        verbose_name='Percentual de Proporcionalidade (%)',
        help_text='Fração do benefício proporcional aplicada. Ex: 55.4155 para 6008/10950.'
    )

    # Tempos adicionais exigidos pela regra municipal
    tempo_carreira = models.CharField(max_length=50, blank=True, verbose_name='Tempo de Carreira')
    tempo_no_cargo = models.CharField(max_length=50, blank=True, verbose_name='Tempo no Cargo')
    marco_temporal_ingresso = models.DateField(null=True, blank=True, verbose_name='Marco Temporal de Ingresso no Serviço Público')

    class Meta:
        verbose_name = 'Dados do Benefício'
        verbose_name_plural = 'Dados dos Benefícios'

    def __str__(self):
        return f'Dados - {self.processo}'


class OrigemTempo(models.TextChoices):
    INSS_RGPS        = 'INSS_RGPS',        'RGPS/INSS'
    INSS_MUNICIPIO   = 'INSS_MUNICIPIO',   'INSS Município (órgão público)'
    RPPS_MUNICIPAL   = 'RPPS_MUNICIPAL',   'RPPS Municipal (outro município)'
    RPPS_ESTADUAL    = 'RPPS_ESTADUAL',    'RPPS Estadual'
    RPPS_FEDERAL     = 'RPPS_FEDERAL',     'RPPS Federal (RJU/União)'


class CertidaoTempoContribuicao(models.Model):
    """
    Certidão de Tempo de Contribuição averbada ao processo.
    Pode ser oriunda do RGPS/INSS ou de outro regime próprio (municipal, estadual, federal).
    Períodos concomitantes com o RPPS que concede a aposentadoria são descontados.
    """
    processo      = models.ForeignKey(
        Processo, on_delete=models.CASCADE,
        related_name='certidoes_tempo', verbose_name='Processo'
    )
    numero_certidao = models.CharField(max_length=100, blank=True, verbose_name='Número da Certidão')
    orgao_emissor   = models.CharField(max_length=200, verbose_name='Órgão Emissor',
                                       help_text='Ex: INSS, IPSM-MG, RJU Federal, RPPS Município de Barra Mansa')
    tipo_origem     = models.CharField(max_length=20, choices=OrigemTempo.choices, verbose_name='Tipo de Origem')
    data_inicio_periodo = models.DateField(null=True, blank=True, verbose_name='Início do Período')
    data_fim_periodo    = models.DateField(null=True, blank=True, verbose_name='Fim do Período')
    data_emissao        = models.DateField(null=True, blank=True, verbose_name='Data de Emissão da Certidão')

    # Tempo certificado
    cert_anos  = models.PositiveIntegerField(default=0, verbose_name='Anos (certificado)')
    cert_meses = models.PositiveIntegerField(default=0, verbose_name='Meses (certificado)')
    cert_dias  = models.PositiveIntegerField(default=0, verbose_name='Dias (certificado)')

    # Período concomitante a descontar (sobreposição com o RPPS atual)
    possui_concomitancia    = models.BooleanField(default=False, verbose_name='Possui período concomitante?')
    conc_anos  = models.PositiveIntegerField(default=0, verbose_name='Anos concomitantes')
    conc_meses = models.PositiveIntegerField(default=0, verbose_name='Meses concomitantes')
    conc_dias  = models.PositiveIntegerField(default=0, verbose_name='Dias concomitantes')
    descricao_concomitancia = models.TextField(blank=True,
        verbose_name='Descrição da concomitância',
        help_text='Descreva o período e o vínculo simultâneo com o RPPS atual que originou a concomitância.')

    observacoes = models.TextField(blank=True, verbose_name='Observações')

    class Meta:
        verbose_name = 'Certidão de Tempo de Contribuição'
        verbose_name_plural = 'Certidões de Tempo de Contribuição'
        ordering = ['processo', 'data_inicio_periodo']

    def __str__(self):
        return f'CTC {self.orgao_emissor} — {self.tempo_certificado_display} ({self.processo})'

    # ── helpers ──────────────────────────────────────────────────────────
    @property
    def total_dias_certificado(self):
        return _dias(self.cert_anos, self.cert_meses, self.cert_dias)

    @property
    def total_dias_concomitantes(self):
        if not self.possui_concomitancia:
            return 0
        return _dias(self.conc_anos, self.conc_meses, self.conc_dias)

    @property
    def dias_averbar(self):
        """Dias efetivamente averbuláveis (certificado − concomitante)."""
        return max(0, self.total_dias_certificado - self.total_dias_concomitantes)

    @property
    def tempo_certificado_display(self):
        return _fmt_amd(self.cert_anos, self.cert_meses, self.cert_dias)

    @property
    def tempo_concomitante_display(self):
        return _fmt_amd(self.conc_anos, self.conc_meses, self.conc_dias)

    @property
    def tempo_averbavel_display(self):
        return _fmt_amd(*_dias_para_amd(self.dias_averbar))

    @property
    def is_servico_publico(self):
        """True quando a certidão é oriunda de vínculo público (conta como tempo de serviço público)."""
        return self.tipo_origem in (
            OrigemTempo.INSS_MUNICIPIO,
            OrigemTempo.RPPS_MUNICIPAL,
            OrigemTempo.RPPS_ESTADUAL,
            OrigemTempo.RPPS_FEDERAL,
        )


class TipoDocumento(models.TextChoices):
    CONTRACHEQUE_ATIVO   = 'CONTRACHEQUE_ATIVO',   'Contracheque Ativo'
    CONTRACHEQUE_INATIVO = 'CONTRACHEQUE_INATIVO', 'Contracheque Inativo'
    OUTRO                = 'OUTRO',                'Outro Documento'


class DocumentoProcesso(models.Model):
    """Arquivo PDF vinculado a um processo (contracheques e outros documentos)."""
    processo      = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name='documentos', verbose_name='Processo')
    tipo          = models.CharField(max_length=30, choices=TipoDocumento.choices, verbose_name='Tipo de Documento')
    arquivo       = models.FileField(upload_to='documentos/%Y/%m/', verbose_name='Arquivo')
    nome_original = models.CharField(max_length=255, blank=True, verbose_name='Nome Original')
    data_upload   = models.DateTimeField(default=timezone.now, verbose_name='Data de Upload')

    class Meta:
        verbose_name = 'Documento do Processo'
        verbose_name_plural = 'Documentos dos Processos'
        ordering = ['processo', 'tipo']

    def __str__(self):
        return f'{self.get_tipo_display()} — {self.processo}'


class ContrachequeAuditoria(models.Model):
    """
    Dados do contracheque coletados pelo auditor ao abrir o processo.
    - Regime MÉDIA: informar apenas a parcela vencimento/salário do mês.
    - Regime PARIDADE: informar a última remuneração do cargo efetivo paradigma
      e a lei municipal de reajuste dos servidores em atividade.
    """
    processo = models.OneToOneField(
        Processo, on_delete=models.CASCADE,
        related_name='contracheque', verbose_name='Processo'
    )
    mes_referencia = models.DateField(verbose_name='Mês de Referência do Contracheque')

    # ── MÉDIA ──────────────────────────────────────────────────────────────
    valor_vencimento = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor do Vencimento/Salário no Contracheque (R$)',
        help_text='Para regime MÉDIA: informar apenas a parcela vencimento básico do contracheque do mês.'
    )

    # ── PARIDADE ───────────────────────────────────────────────────────────
    ultima_remuneracao_cargo = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Última Remuneração do Cargo Efetivo Paradigma (R$)',
        help_text='Para regime PARIDADE: remuneração atual do servidor ativo no cargo equivalente.'
    )
    lei_reajuste_municipal = models.CharField(
        max_length=300, blank=True,
        verbose_name='Lei Municipal de Reajuste (servidores em atividade)',
        help_text='Ex: Lei nº 1.234/2025 — reajuste de 5% a partir de 01/03/2025.'
    )
    percentual_reajuste_lei = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        verbose_name='Percentual de Reajuste da Lei Municipal (%)'
    )
    data_vigencia_reajuste = models.DateField(
        null=True, blank=True,
        verbose_name='Data de Vigência do Reajuste Municipal'
    )

    # Demonstrativo completo importado do PDF (JSON)
    # Estrutura: {"rubricas": [{"conta","descricao","referencia","vencimento","desconto"},...],
    #             "total_vencimentos", "total_descontos", "total_liquido",
    #             "base_irrf", "periodo"}
    demonstrativo_json = models.TextField(
        blank=True, verbose_name='Demonstrativo de Pagamento (JSON)',
        help_text='Importado automaticamente do PDF do holerite.'
    )

    observacoes = models.TextField(blank=True, verbose_name='Observações')
    data_registro = models.DateTimeField(default=timezone.now, verbose_name='Data de Registro')

    class Meta:
        verbose_name = 'Contracheque do Processo'
        verbose_name_plural = 'Contracheques dos Processos'

    # Contas classificadas como desconto nos holerites do RPPS Mangaratiba
    _CONTAS_DESCONTO = {'1021', '1025', '1630', '1631', '1632', '1640', '1641'}

    def get_demonstrativo(self):
        """Retorna o demonstrativo como dict, ou None se não importado.

        Normaliza rubricas que vieram com a chave 'valor' (import antigo)
        classificando-as em vencimento/desconto e calcula totais.
        """
        import json
        from decimal import Decimal, InvalidOperation

        if not self.demonstrativo_json:
            return None
        try:
            demo = json.loads(self.demonstrativo_json)
        except (ValueError, TypeError):
            return None

        def _parse(v):
            if not v:
                return Decimal('0')
            try:
                return Decimal(str(v).replace('.', '').replace(',', '.'))
            except InvalidOperation:
                return Decimal('0')

        rubricas = demo.get('rubricas', [])
        for r in rubricas:
            if 'vencimento' not in r and 'desconto' not in r:
                conta = str(r.get('conta', ''))
                valor = r.get('valor', '')
                if conta in self._CONTAS_DESCONTO:
                    r['desconto'] = valor
                    r['vencimento'] = ''
                else:
                    r['vencimento'] = valor
                    r['desconto'] = ''

        if 'total_vencimentos' not in demo:
            total_v = sum(_parse(r.get('vencimento')) for r in rubricas)
            total_d = sum(_parse(r.get('desconto')) for r in rubricas)
            liquido = total_v - total_d
            def _fmt(v):
                return f"{v:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            demo['total_vencimentos'] = _fmt(total_v)
            demo['total_descontos'] = _fmt(total_d)
            demo['total_liquido'] = _fmt(liquido)

        demo['rubricas'] = rubricas
        return demo

    def __str__(self):
        return f'Contracheque — {self.processo} ({self.mes_referencia})'


class ContribuicaoPrevidenciaria(models.Model):
    """
    Histórico de salários de contribuição previdenciária por competência.
    Usado para apurar a média de contribuições nos processos em regime MÉDIA.
    Referência: Lei 10.887/2004 — média das 80% maiores contribuições desde jul/1994.
    """
    processo = models.ForeignKey(
        Processo, on_delete=models.CASCADE,
        related_name='contribuicoes', verbose_name='Processo'
    )
    competencia = models.DateField(verbose_name='Competência (mês/ano)')
    salario_contribuicao = models.DecimalField(
        max_digits=12, decimal_places=2,
        verbose_name='Salário de Contribuição (R$)',
        help_text='Valor bruto do salário de contribuição na competência.'
    )
    indice_correcao = models.DecimalField(
        max_digits=10, decimal_places=6, null=True, blank=True,
        verbose_name='Índice de Correção Monetária',
        help_text='Fator de correção para atualizar o valor à data de concessão (ex: INPC acumulado).'
    )
    valor_corrigido = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor Corrigido (R$)',
        help_text='Salário de contribuição atualizado monetariamente. Calculado automaticamente se informado o índice.'
    )
    observacoes = models.CharField(max_length=200, blank=True, verbose_name='Observações')

    class Meta:
        verbose_name = 'Contribuição Previdenciária'
        verbose_name_plural = 'Contribuições Previdenciárias'
        ordering = ['processo', 'competencia']
        unique_together = [('processo', 'competencia')]

    def __str__(self):
        from decimal import Decimal
        comp = self.competencia.strftime('%m/%Y') if self.competencia else '—'
        return f'{self.processo} — {comp} R$ {self.salario_contribuicao}'

    def save(self, *args, **kwargs):
        """Calcula valor_corrigido automaticamente se índice for informado."""
        if self.indice_correcao and self.salario_contribuicao:
            from decimal import Decimal
            self.valor_corrigido = (self.salario_contribuicao * self.indice_correcao).quantize(Decimal('0.01'))
        super().save(*args, **kwargs)

    @property
    def valor_efetivo(self):
        """Valor a usar no cálculo da média: corrigido se disponível, senão original."""
        return self.valor_corrigido if self.valor_corrigido else self.salario_contribuicao


class MetodoReajuste(models.TextChoices):
    PARIDADE_MUNICIPAL = 'PARIDADE_MUNICIPAL', 'Paridade — Lei Municipal'
    INDICE_INSS = 'INDICE_INSS', 'Índice INSS (benefícios sem paridade)'


class HistoricoReajusteBeneficio(models.Model):
    """Registra a reconstrução ano a ano da evolução do benefício."""
    processo = models.ForeignKey(
        Processo, on_delete=models.CASCADE,
        related_name='historico_reajuste', verbose_name='Processo'
    )
    ano_reajuste = models.IntegerField(verbose_name='Ano')
    norma_reajuste = models.CharField(max_length=300, blank=True, verbose_name='Norma / Lei de Reajuste')
    percentual_reajuste = models.DecimalField(
        max_digits=7, decimal_places=4, null=True, blank=True,
        verbose_name='Percentual de Reajuste (%)'
    )
    valor_reconstruido_ano = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        verbose_name='Valor Reconstruído no Ano (R$)'
    )
    metodo_reajuste = models.CharField(
        max_length=30, choices=MetodoReajuste.choices,
        default=MetodoReajuste.INDICE_INSS, verbose_name='Método de Reajuste'
    )
    descricao = models.TextField(blank=True, verbose_name='Descrição / Observação')

    class Meta:
        verbose_name = 'Histórico de Reajuste do Benefício'
        verbose_name_plural = 'Históricos de Reajuste dos Benefícios'
        ordering = ['processo', 'ano_reajuste']
        unique_together = [('processo', 'ano_reajuste')]

    def __str__(self):
        return f'{self.processo} — {self.ano_reajuste} ({self.percentual_reajuste}%)'
