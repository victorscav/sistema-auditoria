from decimal import Decimal
from django.db import models
from processos.models import ReajusteINSS


def gerar_analise_tecnica(processo, elegibilidade, calculo, folha,
                          dados_beneficio, valor_esperado, passos_reajuste, achados):
    """
    Gera automaticamente os parágrafos da análise técnica com base em todos os
    campos preenchidos nas abas de elegibilidade, cálculo e folha.
    Retorna lista de strings (cada item é um parágrafo).
    """
    paragrafos = []
    beneficiario = processo.beneficiario

    # ── 1. Introdução ─────────────────────────────────────────────────────────
    data_conc = processo.data_concessao.strftime('%d/%m/%Y') if processo.data_concessao else 'não informada'
    intro = (
        f"Trata-se do processo n.º {processo.numero}, referente à concessão de "
        f"{processo.get_tipo_beneficio_display()} em favor de {beneficiario.nome}"
    )
    if beneficiario.cpf:
        intro += f" (CPF {beneficiario.cpf})"
    if beneficiario.cargo:
        intro += f", ocupante do cargo de {beneficiario.cargo}"
        if beneficiario.carreira:
            intro += f" na carreira {beneficiario.carreira}"
    intro += f", com data de concessão em {data_conc}"
    if dados_beneficio:
        if dados_beneficio.valor_concedido:
            intro += f", no valor inicial de R$ {dados_beneficio.valor_concedido}"
        if dados_beneficio.regime_reajuste:
            intro += f", sujeito ao regime de reajuste de {dados_beneficio.get_regime_reajuste_display()}"
    intro += "."
    if processo.instituto:
        intro += f" O processo está vinculado ao {processo.instituto.nome}."
    paragrafos.append(intro)

    # ── 2. Elegibilidade ──────────────────────────────────────────────────────
    if elegibilidade:
        checks = [
            ('enquadramento_correto',    'enquadramento_obs',        'o enquadramento no tipo de benefício'),
            ('requisitos_idade',         'requisitos_idade_obs',      'os requisitos de idade'),
            ('tempo_contribuicao_ok',    'tempo_contribuicao_obs',    'o tempo de contribuição'),
            ('tempo_servico_publico_ok', 'tempo_servico_publico_obs', 'o tempo de serviço público'),
            ('normas_vigentes_epoca_ok', 'normas_vigentes_epoca_obs', 'as normas vigentes à época da concessão'),
            ('carreira_cargo_ok',        'carreira_cargo_obs',        'a carreira e o cargo'),
            ('tempo_carreira_ok',        'tempo_carreira_obs',        'o tempo de carreira'),
            ('tempo_no_cargo_ok',        'tempo_no_cargo_obs',        'o tempo no cargo'),
            ('marco_temporal_ok',        'marco_temporal_obs',        'o marco temporal de ingresso no serviço público'),
            ('condicao_dependente_ok',   'condicao_dependente_obs',   'a condição de dependente'),
        ]
        conformes, nao_conformes = [], []
        for field_ok, field_obs, label in checks:
            val = getattr(elegibilidade, field_ok, None)
            obs = getattr(elegibilidade, field_obs, '') or ''
            if val is True:
                conformes.append(label)
            elif val is False:
                nao_conformes.append(f"{label}{' (' + obs + ')' if obs else ''}")

        p = "No que se refere à elegibilidade, "
        if nao_conformes and conformes:
            p += (
                f"a análise identificou não conformidade em: {'; '.join(nao_conformes)}. "
                f"Os demais requisitos verificados — {', '.join(conformes)} — foram considerados conformes."
            )
        elif nao_conformes:
            p += f"a análise identificou não conformidade em: {'; '.join(nao_conformes)}."
        elif conformes:
            p += f"todos os requisitos verificados — {', '.join(conformes)} — foram considerados conformes."
        else:
            p += "a análise de elegibilidade ainda não foi concluída."

        result = elegibilidade.resultado
        if result and result != 'INDETERMINADO':
            labels = {'CONFORME': 'CONFORME', 'NAO_CONFORME': 'NÃO CONFORME', 'RESSALVAS': 'CONFORME COM RESSALVAS'}
            p += f" Resultado da análise de elegibilidade: {labels.get(result, result)}."
        paragrafos.append(p)

    # ── 3. Conformidade de Cálculo ────────────────────────────────────────────
    if calculo:
        regime = dados_beneficio.regime_reajuste if dados_beneficio else None
        tipo = processo.tipo_beneficio
        irregularidades = []

        if tipo == 'PENSAO_MORTE':
            sit = calculo.situacao_instituidor_pensao
            if sit == 'APOSENTADO':
                base_label = 'base de cálculo (último contracheque do aposentado falecido)'
            elif sit == 'EM_ATIVIDADE':
                base_label = 'base de cálculo (última remuneração do servidor falecido em atividade)'
            else:
                base_label = 'base de cálculo da pensão'
            if calculo.base_calculo_ok is False:
                obs = calculo.base_calculo_obs or ''
                irregularidades.append(f"{base_label}{': ' + obs if obs else ''}")
            if calculo.reajuste_ok is False:
                obs = calculo.reajuste_obs or ''
                irregularidades.append(f"reajuste aplicado{': ' + obs if obs else ''}")
        elif regime == 'MEDIA':
            if calculo.media_integralidade_ok is False:
                obs = calculo.media_integralidade_obs or ''
                irregularidades.append(f"cálculo da média/integralidade{': ' + obs if obs else ''}")
            if calculo.reajuste_ok is False:
                obs = calculo.reajuste_obs or ''
                irregularidades.append(f"reajuste pelo índice INSS{': ' + obs if obs else ''}")
        elif regime == 'PARIDADE':
            if calculo.composicao_remuneracao_ok is False:
                obs = calculo.composicao_remuneracao_obs or ''
                irregularidades.append(f"composição da remuneração em regime de paridade{': ' + obs if obs else ''}")
        else:
            for fok, fobs, lbl in [
                ('base_calculo_ok',         'base_calculo_obs',         'base de cálculo'),
                ('composicao_remuneracao_ok','composicao_remuneracao_obs','composição da remuneração'),
                ('media_integralidade_ok',  'media_integralidade_obs',   'média/integralidade'),
                ('reajuste_ok',             'reajuste_obs',              'reajuste'),
            ]:
                if getattr(calculo, fok, None) is False:
                    obs = getattr(calculo, fobs, '') or ''
                    irregularidades.append(f"{lbl}{': ' + obs if obs else ''}")

        if calculo.teto_acumulacao_ok is False:
            obs = calculo.teto_acumulacao_obs or ''
            irregularidades.append(f"teto remuneratório ou acumulação de cargos{': ' + obs if obs else ''}")

        p = "Quanto à conformidade de cálculo, "
        if irregularidades:
            p += f"foram identificadas irregularidades em: {'; '.join(irregularidades)}."
        else:
            result = calculo.resultado
            if result == 'CONFORME':
                p += "todos os itens verificados estão em conformidade com a legislação aplicável."
            elif result == 'NAO_CONFORME':
                p += "foram identificadas irregularidades nos itens analisados."
            else:
                p += "os itens verificados estão em conformidade com a legislação aplicável."

        if calculo.metodo_reajuste_aplicado:
            metodo = calculo.get_metodo_reajuste_aplicado_display() or calculo.metodo_reajuste_aplicado
            p += f" O método de reajuste verificado foi '{metodo}'"
            if calculo.lei_municipal_aplicada:
                p += f", com aplicação da lei municipal '{calculo.lei_municipal_aplicada}'"
            if calculo.indice_inss_aplicado:
                p += f", com índice INSS de {calculo.indice_inss_aplicado}%"
            if calculo.regime_compativel is True:
                p += ", compatível com o regime jurídico do benefício."
            elif calculo.regime_compativel is False:
                p += ", INCOMPATÍVEL com o regime jurídico do benefício."
            else:
                p += "."

        if calculo.houve_acumulacao:
            p += " Verificou-se acumulação de benefícios"
            if calculo.acumulacao_cargos_acumulaveis is True:
                p += ", tratando-se de cargos acumuláveis nos termos do art. 37, XVI da CF/88"
            if calculo.acumulacao_valor_total:
                p += f", com valor total de R$ {calculo.acumulacao_valor_total}"
            if calculo.acumulacao_regular is True:
                p += ". A acumulação está regular."
            elif calculo.acumulacao_regular is False:
                p += ". A acumulação NÃO está regular, em desacordo com o art. 24 da EC 103/2019."
            else:
                p += "."
            if calculo.acumulacao_obs:
                p += f" {calculo.acumulacao_obs}"

        result = calculo.resultado
        if result and result != 'INDETERMINADO':
            labels = {'CONFORME': 'CONFORME', 'NAO_CONFORME': 'NÃO CONFORME', 'RESSALVAS': 'CONFORME COM RESSALVAS'}
            p += f" Resultado da análise de cálculo: {labels.get(result, result)}."
        paragrafos.append(p)

    # ── 4. Conferência da Folha ───────────────────────────────────────────────
    if folha or valor_esperado:
        regime = dados_beneficio.regime_reajuste if dados_beneficio else None
        p = "Em relação à conferência da folha de pagamento, "

        if passos_reajuste and folha and folha.valor_concedido:
            if regime == 'PARIDADE':
                leis = "; ".join(
                    f"Lei nº {s['lei']} (vigência {s['vigencia']}, +{s['percentual']}%)"
                    for s in passos_reajuste
                )
                p += (
                    f"o valor inicial de R$ {folha.valor_concedido} foi reconstituído mediante "
                    f"aplicação das seguintes leis municipais de reajuste: {leis}. "
                )
            elif regime == 'MEDIA':
                indices = "; ".join(
                    f"INSS {s['ano']} ({s['vigencia']}, +{s['percentual']}%)"
                    for s in passos_reajuste
                )
                p += (
                    f"o valor inicial de R$ {folha.valor_concedido} foi reconstituído mediante "
                    f"aplicação dos seguintes índices INSS: {indices}. "
                )
        elif folha and folha.valor_concedido:
            p += f"o valor inicial verificado foi de R$ {folha.valor_concedido}. "

        if valor_esperado:
            p += f"O valor esperado no período de referência totalizou R$ {valor_esperado}. "

        if folha and folha.valor_pago_folha:
            p += f"O valor verificado na folha de pagamento foi de R$ {folha.valor_pago_folha}. "

        if folha:
            if folha.tipo_divergencia == 'SEM_DIVERGENCIA':
                p += "Não foram identificadas divergências financeiras entre o valor esperado e o valor pago na folha."
            elif folha.tipo_divergencia == 'PAGAMENTO_MAIOR':
                p += (
                    f"Foi identificada divergência: o valor pago é R$ {folha.impacto_financeiro_estimado} "
                    f"MAIOR que o esperado, configurando pagamento a maior que demanda providências corretivas."
                )
            elif folha.tipo_divergencia == 'PAGAMENTO_MENOR':
                p += (
                    f"Foi identificada divergência: o valor pago é R$ {folha.impacto_financeiro_estimado} "
                    f"MENOR que o esperado, configurando possível déficit no pagamento ao beneficiário."
                )
            if folha.observacoes:
                p += f" {folha.observacoes}"
            result = folha.resultado
            if result and result != 'INDETERMINADO':
                labels = {'CONFORME': 'CONFORME', 'NAO_CONFORME': 'NÃO CONFORME', 'RESSALVAS': 'CONFORME COM RESSALVAS'}
                p += f" Resultado da conferência de folha: {labels.get(result, result)}."
        paragrafos.append(p)

    # ── 5. Achados ────────────────────────────────────────────────────────────
    achados_list = list(achados) if achados else []
    if achados_list:
        nc = sum(1 for a in achados_list if a.classificacao == 'NAO_CONFORME')
        intro = f"Foram registrados {len(achados_list)} achado(s) de auditoria"
        if nc:
            intro += f", dos quais {nc} classificado(s) como Não Conforme"
        intro += ":"
        paragrafos.append(intro)
        for a in achados_list:
            desc = f"[{a.get_classificacao_display()}] {a.descricao}"
            if a.normas_aplicaveis:
                desc += f" Normas: {a.normas_aplicaveis}."
            if a.impacto_financeiro:
                desc += f" Impacto financeiro estimado: R$ {a.impacto_financeiro}."
            if a.recomendacao:
                desc += f" Recomendação: {a.recomendacao}."
            paragrafos.append(desc)

    # ── 6. Conclusão ─────────────────────────────────────────────────────────
    resultado_geral = processo.get_resultado_analise()
    if resultado_geral:
        labels = {'CONFORME': 'CONFORME', 'NAO_CONFORME': 'NÃO CONFORME', 'RESSALVAS': 'CONFORME COM RESSALVAS'}
        result_display = labels.get(resultado_geral, resultado_geral)
        concl = (
            f"Diante do exposto, o processo n.º {processo.numero} — {beneficiario.nome} — "
            f"recebe resultado final: {result_display}."
        )
        if resultado_geral == 'CONFORME':
            concl += (
                " A concessão do benefício atende aos requisitos legais e regulamentares, "
                "os valores estão corretamente calculados e não foram identificadas divergências "
                "relevantes na folha de pagamento."
            )
        elif resultado_geral == 'NAO_CONFORME':
            concl += (
                " Foram identificadas irregularidades que demandam providências corretivas "
                "por parte do gestor do RPPS, conforme detalhado nas seções anteriores e nos achados registrados."
            )
        elif resultado_geral == 'RESSALVAS':
            concl += (
                " O processo apresenta conformidade geral, porém com ressalvas que merecem "
                "atenção e acompanhamento continuado por parte do gestor do RPPS."
            )
        paragrafos.append(concl)

    return paragrafos


def calcular_valor_esperado(processo):
    """
    Calcula valor_esperado da conferência de folha com base no regime de reajuste.
    MÉDIA + piso → valor esperado = salário mínimo vigente (não aplica tabela INSS).
    MÉDIA acima  → aplica índices INSS após data_concessao até data_ref.
    PARIDADE     → se contracheque tiver ultima_remuneracao_cargo, usa esse valor +
                   triênio correto (vencimento_base × percentual_trienio / 100).
                   Caso contrário, aplica leis municipais do instituto.
    Retorna (valor_esperado: Decimal|None, passos: list[dict]).
    """
    import datetime as _dt
    dados = getattr(processo, 'dados_beneficio', None)
    contracheque = getattr(processo, 'contracheque', None)

    if not dados or not dados.valor_concedido or not processo.data_concessao:
        return None, []

    # valor_pago_folha reflete o pagamento corrente (ano atual); contracheque pode ser antigo.
    contracheque_ref = contracheque.mes_referencia if contracheque else None
    if dados.valor_pago_folha:
        data_ref = _dt.date.today()
    else:
        data_ref = contracheque_ref
    regime = dados.regime_reajuste
    valor_base = Decimal(str(dados.valor_concedido))
    ano_base = processo.data_concessao.year

    # Detecta se o benefício foi concedido no salário mínimo
    sm_concessao_obj = ReajusteINSS.objects.filter(ano__lte=ano_base).order_by('-ano').first()
    sm_concessao = sm_concessao_obj.salario_minimo if sm_concessao_obj else None
    is_salario_minimo = sm_concessao is not None and abs(valor_base - sm_concessao) <= Decimal('1.00')

    if regime == 'MEDIA' and is_salario_minimo:
        # Benefício no piso: valor esperado é o SM vigente, não índice INSS
        ano_ref = data_ref.year if data_ref else _dt.date.today().year
        sm_atual_obj = ReajusteINSS.objects.filter(ano__lte=ano_ref).order_by('-ano').first()
        sm_atual = sm_atual_obj.salario_minimo if sm_atual_obj else None
        return sm_atual, []

    if regime == 'MEDIA' and data_ref:
        return _calcular_media(dados.valor_concedido, processo.data_concessao, data_ref)

    if regime == 'PARIDADE':
        # Prioridade 1: demonstrativo importado — extrai vencimento base e triênio
        # reais e recalcula o esperado com o triênio correto (apenas sobre vencimento base).
        if contracheque:
            analise = contracheque.analisar_trienio_demonstrativo()
            if analise is not None:
                return analise['valor_esperado_correto'], []

        # Prioridade 2: contracheque com remuneração preenchida manualmente pelo auditor.
        # ultima_remuneracao_cargo deve ser preenchida SEM o valor do triênio;
        # o triênio correto é calculado como percentual_trienio % × vencimento_base_paradigma.
        if contracheque and contracheque.ultima_remuneracao_cargo:
            base_paridade = Decimal(str(contracheque.ultima_remuneracao_cargo))
            trienio_correto = contracheque.valor_trienio_calculado or Decimal('0')
            valor_esperado = (base_paridade + trienio_correto).quantize(Decimal('0.01'))
            return valor_esperado, []

        # Prioridade 3: leis municipais de reajuste cadastradas no instituto.
        if data_ref and processo.instituto_id:
            return _calcular_paridade(processo, dados.valor_concedido, data_ref)

    return None, []


def _calcular_media(valor_base, data_concessao, data_ref):
    reajustes = ReajusteINSS.objects.filter(
        vigencia__gt=data_concessao,
        vigencia__lte=data_ref,
    ).order_by('vigencia')

    valor = Decimal(str(valor_base))
    passos = []
    for r in reajustes:
        pct = r.percentual_para(data_concessao)
        fator = Decimal('1') + pct / Decimal('100')
        anterior = valor
        valor = (valor * fator).quantize(Decimal('0.01'))
        passos.append({
            'ano':        r.ano,
            'vigencia':   r.vigencia.strftime('%m/%Y'),
            'percentual': float(pct),
            'anterior':   float(anterior),
            'novo':       float(valor),
            'base_legal': r.base_legal,
        })
    return valor, passos


def _calcular_paridade(processo, valor_concedido, data_ref):
    from institutos.models import LeiMunicipalReajuste
    is_pensao = (processo.tipo_beneficio == 'PENSAO_MORTE')
    filtro = {'aplica_pensoes': True} if is_pensao else {'aplica_inativos': True}

    # A lei só se aplica se o benefício existia ANTES da publicação da lei
    # (quem se aposenta após a publicação já incorpora o novo salário, sem direito a reajuste).
    # Fallback: usa data_vigencia quando data_publicacao não está preenchida.
    leis_qs = LeiMunicipalReajuste.objects.filter(
        instituto_id=processo.instituto_id,
        **filtro,
    ).filter(
        # publicação após a concessão → beneficiário existia antes da lei
        models.Q(data_publicacao__isnull=False, data_publicacao__gt=processo.data_concessao)
        | models.Q(data_publicacao__isnull=True,  data_vigencia__gt=processo.data_concessao)
    ).filter(
        data_vigencia__lte=data_ref,
    ).order_by('data_vigencia')

    if not leis_qs.exists():
        return None, []

    valor = Decimal(str(valor_concedido))
    passos = []
    for lei in leis_qs:
        fator = Decimal('1') + lei.percentual / Decimal('100')
        anterior = valor
        valor = (valor * fator).quantize(Decimal('0.01'))
        passos.append({
            'lei':        lei.numero,
            'vigencia':   lei.data_vigencia.strftime('%m/%Y'),
            'percentual': float(lei.percentual),
            'anterior':   float(anterior),
            'novo':       float(valor),
            'base_legal': lei.descricao or lei.base_legal,
        })
    return valor, passos


def recalcular_conferencia(processo, salvar=False):
    """
    Recalcula valor_esperado, tipo_divergencia, impacto_financeiro e DivergenciaFolha.

    Com salvar=False (padrão): atualiza apenas o objeto em memória para exibição
    correta em telas e relatórios, sem nenhuma escrita no banco de dados.

    Com salvar=True: persiste todas as alterações, sincroniza divergências automáticas
    e recalcula tipo_divergencia/impacto. Use apenas em ações explícitas do auditor.
    """
    from analise.models import ConferenciaFolha, DivergenciaFolha

    dados = getattr(processo, 'dados_beneficio', None)
    if not dados or not dados.valor_concedido:
        return

    valor_esperado, _ = calcular_valor_esperado(processo)

    folha = getattr(processo, 'conferenciafolha', None)
    if folha is None:
        if not salvar or (valor_esperado is None and not dados.valor_pago_folha):
            return
        folha, _ = ConferenciaFolha.objects.get_or_create(processo=processo)
        processo.conferenciafolha = folha

    # Atualiza o objeto em memória (necessário para exibição correta)
    if folha.valor_concedido != dados.valor_concedido:
        folha.valor_concedido = dados.valor_concedido

    vpf = dados.valor_pago_folha
    if vpf is not None and folha.valor_pago_folha != vpf:
        folha.valor_pago_folha = vpf

    if valor_esperado is not None and folha.valor_esperado != valor_esperado:
        folha.valor_esperado = valor_esperado

    if not salvar:
        return

    # ── A partir daqui: operações de escrita no banco ─────────────────────────
    folha.save()

    _sync_divergencias_automaticas(processo, folha, dados, valor_esperado)
    _recalcular_tipo_divergencia(folha)


def _sync_divergencias_automaticas(processo, folha, dados, valor_esperado_correto):
    """Detecta e sincroniza divergências automáticas no ConferenciaFolha."""
    from analise.models import DivergenciaFolha
    regime = dados.regime_reajuste
    contracheque = getattr(processo, 'contracheque', None)
    tol = Decimal('0.01')

    # ── 1. Triênio calculado incorretamente (PARIDADE com demonstrativo) ──────
    analise_trienio = None
    if regime == 'PARIDADE' and contracheque:
        try:
            analise_trienio = contracheque.analisar_trienio_demonstrativo()
        except Exception:
            pass

    existing_trienio = folha.divergencias.filter(
        tipo=DivergenciaFolha.Tipo.TRIENIO_MAIOR,
        detectado_automaticamente=True
    ).first()

    if analise_trienio and analise_trienio['tem_divergencia']:
        valor_div = analise_trienio['pagamento_maior']
        if existing_trienio:
            if abs(existing_trienio.valor - valor_div) > tol:
                existing_trienio.valor = valor_div
                existing_trienio.save()
        else:
            instituto = processo.instituto
            base_legal = instituto.norma_trienio if instituto and instituto.norma_trienio else ''
            DivergenciaFolha.objects.create(
                conferencia=folha,
                tipo=DivergenciaFolha.Tipo.TRIENIO_MAIOR,
                impacto=DivergenciaFolha.Impacto.MAIOR,
                valor=valor_div,
                descricao=(
                    f"Triênio de {analise_trienio['trienio_percentual']}% calculado sobre "
                    f"vencimento base + FG incorporada (R$ {analise_trienio['trienio_pago']}) "
                    f"em vez de somente sobre o vencimento base "
                    f"(R$ {analise_trienio['trienio_correto']})."
                ),
                base_legal=base_legal,
                detectado_automaticamente=True,
            )
    elif existing_trienio:
        existing_trienio.delete()

    # ── 2. Reajuste a menor/maior (PARIDADE com lei + demonstrativo) ──────────
    # Compara o valor que a lei municipal esperaria (sobre valor_concedido) com o
    # valor que o demonstrativo mostra (corrigido do triênio). Se diferentes, há
    # uma divergência de reajuste independente da divergência de triênio.
    if regime == 'PARIDADE' and analise_trienio and processo.data_concessao and processo.instituto_id:
        import datetime as _dt
        lei_valor, _ = _calcular_paridade(processo, dados.valor_concedido, _dt.date.today())
        if lei_valor is not None and dados.valor_pago_folha:
            # Reajuste comparado direto contra o valor pago na folha —
            # apuração independente do triênio.
            valor_pago = Decimal(str(dados.valor_pago_folha))
            diff_reajuste = (lei_valor - valor_pago).quantize(Decimal('0.01'))
            # Tolerância de R$ 0,05 para absorver arredondamentos
            tol_reajuste = Decimal('0.05')

            existing_rej_menor = folha.divergencias.filter(
                tipo=DivergenciaFolha.Tipo.REAJUSTE_MENOR,
                detectado_automaticamente=True
            ).first()
            existing_rej_maior = folha.divergencias.filter(
                tipo=DivergenciaFolha.Tipo.REAJUSTE_MAIOR,
                detectado_automaticamente=True
            ).first()

            if diff_reajuste > tol_reajuste:
                # Lei esperaria mais do que o pago na folha → reajuste a menor
                if existing_rej_menor:
                    if abs(existing_rej_menor.valor - diff_reajuste) > tol:
                        existing_rej_menor.valor = diff_reajuste
                        existing_rej_menor.descricao = (
                            f"Reajuste aplicado a menor: valor esperado pela lei municipal "
                            f"R$ {lei_valor}, valor pago na folha R$ {valor_pago}."
                        )
                        existing_rej_menor.save()
                else:
                    DivergenciaFolha.objects.create(
                        conferencia=folha,
                        tipo=DivergenciaFolha.Tipo.REAJUSTE_MENOR,
                        impacto=DivergenciaFolha.Impacto.MENOR,
                        valor=diff_reajuste,
                        descricao=(
                            f"Reajuste aplicado a menor: valor esperado pela lei municipal "
                            f"R$ {lei_valor}, valor pago na folha R$ {valor_pago}."
                        ),
                        detectado_automaticamente=True,
                    )
                if existing_rej_maior:
                    existing_rej_maior.delete()
            elif diff_reajuste < -tol_reajuste:
                # Lei esperaria menos do que o pago na folha → reajuste a maior
                valor_abs = abs(diff_reajuste)
                if existing_rej_maior:
                    if abs(existing_rej_maior.valor - valor_abs) > tol:
                        existing_rej_maior.valor = valor_abs
                        existing_rej_maior.descricao = (
                            f"Reajuste aplicado a maior: valor esperado pela lei municipal "
                            f"R$ {lei_valor}, valor pago na folha R$ {valor_pago}."
                        )
                        existing_rej_maior.save()
                else:
                    DivergenciaFolha.objects.create(
                        conferencia=folha,
                        tipo=DivergenciaFolha.Tipo.REAJUSTE_MAIOR,
                        impacto=DivergenciaFolha.Impacto.MAIOR,
                        valor=valor_abs,
                        descricao=(
                            f"Reajuste aplicado a maior: valor esperado pela lei municipal "
                            f"R$ {lei_valor}, valor pago na folha R$ {valor_pago}."
                        ),
                        detectado_automaticamente=True,
                    )
                if existing_rej_menor:
                    existing_rej_menor.delete()
            else:
                if existing_rej_menor:
                    existing_rej_menor.delete()
                if existing_rej_maior:
                    existing_rej_maior.delete()

    # ── 3. Divergência geral (MEDIA ou PARIDADE sem demonstrativo) ────────────
    # Cobre todos os casos não tratados pelos blocos 1 e 2: compara valor_pago
    # com folha.valor_esperado já calculado e persistido pelo recalcular_conferencia.
    if not analise_trienio and folha.valor_esperado and dados.valor_pago_folha:
        valor_pago = Decimal(str(dados.valor_pago_folha))
        valor_esp  = Decimal(str(folha.valor_esperado))
        diff = valor_pago - valor_esp

        # Tolerância: R$ 1,00 para benefício no piso (SM pode diferir por arredondamento)
        sm_obj = ReajusteINSS.objects.filter(
            ano__lte=processo.data_concessao.year
        ).order_by('-ano').first() if processo.data_concessao else None
        sm_rc = sm_obj.salario_minimo if sm_obj else None
        is_piso = (sm_rc is not None
                   and folha.valor_concedido is not None
                   and abs(Decimal(str(folha.valor_concedido)) - sm_rc) <= Decimal('1.00'))
        tol_geral = Decimal('1.00') if is_piso else Decimal('0.05')

        existing_g_menor = folha.divergencias.filter(
            tipo__in=[DivergenciaFolha.Tipo.REAJUSTE_MENOR, DivergenciaFolha.Tipo.OUTRO_MENOR],
            detectado_automaticamente=True
        ).first()
        existing_g_maior = folha.divergencias.filter(
            tipo__in=[DivergenciaFolha.Tipo.REAJUSTE_MAIOR, DivergenciaFolha.Tipo.OUTRO_MAIOR],
            detectado_automaticamente=True
        ).first()

        if diff < -tol_geral:
            valor_abs = abs(diff).quantize(Decimal('0.01'))
            if regime == 'MEDIA':
                descricao = (
                    f"Reajuste INSS aplicado a menor: valor esperado R$ {valor_esp}, "
                    f"valor pago na folha R$ {valor_pago}. "
                    f"Diferença apurada: R$ {valor_abs} a menor por mês de competência."
                )
            else:
                descricao = (
                    f"Reajuste aplicado a menor: valor esperado R$ {valor_esp}, "
                    f"valor pago na folha R$ {valor_pago}. "
                    f"Diferença apurada: R$ {valor_abs} a menor por mês de competência."
                )
            if existing_g_menor:
                if abs(existing_g_menor.valor - valor_abs) > tol:
                    existing_g_menor.valor = valor_abs
                    existing_g_menor.descricao = descricao
                    existing_g_menor.save()
            else:
                DivergenciaFolha.objects.create(
                    conferencia=folha,
                    tipo=DivergenciaFolha.Tipo.REAJUSTE_MENOR,
                    impacto=DivergenciaFolha.Impacto.MENOR,
                    valor=valor_abs,
                    descricao=descricao,
                    detectado_automaticamente=True,
                )
            if existing_g_maior:
                existing_g_maior.delete()

        elif diff > tol_geral:
            valor_abs = diff.quantize(Decimal('0.01'))
            if regime == 'MEDIA':
                descricao = (
                    f"Reajuste INSS aplicado a maior: valor esperado R$ {valor_esp}, "
                    f"valor pago na folha R$ {valor_pago}. "
                    f"Diferença apurada: R$ {valor_abs} a maior por mês de competência."
                )
            else:
                descricao = (
                    f"Reajuste aplicado a maior: valor esperado R$ {valor_esp}, "
                    f"valor pago na folha R$ {valor_pago}. "
                    f"Diferença apurada: R$ {valor_abs} a maior por mês de competência."
                )
            if existing_g_maior:
                if abs(existing_g_maior.valor - valor_abs) > tol:
                    existing_g_maior.valor = valor_abs
                    existing_g_maior.descricao = descricao
                    existing_g_maior.save()
            else:
                DivergenciaFolha.objects.create(
                    conferencia=folha,
                    tipo=DivergenciaFolha.Tipo.REAJUSTE_MAIOR,
                    impacto=DivergenciaFolha.Impacto.MAIOR,
                    valor=valor_abs,
                    descricao=descricao,
                    detectado_automaticamente=True,
                )
            if existing_g_menor:
                existing_g_menor.delete()

        else:
            if existing_g_menor:
                existing_g_menor.delete()
            if existing_g_maior:
                existing_g_maior.delete()


def _recalcular_tipo_divergencia(folha):
    """Atualiza tipo_divergencia e impacto_financeiro_estimado do ConferenciaFolha
    com base no conjunto atual de divergências (automáticas + manuais)."""
    from analise.models import DivergenciaFolha, ConferenciaFolha

    divs = list(folha.divergencias.all())
    if not divs:
        # Sem divergências registradas: comparação direta pago vs esperado
        base_comp = folha.valor_esperado
        if base_comp is not None and folha.valor_pago_folha:
            diff = folha.valor_pago_folha - base_comp
            tol = Decimal('0.01')
            if diff > tol:
                novo_tipo = ConferenciaFolha.TipoDivergencia.PAGAMENTO_MAIOR
                novo_impact = diff
            elif diff < -tol:
                novo_tipo = ConferenciaFolha.TipoDivergencia.PAGAMENTO_MENOR
                novo_impact = abs(diff)
            else:
                novo_tipo = ConferenciaFolha.TipoDivergencia.SEM_DIVERGENCIA
                novo_impact = Decimal('0.00')
        else:
            novo_tipo = ConferenciaFolha.TipoDivergencia.SEM_DIVERGENCIA
            novo_impact = Decimal('0.00')
    else:
        total_maior = sum(d.valor for d in divs if d.impacto == DivergenciaFolha.Impacto.MAIOR)
        total_menor = sum(d.valor for d in divs if d.impacto == DivergenciaFolha.Impacto.MENOR)
        net = total_maior - total_menor
        tol = Decimal('0.01')
        if total_maior > tol and total_menor > tol:
            novo_tipo = ConferenciaFolha.TipoDivergencia.COM_DIVERGENCIAS
            novo_impact = abs(net)
        elif total_maior > tol:
            novo_tipo = ConferenciaFolha.TipoDivergencia.PAGAMENTO_MAIOR
            novo_impact = total_maior
        elif total_menor > tol:
            novo_tipo = ConferenciaFolha.TipoDivergencia.PAGAMENTO_MENOR
            novo_impact = total_menor
        else:
            novo_tipo = ConferenciaFolha.TipoDivergencia.SEM_DIVERGENCIA
            novo_impact = Decimal('0.00')

    if folha.tipo_divergencia != novo_tipo or folha.impacto_financeiro_estimado != novo_impact:
        folha.tipo_divergencia = novo_tipo
        folha.impacto_financeiro_estimado = novo_impact
        folha.save()


def gerar_achados_de_divergencias(processo):
    """
    Cria AchadoAuditoria para cada DivergenciaFolha ainda não convertida.
    Textos completos gerados conforme o tipo de divergência.
    Retorna a quantidade de achados criados.
    """
    from analise.models import DivergenciaFolha, AchadoAuditoria

    folha = getattr(processo, 'conferenciafolha', None)
    if not folha:
        return 0

    # Reset flags when achados were deleted externally but flags remain True
    if folha.divergencias.filter(achado_gerado=True).exists() and not AchadoAuditoria.objects.filter(processo=processo).exists():
        folha.divergencias.update(achado_gerado=False)

    contracheque = getattr(processo, 'contracheque', None)
    analise_trienio = None
    if contracheque:
        try:
            analise_trienio = contracheque.analisar_trienio_demonstrativo()
        except Exception:
            pass

    instituto = processo.instituto
    norma_trienio = instituto.norma_trienio if instituto and instituto.norma_trienio else ''

    criados = 0
    for div in folha.divergencias.filter(achado_gerado=False):
        descricao = _texto_achado(div, analise_trienio, processo)
        normas = div.base_legal or norma_trienio if div.tipo == DivergenciaFolha.Tipo.TRIENIO_MAIOR else div.base_legal
        recomendacao = _recomendacao_achado(div, norma_trienio)

        AchadoAuditoria.objects.create(
            processo=processo,
            classificacao=AchadoAuditoria.Classificacao.NAO_CONFORME,
            descricao=descricao,
            normas_aplicaveis=normas or '',
            impacto_financeiro=div.valor,
            recomendacao=recomendacao,
        )
        div.achado_gerado = True
        div.save(update_fields=['achado_gerado'])
        criados += 1

    return criados


def _texto_achado(div, analise_trienio, processo):
    from analise.models import DivergenciaFolha
    dados = getattr(processo, 'dados_beneficio', None)

    if div.tipo == DivergenciaFolha.Tipo.TRIENIO_MAIOR and analise_trienio:
        pct = analise_trienio['trienio_percentual']
        venc_base = analise_trienio['vencimento_base']
        trienio_pago = analise_trienio['trienio_pago']
        trienio_correto = analise_trienio['trienio_correto']
        diferenca = analise_trienio['diferenca_trienio']
        # Base real usada no cálculo incorreto = triênio pago ÷ percentual
        from decimal import Decimal
        base_errada = (trienio_pago / (pct / Decimal('100'))).quantize(Decimal('0.01'))
        return (
            f"Constatou-se que o adicional por tempo de serviço (triênio) foi calculado sobre "
            f"base de cálculo incorreta. O percentual de {pct}% foi aplicado sobre o valor de "
            f"R$ {base_errada} (vencimento base acrescido de gratificação incorporada), "
            f"resultando no pagamento de R$ {trienio_pago} a título de triênio. "
            f"O correto, conforme a legislação aplicável, seria aplicar o percentual "
            f"exclusivamente sobre o vencimento base (R$ {venc_base}), "
            f"o que corresponderia a R$ {trienio_correto}. "
            f"Diferença apurada: R$ {diferenca} a maior por mês de competência."
        )

    if div.tipo == DivergenciaFolha.Tipo.REAJUSTE_MENOR:
        valor_pago = dados.valor_pago_folha if dados else '—'
        # Extrai valor esperado da descrição existente ou usa apenas os valores da divergência
        return (
            f"Constatou-se que o reajuste previsto na legislação municipal não foi "
            f"integralmente aplicado ao benefício. O valor pago na folha é de "
            f"R$ {valor_pago}, inferior ao valor esperado conforme a lei municipal de reajuste. "
            f"Diferença apurada: R$ {div.valor} a menor por mês de competência. "
            f"{div.descricao}"
        )

    if div.tipo == DivergenciaFolha.Tipo.REAJUSTE_MAIOR:
        valor_pago = dados.valor_pago_folha if dados else '—'
        return (
            f"Constatou-se que o valor pago na folha (R$ {valor_pago}) supera o valor "
            f"esperado conforme a lei municipal de reajuste. "
            f"Diferença apurada: R$ {div.valor} a maior por mês de competência. "
            f"{div.descricao}"
        )

    # Fallback para tipos manuais
    return div.descricao or div.get_tipo_display()


def _recomendacao_achado(div, norma_trienio):
    from analise.models import DivergenciaFolha

    if div.tipo == DivergenciaFolha.Tipo.TRIENIO_MAIOR:
        base = f", nos termos de {norma_trienio}" if norma_trienio else ''
        return (
            f"Recalcular o adicional por tempo de serviço (triênio) utilizando como base "
            f"exclusivamente o vencimento base{base}. "
            f"Proceder à apuração e restituição dos valores pagos a maior."
        )

    if div.tipo == DivergenciaFolha.Tipo.REAJUSTE_MENOR:
        return (
            f"Aplicar o percentual de reajuste previsto na legislação municipal, "
            f"corrigindo o valor do benefício e pagando as diferenças devidas "
            f"com efeitos retroativos à data de vigência da lei."
        )

    if div.tipo == DivergenciaFolha.Tipo.REAJUSTE_MAIOR:
        return (
            f"Revisar o valor do benefício para adequá-lo ao esperado pela legislação municipal, "
            f"apurando e restituindo os valores pagos a maior."
        )

    return ''
