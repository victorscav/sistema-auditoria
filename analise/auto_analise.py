"""
Motor de pré-análise automática.

Compara dados do processo/benefício com uma RegraAposentadoria e retorna
sugestões de Conforme/Não Conforme para cada campo dos 3 módulos de análise.
"""
import re
from decimal import Decimal


def _parse_anos(texto):
    """
    Extrai número de anos de strings como:
      "35 anos", "35a 6m", "35a", "420 meses", "35 anos e 6 meses"
    Retorna float de anos, ou None se não conseguir.
    """
    if not texto:
        return None
    texto = str(texto).strip().lower()

    # "420 meses"
    m = re.search(r'(\d+)\s*m[eê]s', texto)
    if m and 'ano' not in texto:
        return int(m.group(1)) / 12

    # "35a 6m" ou "35 anos 6 meses" etc.
    anos = 0
    m_anos = re.search(r'(\d+)\s*a(?:nos?)?', texto)
    if m_anos:
        anos = int(m_anos.group(1))
    m_meses = re.search(r'(\d+)\s*m(?:eses?)?', texto)
    if m_meses:
        anos += int(m_meses.group(1)) / 12
    if anos:
        return anos

    # número solto — assume anos
    m_num = re.search(r'(\d+)', texto)
    if m_num:
        return float(m_num.group(1))

    return None


def _ok_ou_none(cond):
    """Converte bool ou None para tuple (value, str)."""
    if cond is None:
        return None, 'Informação insuficiente para verificar.'
    return cond, ''


def _resultado_sugerido(checks):
    """Dado uma lista de bool|None, retorna resultado sugerido."""
    valores = [v for v in checks if v is not None]
    if not valores:
        return 'INDETERMINADO'
    if all(v for v in valores):
        return 'CONFORME'
    if any(v is False for v in valores):
        return 'NAO_CONFORME'
    return 'RESSALVAS'


def executar_pre_analise(processo, regra):
    """
    Retorna dict com sugestões de pré-preenchimento para os 3 módulos.
    Cada item é (bool|None, str_obs).
    """
    dados = getattr(processo, 'dados_beneficio', None)

    # ── ELEGIBILIDADE ────────────────────────────────────────────────────────

    # Tipos tratados como equivalentes para fins de enquadramento
    _EQUIV = {
        'APOS_VOLUNTARIA_IDADE_TC': {'APOS_VOLUNTARIA', 'APOS_VOLUNTARIA_PROP', 'APOS_VOLUNTARIA_IDADE_TC'},
        'APOS_VOLUNTARIA':          {'APOS_VOLUNTARIA', 'APOS_VOLUNTARIA_IDADE_TC'},
        'APOS_VOLUNTARIA_PROP':     {'APOS_VOLUNTARIA_PROP', 'APOS_VOLUNTARIA_IDADE_TC'},
        'APOS_VOLUNTARIA_POR_IDADE':{'APOS_VOLUNTARIA_POR_IDADE', 'APOS_VOLUNTARIA_PROP_IDADE', 'APOS_VOLUNTARIA_PROP'},
        'APOS_VOLUNTARIA_PROP_IDADE':{'APOS_VOLUNTARIA_PROP_IDADE','APOS_VOLUNTARIA_POR_IDADE', 'APOS_VOLUNTARIA_PROP'},
        'APOS_INCAPACIDADE':        {'APOS_INCAPACIDADE', 'APOS_INVALIDEZ_PERMANENTE'},
        'APOS_INVALIDEZ_PERMANENTE':{'APOS_INVALIDEZ_PERMANENTE', 'APOS_INCAPACIDADE'},
    }
    tipos_equiv = _EQUIV.get(processo.tipo_beneficio, {processo.tipo_beneficio})

    # enquadramento_correto
    if regra.tipo_beneficio in tipos_equiv:
        enq_val = True
        enq_obs = (f'Tipo de benefício do processo ({processo.get_tipo_beneficio_display()}) '
                   f'corresponde ao tipo da regra.')
    else:
        enq_val = False
        enq_obs = (f'Tipo de benefício do processo ({processo.get_tipo_beneficio_display()}) '
                   f'não corresponde ao tipo da regra ({regra.get_tipo_beneficio_display()}).')

    # normas_vigentes_epoca
    if processo.data_concessao and regra.vigente_desde:
        inicio_ok = processo.data_concessao >= regra.vigente_desde
        fim_ok = (regra.vigente_ate is None) or (processo.data_concessao <= regra.vigente_ate)
        norm_val = inicio_ok and fim_ok
        if norm_val:
            norm_obs = (f'Data de concessão {processo.data_concessao} está dentro do período de '
                        f'vigência da norma ({regra.vigente_desde} a '
                        f'{regra.vigente_ate or "atual"}).')
        else:
            norm_obs = (f'Data de concessão {processo.data_concessao} está FORA do período de '
                        f'vigência da norma ({regra.vigente_desde} a '
                        f'{regra.vigente_ate or "atual"}).')
    else:
        norm_val = None
        norm_obs = 'Data de concessão ou vigência da norma não informadas.'

    # requisitos_idade
    if dados and dados.idade_concessao is not None:
        # tenta determinar sexo pelo nome (heurística simples) ou usa menor dos dois
        sexo = _inferir_sexo(processo.beneficiario.nome if processo.beneficiario else '')
        if sexo == 'M' and regra.idade_minima_homem is not None:
            idade_min = regra.idade_minima_homem
            label_sexo = 'homem'
        elif sexo == 'F' and regra.idade_minima_mulher is not None:
            idade_min = regra.idade_minima_mulher
            label_sexo = 'mulher'
        elif regra.idade_minima_mulher is not None:
            # usa o menor (mais favorável) quando sexo indeterminado
            idade_min = min(
                v for v in [regra.idade_minima_homem, regra.idade_minima_mulher] if v is not None
            )
            label_sexo = 'mínimo aplicável'
        else:
            idade_min = None
            label_sexo = ''

        if idade_min is not None:
            req_idade_val = dados.idade_concessao >= idade_min
            req_idade_obs = (f'Idade na concessão: {dados.idade_concessao} anos. '
                             f'Mínimo exigido ({label_sexo}): {idade_min} anos. '
                             f'{"CONFORME" if req_idade_val else "NÃO CONFORME"}.')
        else:
            req_idade_val = None
            req_idade_obs = 'Regra não define idade mínima para este tipo de benefício.'
    else:
        req_idade_val = None
        req_idade_obs = 'Idade na concessão não informada no processo.'

    # tempo_contribuicao — inclui tempo averbado via certidões (descontadas concomitâncias)
    from processos.models import _dias_para_amd, _fmt_amd

    # Tempo próprio declarado no processo
    anos_proprio = _parse_anos(dados.tempo_contribuicao) if dados and dados.tempo_contribuicao else None

    # Tempo averbado pelas certidões (já líquido de concomitâncias)
    averbado_dias = processo.tempo_averbado_total_dias()
    averbado_anos = averbado_dias / 365.0 if averbado_dias else 0.0
    averbado_display = processo.tempo_averbado_display() if averbado_dias else None

    sexo = _inferir_sexo(processo.beneficiario.nome if processo.beneficiario else '')
    if sexo == 'M' and regra.tempo_contribuicao_homem is not None:
        tc_min = regra.tempo_contribuicao_homem
        tc_label = 'homem'
    elif sexo == 'F' and regra.tempo_contribuicao_mulher is not None:
        tc_min = regra.tempo_contribuicao_mulher
        tc_label = 'mulher'
    elif any(v is not None for v in [regra.tempo_contribuicao_homem, regra.tempo_contribuicao_mulher]):
        tc_min = min(
            v for v in [regra.tempo_contribuicao_homem, regra.tempo_contribuicao_mulher]
            if v is not None
        )
        tc_label = 'mínimo aplicável'
    else:
        tc_min = None
        tc_label = ''

    if tc_min is not None and anos_proprio is not None:
        total_anos = anos_proprio + averbado_anos
        # Total em dias → display
        total_dias = int(total_anos * 365)
        total_display = _fmt_amd(*_dias_para_amd(total_dias))
        tc_val = total_anos >= tc_min
        linhas = [
            f'Tempo próprio (declarado): {dados.tempo_contribuicao} ({anos_proprio:.1f} anos).',
        ]
        if averbado_dias:
            certidoes_qs = processo.certidoes_tempo.all()
            for ctc in certidoes_qs:
                linhas.append(
                    f'  + Averbado [{ctc.orgao_emissor}]: certificado {ctc.tempo_certificado_display}'
                    + (f', concomitante descontado: {ctc.tempo_concomitante_display}' if ctc.possui_concomitancia else '')
                    + f' → averbável: {ctc.tempo_averbavel_display}.'
                )
            linhas.append(f'Total averbado: {averbado_display} ({averbado_anos:.1f} anos).')
        linhas.append(f'TOTAL EFETIVO: {total_display} ({total_anos:.1f} anos).')
        linhas.append(f'Mínimo exigido ({tc_label}): {tc_min} anos.')
        linhas.append('CONFORME.' if tc_val else 'NÃO CONFORME — tempo insuficiente.')
        tc_obs = ' '.join(linhas)
    elif tc_min is not None and anos_proprio is None and averbado_dias:
        # só tem averbado, sem tempo próprio declarado
        tc_val = averbado_anos >= tc_min
        tc_obs = (f'Tempo próprio não declarado no processo. '
                  f'Tempo averbado (certidões): {averbado_display} ({averbado_anos:.1f} anos). '
                  f'Mínimo exigido ({tc_label}): {tc_min} anos. '
                  f'{"CONFORME" if tc_val else "NÃO CONFORME"}.')
    elif tc_min is None:
        # Para aposentadoria proporcional por idade, TC não é requisito mínimo
        # mas é obrigatório para calcular a proporcionalidade
        if processo.tipo_beneficio == 'APOS_VOLUNTARIA_PROP':
            total_anos = (anos_proprio or 0) + averbado_anos
            total_dias = int(total_anos * 365)
            if total_anos > 0:
                sexo = _inferir_sexo(processo.beneficiario.nome if processo.beneficiario else '')
                dias_int = 10950 if sexo == 'F' else 12775
                perc = min(100.0, total_anos * 365 / dias_int * 100)
                total_display = _fmt_amd(*_dias_para_amd(total_dias))
                tc_val = True  # Não há mínimo — conforme por definição
                linhas = [f'Aposentadoria por Idade — sem TC mínimo exigido (Art. 78 LC 33/2014).']
                if anos_proprio:
                    linhas.append(f'Tempo próprio: {dados.tempo_contribuicao} ({anos_proprio:.1f} anos).')
                if averbado_dias:
                    linhas.append(f'Tempo averbado: {averbado_display} ({averbado_anos:.1f} anos).')
                linhas.append(f'TOTAL: {total_display} ({total_anos:.1f} anos).')
                linhas.append(f'Proporcionalidade calculada: {perc:.4f}% ({total_dias}/{dias_int} dias).')
                linhas.append('TC será usado para cálculo dos proventos proporcionais.')
                tc_obs = ' '.join(linhas)
            else:
                tc_val = None
                tc_obs = ('Aposentadoria por Idade — TC não é requisito mínimo (Art. 78). '
                          'Informe o tempo de contribuição para que o sistema calcule a proporcionalidade.')
        else:
            tc_val = None
            tc_obs = 'Regra não define tempo mínimo de contribuição para este tipo de benefício.'
    else:
        tc_val = None
        tc_obs = 'Tempo de contribuição não informado no processo e sem certidões averbadas.'

    # tempo_servico_publico
    # Inclui certidões de origem pública (INSS Município, RPPS estadual/municipal/federal)
    from processos.models import OrigemTempo as _OT
    certidoes_sp = [
        c for c in processo.certidoes_tempo.all()
        if c.is_servico_publico
    ]
    averbado_sp_dias = sum(c.dias_averbar for c in certidoes_sp)
    averbado_sp_anos = averbado_sp_dias / 365.0 if averbado_sp_dias else 0.0

    if regra.tempo_servico_publico is not None:
        anos_sp_proprio = _parse_anos(dados.tempo_servico_publico) if dados and dados.tempo_servico_publico else None
        total_sp_anos = (anos_sp_proprio or 0.0) + averbado_sp_anos
        if total_sp_anos > 0:
            sp_val = total_sp_anos >= regra.tempo_servico_publico
            linhas_sp = []
            if anos_sp_proprio:
                linhas_sp.append(f'Tempo próprio de serviço público: {dados.tempo_servico_publico} ({anos_sp_proprio:.1f} anos).')
            if certidoes_sp:
                for ctc in certidoes_sp:
                    linhas_sp.append(
                        f'  + Averbado [{ctc.orgao_emissor} / {ctc.get_tipo_origem_display()}]: '
                        f'{ctc.tempo_averbavel_display} (serviço público).'
                    )
                linhas_sp.append(f'Total averbado (serviço público): {_fmt_amd(*_dias_para_amd(averbado_sp_dias))} ({averbado_sp_anos:.1f} anos).')
            linhas_sp.append(f'TOTAL SERVIÇO PÚBLICO: {total_sp_anos:.1f} anos. Mínimo exigido: {regra.tempo_servico_publico} anos.')
            linhas_sp.append('CONFORME.' if sp_val else 'NÃO CONFORME — tempo insuficiente.')
            sp_obs = ' '.join(linhas_sp)
        else:
            sp_val = None
            sp_obs = 'Tempo de serviço público não informado no processo e sem certidões de origem pública.'
    else:
        sp_val = None
        sp_obs = 'Tempo de serviço público não exigido pela regra.'

    # tempo_carreira
    if dados and dados.tempo_carreira:
        anos_carreira = _parse_anos(dados.tempo_carreira)
        if anos_carreira is not None:
            if regra.tempo_carreira is not None:
                carr_val = anos_carreira >= regra.tempo_carreira
                carr_obs = (f'Tempo de carreira: {dados.tempo_carreira} ({anos_carreira:.1f} anos). '
                            f'Mínimo exigido: {regra.tempo_carreira} anos. '
                            f'{"CONFORME" if carr_val else "NÃO CONFORME"}.')
            else:
                carr_val = True
                carr_obs = f'Tempo de carreira informado: {dados.tempo_carreira} ({anos_carreira:.1f} anos). Sem mínimo definido na regra.'
        else:
            carr_val = None
            carr_obs = 'Não foi possível interpretar o tempo de carreira informado.'
    else:
        carr_val = None
        carr_obs = 'Tempo de carreira não informado. Verifique se exigido pela lei municipal.'

    # tempo_no_cargo
    if dados and dados.tempo_no_cargo and regra.tempo_no_cargo is not None:
        anos_cargo = _parse_anos(dados.tempo_no_cargo)
        if anos_cargo is not None:
            cargo_val = anos_cargo >= regra.tempo_no_cargo
            cargo_obs = (f'Tempo no cargo: {dados.tempo_no_cargo} ({anos_cargo:.1f} anos). '
                         f'Mínimo exigido: {regra.tempo_no_cargo} anos. '
                         f'{"CONFORME" if cargo_val else "NÃO CONFORME"}.')
        else:
            cargo_val = None
            cargo_obs = 'Não foi possível interpretar o tempo no cargo.'
    elif dados and dados.tempo_no_cargo:
        # Tempo informado mas sem mínimo definido na regra — verifica e confirma o dado
        anos_cargo_sem_min = _parse_anos(dados.tempo_no_cargo)
        if anos_cargo_sem_min is not None and anos_cargo_sem_min > 0:
            cargo_val = True
            cargo_obs = (
                f'Tempo no cargo verificado: {dados.tempo_no_cargo} ({anos_cargo_sem_min:.1f} anos). '
                f'Regra não define tempo mínimo para este tipo de benefício. CONFORME.'
            )
        else:
            cargo_val = None
            cargo_obs = f'Tempo no cargo informado: {dados.tempo_no_cargo}. Não foi possível interpretar o valor.'
    else:
        cargo_val = None
        cargo_obs = 'Tempo no cargo não informado ou não exigido pela regra.'

    # marco_temporal_ingresso
    if dados and dados.marco_temporal_ingresso:
        from datetime import date
        ec41  = date(2003, 12, 31)
        ec103 = date(2019, 11, 13)
        marco = dados.marco_temporal_ingresso

        # Marco temporal é sempre Conforme quando o ingresso é anterior à concessão
        # — a diferença está em qual conjunto de regras se aplica.
        marc_val = True
        if marco <= ec41:
            marc_obs = (
                f'Ingresso em {marco.strftime("%d/%m/%Y")} — anterior à EC 41/2003 (31/12/2003). '
                f'Elegível às regras de transição da EC 41/2003. CONFORME.'
            )
        elif marco <= ec103:
            marc_obs = (
                f'Ingresso em {marco.strftime("%d/%m/%Y")} — posterior à EC 41/2003 e anterior à '
                f'EC 103/2019 (13/11/2019). '
                f'Elegível às regras de transição da EC 103/2019. CONFORME.'
            )
        else:
            marc_obs = (
                f'Ingresso em {marco.strftime("%d/%m/%Y")} — posterior à EC 103/2019 (13/11/2019). '
                f'Sujeito exclusivamente às regras permanentes da EC 103/2019. CONFORME.'
            )
    else:
        marc_val = None
        marc_obs = 'Marco temporal de ingresso não informado. Verificar manualmente.'

    # carreira_cargo — verifica se cargo/carreira estão documentados no processo
    cargo_nome = processo.beneficiario.cargo if processo.beneficiario else ''
    cargo_paradigma = dados.cargo_paradigma if dados else ''
    if cargo_nome or cargo_paradigma:
        carr_cargo_val = True
        partes = []
        if cargo_nome:
            partes.append(f'Cargo informado: {cargo_nome}.')
        if cargo_paradigma:
            partes.append(f'Cargo paradigma: {cargo_paradigma}.')
        partes.append(
            'Confirme na legislação municipal que o cargo é efetivo e pertence à '
            'carreira declarada. CONFORME (documentado).'
        )
        carr_cargo_obs = ' '.join(partes)
    else:
        carr_cargo_val = None
        carr_cargo_obs = (
            'Cargo/carreira não informados no processo. '
            'Preencha o campo "Cargo/Função" na edição do processo para permitir verificação.'
        )

    # base_calculo_pensao — verifica base de cálculo e redutor constitucional (EC 41/2003)
    base_calc_val = None
    base_calc_obs = ''
    if processo.tipo_beneficio == 'PENSAO_MORTE':
        # Teto RGPS: usa o mais recente cadastrado
        from processos.models import ReajusteINSS as _RINSS2
        teto_rgps_obj = _RINSS2.objects.order_by('-ano').first()
        teto_rgps = teto_rgps_obj.teto_inss if teto_rgps_obj else None

        base_proventos = dados.base_calculo if dados else None   # última remuneração/provento do instituidor
        valor_pensao = dados.valor_concedido if dados else None

        if base_proventos and valor_pensao and teto_rgps:
            base_dec = Decimal(str(base_proventos))
            pensao_dec = Decimal(str(valor_pensao))
            teto_dec = Decimal(str(teto_rgps))

            if base_dec <= teto_dec:
                # Sem redutor: pensão = base integral
                esperado = base_dec
                base_calc_val = abs(pensao_dec - esperado) <= Decimal('1.00')
                base_calc_obs = (
                    f'Base de cálculo (proventos/remuneração do instituidor): R$ {base_proventos}. '
                    f'Teto RGPS vigente: R$ {teto_rgps}. '
                    f'Base não supera o teto — sem aplicação do redutor constitucional. '
                    f'Valor esperado: R$ {esperado}. '
                    f'Valor concedido: R$ {valor_pensao}. '
                    + ('CONFORME.' if base_calc_val else f'NÃO CONFORME — divergência de R$ {abs(pensao_dec - esperado):.2f}.')
                )
            else:
                # Redutor: pensão = teto_RGPS + 70% × (base - teto_RGPS)
                excesso = base_dec - teto_dec
                parcela_reducao = (excesso * Decimal('0.70')).quantize(Decimal('0.01'))
                esperado = (teto_dec + parcela_reducao).quantize(Decimal('0.01'))
                base_calc_val = abs(pensao_dec - esperado) <= Decimal('1.00')
                base_calc_obs = (
                    f'Base de cálculo (proventos/remuneração do instituidor): R$ {base_proventos}. '
                    f'Teto RGPS vigente: R$ {teto_rgps}. '
                    f'Aplica redutor constitucional (EC 41/2003): '
                    f'R$ {teto_dec} + 70% × (R$ {base_dec} − R$ {teto_dec}) = '
                    f'R$ {teto_dec} + R$ {parcela_reducao} = R$ {esperado}. '
                    f'Valor concedido: R$ {valor_pensao}. '
                    + ('CONFORME.' if base_calc_val else f'NÃO CONFORME — divergência de R$ {abs(pensao_dec - esperado):.2f}.')
                )
        elif not base_proventos:
            base_calc_obs = (
                'Base de cálculo do instituidor não informada. '
                'Preencha o campo "Base de Cálculo" nos dados do processo para verificação automática do redutor.'
            )
        elif not teto_rgps:
            base_calc_obs = 'Teto RGPS não cadastrado. Informe na tabela de Reajustes INSS.'
        else:
            base_calc_obs = 'Valor concedido não informado — verificação do redutor não pôde ser concluída.'

    # condicao_dependente (apenas para pensão)
    if processo.tipo_beneficio == 'PENSAO_MORTE':
        dep_val = None
        dep_obs = 'Verificar documentação de dependente manualmente (certidão/declaração).'
    else:
        dep_val = True
        dep_obs = 'Não aplicável para este tipo de benefício.'

    eleg_checks = [enq_val, norm_val, req_idade_val, tc_val, sp_val, carr_cargo_val, cargo_val]
    eleg_resultado = _resultado_sugerido(eleg_checks)

    # ── CÁLCULO ──────────────────────────────────────────────────────────────

    # teto_acumulacao — teto é o subsídio do prefeito; exceção: procuradores municipais
    cargo = (processo.beneficiario.cargo if processo.beneficiario else '') or ''
    is_procurador = 'procurador' in cargo.lower()

    from institutos.models import Instituto as _Inst
    subsidio_prefeito = None
    if processo.instituto_id:
        subsidio_prefeito = _Inst.objects.filter(pk=processo.instituto_id).values_list('subsidio_prefeito', flat=True).first()
    if subsidio_prefeito is None:
        # Processo sem instituto vinculado: usa o único ativo disponível
        subsidio_prefeito = _Inst.objects.filter(ativo=True).order_by('pk').values_list('subsidio_prefeito', flat=True).first()

    valor_verificar_teto = dados.valor_concedido if dados else None

    if is_procurador:
        teto_val = None
        teto_obs = (
            f'Cargo: {cargo}. '
            'Procurador municipal possui teto remuneratório diferenciado (art. 37, XI CF/88 c/c art. 135 CF/88). '
            'Verificar o subsídio dos membros do TCE ou AGU aplicável ao município. '
            'Verificação manual necessária.'
        )
    elif subsidio_prefeito and valor_verificar_teto is not None:
        val_dec = Decimal(str(valor_verificar_teto))
        teto_val = val_dec <= subsidio_prefeito
        teto_obs = (
            f'Teto remuneratório = subsídio do Prefeito: R$ {subsidio_prefeito}. '
            f'Valor do benefício: R$ {valor_verificar_teto}. '
            + ('CONFORME.' if teto_val else f'NÃO CONFORME — valor supera o teto em R$ {val_dec - subsidio_prefeito:.2f}.')
        )
    elif subsidio_prefeito:
        teto_val = None
        teto_obs = (
            f'Subsídio do Prefeito cadastrado: R$ {subsidio_prefeito}. '
            'Valor do benefício não informado — verificação não pôde ser concluída.'
        )
    else:
        teto_val = None
        teto_obs = (
            'Subsídio do Prefeito não cadastrado no Instituto. '
            'Informe o valor no cadastro do Instituto RPPS para habilitar a verificação automática.'
        )

    # ── helper: salário mínimo vigente na data de concessão ─────────────────
    def _salario_minimo_vigente(data_concessao):
        """Retorna o salário mínimo (Decimal) vigente no ano da concessão, ou None."""
        if not data_concessao:
            return None
        from processos.models import ReajusteINSS as _RINSS
        try:
            r = _RINSS.objects.get(ano=data_concessao.year)
            return r.salario_minimo
        except _RINSS.DoesNotExist:
            # Tenta o ano anterior como fallback
            try:
                r = _RINSS.objects.filter(ano__lte=data_concessao.year).order_by('-ano').first()
                return r.salario_minimo if r else None
            except Exception:
                return None

    # ── helper: calcula proporcionalidade esperada a partir do tempo de contribuição ──
    def _proporcional_esperado(processo, regra, dados):
        """
        Calcula o percentual de proporcionalidade esperado conforme Art. 113 LC 33/2014.
        Fração = total_dias_contribuição / dias_para_integral
        Para mulher: 30*365 = 10.950 dias | Para homem: 35*365 = 12.775 dias
        Retorna (percentual_decimal, dias_servico, dias_integrais) ou None.
        """
        if not dados or not dados.tempo_contribuicao:
            return None
        # Calcula total de dias de contribuição (próprio + averbado)
        from processos.models import _dias_para_amd as _d2amd
        averbado = processo.tempo_averbado_total_dias()
        anos_proprio = _parse_anos(dados.tempo_contribuicao)
        if anos_proprio is None:
            return None
        dias_proprio = int(anos_proprio * 365)
        total_dias = dias_proprio + (averbado or 0)

        # Dias para benefício integral conforme sexo
        sexo = _inferir_sexo(processo.beneficiario.nome if processo.beneficiario else '')
        if sexo == 'F':
            dias_integrais = 30 * 365  # 10.950
        else:
            dias_integrais = 35 * 365  # 12.775

        perc = min(Decimal('100'), (Decimal(total_dias) / Decimal(dias_integrais) * 100).quantize(Decimal('0.0001')))
        return perc, total_dias, dias_integrais

    # media_integralidade — para regime MÉDIA, confronta média importada com valor concedido
    from processos.models import RegimeReajuste as _RR
    if dados and dados.regime_reajuste == _RR.MEDIA:
        media = dados.media_contribuicoes
        sal_min = _salario_minimo_vigente(processo.data_concessao)
        if media is not None and dados.valor_concedido is not None:
            valor = Decimal(str(dados.valor_concedido))
            media_dec = Decimal(str(media))
            tol = Decimal('0.10')

            # Calcula valor esperado conforme proporcionalidade
            prop_result = _proporcional_esperado(processo, regra, dados)
            perc_importado = dados.proporcionalidade_percentual

            if prop_result and not regra.integralidade:
                perc_calc, dias_serv, dias_int = prop_result
                # Usa percentual importado se disponível, senão o calculado
                perc_usar = Decimal(str(perc_importado)) if perc_importado else perc_calc
                valor_esperado = (media_dec * perc_usar / 100).quantize(Decimal('0.01'))

                complemento_salmin = sal_min is not None and valor_esperado < sal_min and abs(valor - sal_min) <= tol

                if complemento_salmin:
                    integ_val = True
                    integ_obs = (
                        f'Regime MÉDIA — Proventos Proporcionais. '
                        f'Média das contribuições: R$ {media}. '
                        f'Proporcionalidade: {perc_usar:.4f}% ({dias_serv}/{dias_int} dias). '
                        f'Valor proporcional calculado: R$ {valor_esperado}. '
                        f'Salário mínimo vigente: R$ {sal_min}. '
                        f'Benefício corretamente concedido no salário mínimo (Art. 201 §2º CF/88). CONFORME.')
                else:
                    integ_val = abs(valor - valor_esperado) <= tol
                    integ_obs = (
                        f'Regime MÉDIA — Proventos Proporcionais. '
                        f'Média das contribuições: R$ {media}. '
                        f'Proporcionalidade: {perc_usar:.4f}% ({dias_serv}/{dias_int} dias). '
                        f'Valor esperado (média × proporcionalidade): R$ {valor_esperado}. '
                        + (f'Salário mínimo vigente: R$ {sal_min}. ' if sal_min else '')
                        + f'Valor concedido: R$ {valor}. '
                        + ('CONFORME.' if integ_val else f'NÃO CONFORME — divergência de R$ {abs(valor - valor_esperado):.2f}.'))
            else:
                # Integral ou sem dados de proporcionalidade
                complemento_salmin = sal_min is not None and media_dec < sal_min and abs(valor - sal_min) <= tol
                if complemento_salmin:
                    integ_val = True
                    integ_obs = (
                        f'Regime MÉDIA. Média das contribuições: R$ {media}. '
                        f'Salário mínimo vigente: R$ {sal_min}. '
                        f'Como a média é inferior ao salário mínimo, o benefício foi concedido '
                        f'no valor do salário mínimo (R$ {valor}) conforme art. 201 §2º CF/88. CONFORME.')
                else:
                    integ_val = abs(valor - media_dec) <= tol
                    integ_obs = (
                        f'Regime MÉDIA. Média das contribuições previdenciárias apurada: R$ {media}. '
                        + (f'Salário mínimo vigente: R$ {sal_min}. ' if sal_min else '')
                        + f'Valor concedido: R$ {valor}. '
                        + ('CONFORME.' if integ_val else f'NÃO CONFORME — divergência de R$ {abs(valor - media_dec):.2f}.'))
        elif media is None:
            integ_val = None
            integ_obs = ('Regime MÉDIA: média das contribuições não informada no processo. '
                         'Preencha o campo "Média das Contribuições (R$)" na planilha ou nos dados do processo.')
        else:
            integ_val = None
            integ_obs = 'Valor concedido não informado no processo.'
    elif dados and dados.integralidade is not None and regra.integralidade is not None:
        integ_val = dados.integralidade == regra.integralidade
        integ_obs = (f'Integralidade no processo: {"Sim" if dados.integralidade else "Não"}. '
                     f'Regra prevê integralidade: {"Sim" if regra.integralidade else "Não"}. '
                     f'{"CONFORME" if integ_val else "NÃO CONFORME"}.')
    else:
        integ_val = None
        integ_obs = 'Integralidade não informada no processo ou na regra.'

    # reajuste — regime MÉDIA: aplica índices INSS acumulados e compara com contracheque
    from processos.models import ReajusteINSS as _RINSS
    import datetime as _dt
    if dados and dados.regime_reajuste == _RR.MEDIA and dados.valor_concedido and processo.data_concessao:
        contracheque = getattr(processo, 'contracheque', None)
        valor_atual = None
        mes_ref = None
        fonte_atual = ''
        if contracheque and contracheque.valor_vencimento:
            valor_atual = Decimal(str(contracheque.valor_vencimento))
            mes_ref = contracheque.mes_referencia
            fonte_atual = f'contracheque {mes_ref.strftime("%m/%Y")}'
        elif dados.valor_pago_folha:
            valor_atual = Decimal(str(dados.valor_pago_folha))
            fonte_atual = 'folha de pagamento'

        valor_base = Decimal(str(dados.valor_concedido))
        ano_base = processo.data_concessao.year
        ano_final = mes_ref.year if mes_ref else _dt.date.today().year

        reajustes_qs = _RINSS.objects.filter(ano__gt=ano_base, ano__lte=ano_final).order_by('ano')

        sm_ref_obj = _RINSS.objects.filter(ano__lte=ano_base).order_by('-ano').first()
        sm_anterior = sm_ref_obj.salario_minimo if sm_ref_obj else Decimal('0')

        valor_esperado = valor_base
        aplicados = []
        for r in reajustes_qs:
            is_piso = valor_esperado <= sm_anterior
            pct = r.percentual_piso if is_piso else r.percentual_acima_minimo
            valor_esperado = valor_esperado * (1 + pct / Decimal('100'))
            if valor_esperado < r.salario_minimo:
                valor_esperado = r.salario_minimo
            sm_anterior = r.salario_minimo
            aplicados.append(f'{r.ano}: {float(pct):.2f}% ({r.base_legal})')

        valor_esperado = valor_esperado.quantize(Decimal('0.01'))

        if valor_atual is not None:
            diff = abs(valor_atual - valor_esperado)
            reaj_val = diff <= Decimal('1.00')
            if aplicados:
                reaj_obs = (
                    f'Regime MÉDIA — reajuste INSS acumulado. '
                    f'Valor na concessão ({ano_base}): R$ {valor_base}. '
                    f'Índices aplicados: {" | ".join(aplicados)}. '
                    f'Valor esperado: R$ {valor_esperado}. '
                    f'Valor atual ({fonte_atual}): R$ {valor_atual}. '
                    + ('CONFORME.' if reaj_val else f'NÃO CONFORME — divergência de R$ {diff:.2f}.')
                )
            else:
                diff_base = abs(valor_atual - valor_base)
                reaj_val = diff_base <= Decimal('1.00')
                reaj_obs = (
                    f'Regime MÉDIA — sem reajustes INSS cadastrados entre {ano_base} e {ano_final}. '
                    f'Valor na concessão: R$ {valor_base}. '
                    f'Valor atual ({fonte_atual}): R$ {valor_atual}. '
                    + ('CONFORME — sem reajuste a aplicar no período.' if reaj_val
                       else f'NÃO CONFORME — divergência de R$ {diff_base:.2f} sem reajuste previsto.')
                )
        else:
            reaj_val = None
            reaj_obs = (
                'Regime MÉDIA: valor atual não disponível para verificação automática. '
                'Importe o contracheque do beneficiário na tela do processo ou informe o valor pago na folha.'
            )
    elif dados and dados.criterio_reajuste and regra.criterio_reajuste:
        reaj_val = regra.criterio_reajuste.upper() in dados.criterio_reajuste.upper()
        reaj_obs = (f'Critério de reajuste informado: "{dados.criterio_reajuste}". '
                    f'Critério previsto pela regra: "{regra.criterio_reajuste}". '
                    f'{"CONFORME" if reaj_val else "NÃO CONFORME"}.')
    else:
        reaj_val = None
        reaj_obs = 'Critério de reajuste não informado no processo ou na regra.'

    # trava de regime_reajuste x método aplicado
    from processos.models import RegimeReajuste
    regime_val = None
    regime_obs = ''
    if dados and dados.regime_reajuste != RegimeReajuste.NAO_DEFINIDO:
        regime = dados.regime_reajuste
        if regime == RegimeReajuste.PARIDADE:
            regime_val = True
            regime_obs = (
                'Benefício com PARIDADE: reajuste deve seguir as leis municipais '
                'de reestruturação/revisão do cargo paradigma. '
                'Uso da tabela INSS seria incompatível.'
            )
        elif regime == RegimeReajuste.MEDIA:
            regime_val = True
            regime_obs = (
                'Benefício por MÉDIA: reajuste deve seguir os índices INSS aplicáveis '
                'aos benefícios sem paridade. '
                'Vinculação ao cargo paradigma seria incompatível.'
            )
    else:
        regime_obs = 'Regime de reajuste não definido no processo. Informe PARIDADE ou MÉDIA.'

    calc_checks = [teto_val, integ_val, reaj_val, base_calc_val]
    calc_resultado = _resultado_sugerido(calc_checks)

    # ── FOLHA ────────────────────────────────────────────────────────────────

    folha_resultado = 'INDETERMINADO'
    divergencia_tipo = 'SEM_DIVERGENCIA'
    divergencia_valor = Decimal('0.00')

    if dados and dados.valor_pago_folha is not None and dados.valor_concedido is not None:
        pago = Decimal(str(dados.valor_pago_folha))
        concedido = Decimal(str(dados.valor_concedido))
        diff = pago - concedido
        divergencia_valor = abs(diff)

        # Verifica se a diferença é explicada pelo complemento de salário mínimo
        # (benefício < salário mínimo → concedido no salário mínimo conforme art. 201 §2º CF/88)
        sal_min_folha = _salario_minimo_vigente(processo.data_concessao)
        media_folha = dados.media_contribuicoes
        complemento_folha = (
            sal_min_folha is not None
            and media_folha is not None
            and Decimal(str(media_folha)) < sal_min_folha
            and abs(concedido - sal_min_folha) <= Decimal('0.10')
            and abs(pago - sal_min_folha) <= Decimal('0.10')
        )

        if complemento_folha:
            divergencia_tipo = 'SEM_DIVERGENCIA'
            folha_resultado = 'CONFORME'
            divergencia_valor = Decimal('0.00')
        elif diff > Decimal('0.01'):
            divergencia_tipo = 'PAGAMENTO_MAIOR'
            folha_resultado = 'NAO_CONFORME'
        elif diff < Decimal('-0.01'):
            divergencia_tipo = 'PAGAMENTO_MENOR'
            folha_resultado = 'NAO_CONFORME'
        else:
            divergencia_tipo = 'SEM_DIVERGENCIA'
            folha_resultado = 'CONFORME'

    return {
        'elegibilidade': {
            'enquadramento_correto': (enq_val, enq_obs),
            'requisitos_idade': (req_idade_val, req_idade_obs),
            'tempo_contribuicao_ok': (tc_val, tc_obs),
            'tempo_servico_publico_ok': (sp_val, sp_obs),
            'carreira_cargo_ok': (carr_cargo_val, carr_cargo_obs),
            'tempo_carreira_ok': (carr_val, carr_obs),
            'tempo_no_cargo_ok': (cargo_val, cargo_obs),
            'marco_temporal_ok': (marc_val, marc_obs),
            'condicao_dependente_ok': (dep_val, dep_obs),
            'normas_vigentes_epoca_ok': (norm_val, norm_obs),
            'resultado_sugerido': eleg_resultado,
        },
        'calculo': {
            'teto_acumulacao_ok': (teto_val, teto_obs),
            'media_integralidade_ok': (integ_val, integ_obs),
            'reajuste_ok': (reaj_val, reaj_obs),
            'base_calculo_ok': (base_calc_val, base_calc_obs),
            'regime_compativel': (regime_val, regime_obs),
            'resultado_sugerido': calc_resultado,
        },
        'folha': {
            'tipo_divergencia': divergencia_tipo,
            'divergencia_valor': str(divergencia_valor),
            'resultado_sugerido': folha_resultado,
        },
    }


def _inferir_sexo(nome):
    """
    Heurística simples: termina em 'a' → feminino, caso contrário masculino.
    Retorna 'F' ou 'M'.
    """
    if not nome:
        return 'M'
    primeiro = nome.strip().split()[0].lower()
    femininos = {'a', 'e', 'i'}
    if primeiro[-1] in femininos:
        return 'F'
    return 'M'
