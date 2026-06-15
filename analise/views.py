from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from decimal import Decimal

from processos.models import Processo, ReajusteINSS
from .models import (
    AnaliseElegibilidade, AnaliseCalculo, ConferenciaFolha, DivergenciaFolha,
    AchadoAuditoria, ResultadoAnalise, NotaTecnica
)
from .auto_analise import executar_pre_analise
from .utils import calcular_valor_esperado, recalcular_conferencia, gerar_analise_tecnica, gerar_achados_de_divergencias
from institutos.models import EmpresaAuditora


def _get_subsidio_prefeito(processo):
    """Retorna subsidio_prefeito do instituto vinculado ao processo.
    Se o processo não tiver instituto, usa o único ativo disponível."""
    from institutos.models import Instituto
    if processo.instituto_id:
        return processo.instituto.subsidio_prefeito
    inst = Instituto.objects.filter(ativo=True).order_by('pk').first()
    return inst.subsidio_prefeito if inst else None


def _parse_bool(value):
    if value == 'true':
        return True
    if value == 'false':
        return False
    return None


def analise(request, processo_pk):
    processo = get_object_or_404(Processo.objects.select_related('beneficiario', 'contracheque', 'dados_beneficio'), pk=processo_pk)
    aba_ativa = request.GET.get('aba', 'elegibilidade')

    elegibilidade = getattr(processo, 'analiseelegibilidade', None)
    calculo = getattr(processo, 'analisecalculo', None)
    folha = getattr(processo, 'conferenciafolha', None)

    if request.method == 'POST':
        aba = request.POST.get('aba', 'elegibilidade')

        if aba == 'elegibilidade':
            fields = {
                'enquadramento_correto': _parse_bool(request.POST.get('enquadramento_correto')),
                'enquadramento_obs': request.POST.get('enquadramento_obs', ''),
                'requisitos_idade': _parse_bool(request.POST.get('requisitos_idade')),
                'requisitos_idade_obs': request.POST.get('requisitos_idade_obs', ''),
                'tempo_contribuicao_ok': _parse_bool(request.POST.get('tempo_contribuicao_ok')),
                'tempo_contribuicao_obs': request.POST.get('tempo_contribuicao_obs', ''),
                'tempo_servico_publico_ok': _parse_bool(request.POST.get('tempo_servico_publico_ok')),
                'tempo_servico_publico_obs': request.POST.get('tempo_servico_publico_obs', ''),
                'condicao_dependente_ok': _parse_bool(request.POST.get('condicao_dependente_ok')),
                'condicao_dependente_obs': request.POST.get('condicao_dependente_obs', ''),
                'normas_vigentes_epoca_ok': _parse_bool(request.POST.get('normas_vigentes_epoca_ok')),
                'normas_vigentes_epoca_obs': request.POST.get('normas_vigentes_epoca_obs', ''),
                'carreira_cargo_ok': _parse_bool(request.POST.get('carreira_cargo_ok')),
                'carreira_cargo_obs': request.POST.get('carreira_cargo_obs', ''),
                'tempo_carreira_ok': _parse_bool(request.POST.get('tempo_carreira_ok')),
                'tempo_carreira_obs': request.POST.get('tempo_carreira_obs', ''),
                'tempo_no_cargo_ok': _parse_bool(request.POST.get('tempo_no_cargo_ok')),
                'tempo_no_cargo_obs': request.POST.get('tempo_no_cargo_obs', ''),
                'marco_temporal_ok': _parse_bool(request.POST.get('marco_temporal_ok')),
                'marco_temporal_obs': request.POST.get('marco_temporal_obs', ''),
                'resultado': request.POST.get('resultado', ResultadoAnalise.INDETERMINADO),
                'auditor': request.user if request.user.is_authenticated else None,
            }
            AnaliseElegibilidade.objects.update_or_create(processo=processo, defaults=fields)
            _atualizar_status_processo(processo)
            messages.success(request, 'Análise de elegibilidade salva.')
            return redirect(f'{request.path}?aba=elegibilidade')

        elif aba == 'calculo':
            def safe_decimal(v):
                if not v:
                    return None
                try:
                    return float(str(v).replace(',', '.'))
                except Exception:
                    return None

            metodo = request.POST.get('metodo_reajuste_aplicado', '')
            fields = {
                'base_calculo_ok': _parse_bool(request.POST.get('base_calculo_ok')),
                'base_calculo_obs': request.POST.get('base_calculo_obs', ''),
                'composicao_remuneracao_ok': _parse_bool(request.POST.get('composicao_remuneracao_ok')),
                'composicao_remuneracao_obs': request.POST.get('composicao_remuneracao_obs', ''),
                'media_integralidade_ok': _parse_bool(request.POST.get('media_integralidade_ok')),
                'media_integralidade_obs': request.POST.get('media_integralidade_obs', ''),
                'cotas_familiares_ok': _parse_bool(request.POST.get('cotas_familiares_ok')),
                'cotas_familiares_obs': request.POST.get('cotas_familiares_obs', ''),
                'teto_acumulacao_ok': _parse_bool(request.POST.get('teto_acumulacao_ok')),
                'teto_acumulacao_obs': request.POST.get('teto_acumulacao_obs', ''),
                'reajuste_ok': _parse_bool(request.POST.get('reajuste_ok')),
                'reajuste_obs': request.POST.get('reajuste_obs', ''),
                'valor_base_reajuste': request.POST.get('valor_base_reajuste') or None,
                'ano_base_reajuste': request.POST.get('ano_base_reajuste') or None,
                'redutor_ok': _parse_bool(request.POST.get('redutor_ok')),
                'redutor_obs': request.POST.get('redutor_obs', ''),
                # Novos campos
                'metodo_reajuste_aplicado': metodo,
                'lei_municipal_aplicada': request.POST.get('lei_municipal_aplicada', ''),
                'indice_inss_aplicado': safe_decimal(request.POST.get('indice_inss_aplicado')),
                'valor_reconstruido_ano': safe_decimal(request.POST.get('valor_reconstruido_ano')),
                'valor_devido_mes_corrente': safe_decimal(request.POST.get('valor_devido_mes_corrente')),
                'diferenca_folha': safe_decimal(request.POST.get('diferenca_folha')),
                'situacao_instituidor_pensao': request.POST.get('situacao_instituidor_pensao', ''),
                # Acumulação Art. 24 EC 103/2019
                'houve_acumulacao': _parse_bool(request.POST.get('houve_acumulacao')),
                'acumulacao_cargos_acumulaveis': _parse_bool(request.POST.get('acumulacao_cargos_acumulaveis')),
                'acumulacao_valor_total': safe_decimal(request.POST.get('acumulacao_valor_total')),
                'acumulacao_regular': _parse_bool(request.POST.get('acumulacao_regular')),
                'acumulacao_obs': request.POST.get('acumulacao_obs', ''),
                'resultado': request.POST.get('resultado', ResultadoAnalise.INDETERMINADO),
                'auditor': request.user if request.user.is_authenticated else None,
            }
            obj, _ = AnaliseCalculo.objects.update_or_create(processo=processo, defaults=fields)
            # Verifica trava de regime após salvar (save() já calcula regime_compativel)
            if obj.regime_compativel is False:
                messages.warning(request, obj.regime_compativel_obs or 'Método de reajuste incompatível com o regime jurídico do benefício.')
            _atualizar_status_processo(processo)
            messages.success(request, 'Análise de cálculo salva.')
            return redirect(f'{request.path}?aba=calculo')

        elif aba == 'folha':
            # Apenas resultado e observações são editáveis pelo auditor;
            # os valores financeiros e a divergência são calculados automaticamente.
            obj, _ = ConferenciaFolha.objects.get_or_create(processo=processo)
            obj.resultado    = request.POST.get('resultado', ResultadoAnalise.INDETERMINADO)
            obj.observacoes  = request.POST.get('observacoes', '')
            obj.auditor      = request.user if request.user.is_authenticated else None
            obj.save()
            _atualizar_status_processo(processo)
            messages.success(request, 'Conferência de folha salva.')
            return redirect(f'{request.path}?aba=folha')

        elif aba == 'nota_tecnica':
            texto = request.POST.get('texto', '').strip()
            limitacao = request.POST.get('limitacao_documental', '').strip()
            NotaTecnica.objects.update_or_create(
                processo=processo,
                defaults={
                    'texto': texto,
                    'limitacao_documental': limitacao,
                    'auditor': request.user if request.user.is_authenticated else None,
                }
            )
            messages.success(request, 'Nota técnica salva.')
            return redirect(f'{request.path}?aba=nota_tecnica')

        elif aba == 'achados':
            classificacao = request.POST.get('classificacao', 'INDETERMINADO')
            descricao = request.POST.get('descricao', '').strip()
            if descricao:
                def safe_decimal(v):
                    if not v:
                        return None
                    try:
                        return float(v.replace(',', '.'))
                    except Exception:
                        return None

                AchadoAuditoria.objects.create(
                    processo=processo,
                    classificacao=classificacao,
                    descricao=descricao,
                    normas_aplicaveis=request.POST.get('normas_aplicaveis', ''),
                    impacto_financeiro=safe_decimal(request.POST.get('impacto_financeiro')),
                    recomendacao=request.POST.get('recomendacao', ''),
                )
                messages.success(request, 'Achado registrado.')
            return redirect(f'{request.path}?aba=achados')

    dados_beneficio = getattr(processo, 'dados_beneficio', None)

    # ── Conferência de Folha: cálculo automático ─────────────────────────────
    contracheque_obj = getattr(processo, 'contracheque', None)
    data_ref_folha   = contracheque_obj.mes_referencia if contracheque_obj else None
    regime           = dados_beneficio.regime_reajuste if dados_beneficio else None

    valor_esperado, passos_reajuste = calcular_valor_esperado(processo)

    # Fallback para PARIDADE sem leis cadastradas: usa valor manual da aba cálculo
    if valor_esperado is None and regime == 'PARIDADE':
        if calculo and calculo.valor_devido_mes_corrente:
            valor_esperado = Decimal(str(calculo.valor_devido_mes_corrente))
        elif calculo and calculo.valor_reconstruido_ano:
            valor_esperado = Decimal(str(calculo.valor_reconstruido_ano))

    # Persiste e recalcula divergência
    recalcular_conferencia(processo)
    folha = getattr(processo, 'conferenciafolha', None)

    # Monta rows para os formulários de análise
    elegibilidade_rows = [
        {'label': 'Enquadramento no tipo de benefício correto',
         'field_ok': 'enquadramento_correto', 'field_obs': 'enquadramento_obs',
         'value_ok': elegibilidade.enquadramento_correto if elegibilidade else None,
         'value_obs': elegibilidade.enquadramento_obs if elegibilidade else ''},
        {'label': 'Requisitos de idade atendidos',
         'field_ok': 'requisitos_idade', 'field_obs': 'requisitos_idade_obs',
         'value_ok': elegibilidade.requisitos_idade if elegibilidade else None,
         'value_obs': elegibilidade.requisitos_idade_obs if elegibilidade else ''},
        {'label': 'Tempo de contribuição verificado',
         'field_ok': 'tempo_contribuicao_ok', 'field_obs': 'tempo_contribuicao_obs',
         'value_ok': elegibilidade.tempo_contribuicao_ok if elegibilidade else None,
         'value_obs': elegibilidade.tempo_contribuicao_obs if elegibilidade else ''},
        {'label': 'Tempo de serviço público verificado',
         'field_ok': 'tempo_servico_publico_ok', 'field_obs': 'tempo_servico_publico_obs',
         'value_ok': elegibilidade.tempo_servico_publico_ok if elegibilidade else None,
         'value_obs': elegibilidade.tempo_servico_publico_obs if elegibilidade else ''},
        {'label': 'Condição de dependente verificada (pensões)',
         'field_ok': 'condicao_dependente_ok', 'field_obs': 'condicao_dependente_obs',
         'value_ok': elegibilidade.condicao_dependente_ok if elegibilidade else None,
         'value_obs': elegibilidade.condicao_dependente_obs if elegibilidade else ''},
        {'label': 'Normas vigentes à época aplicadas corretamente',
         'field_ok': 'normas_vigentes_epoca_ok', 'field_obs': 'normas_vigentes_epoca_obs',
         'value_ok': elegibilidade.normas_vigentes_epoca_ok if elegibilidade else None,
         'value_obs': elegibilidade.normas_vigentes_epoca_obs if elegibilidade else ''},
        {'label': 'Carreira e cargo verificados (requisitos da legislação municipal)',
         'field_ok': 'carreira_cargo_ok', 'field_obs': 'carreira_cargo_obs',
         'value_ok': elegibilidade.carreira_cargo_ok if elegibilidade else None,
         'value_obs': elegibilidade.carreira_cargo_obs if elegibilidade else ''},
        {'label': 'Tempo de carreira (quando exigido pela lei municipal)',
         'field_ok': 'tempo_carreira_ok', 'field_obs': 'tempo_carreira_obs',
         'value_ok': elegibilidade.tempo_carreira_ok if elegibilidade else None,
         'value_obs': elegibilidade.tempo_carreira_obs if elegibilidade else ''},
        {'label': 'Tempo no cargo (quando exigido pela lei municipal)',
         'field_ok': 'tempo_no_cargo_ok', 'field_obs': 'tempo_no_cargo_obs',
         'value_ok': elegibilidade.tempo_no_cargo_ok if elegibilidade else None,
         'value_obs': elegibilidade.tempo_no_cargo_obs if elegibilidade else ''},
        {'label': 'Marco temporal de ingresso no serviço público',
         'field_ok': 'marco_temporal_ok', 'field_obs': 'marco_temporal_obs',
         'value_ok': elegibilidade.marco_temporal_ok if elegibilidade else None,
         'value_obs': elegibilidade.marco_temporal_obs if elegibilidade else '',
         'marco_temporal_ingresso': dados_beneficio.marco_temporal_ingresso if dados_beneficio else None},
    ]

    # ── Linhas dinâmicas de conformidade de cálculo ────────────────────────
    tipo_beneficio = processo.tipo_beneficio
    regime = dados_beneficio.regime_reajuste if dados_beneficio else None

    def _row(label, field_ok, field_obs, nao_informado=False):
        val = getattr(calculo, field_ok, None) if calculo else None
        return {
            'label': label,
            'field_ok': field_ok, 'field_obs': field_obs,
            'value_ok': val,
            'value_obs': getattr(calculo, field_obs, '') if calculo else '',
            'nao_informado': nao_informado and val is None,
        }

    teto_row = _row('Teto remuneratório e acumulação verificados',
                    'teto_acumulacao_ok', 'teto_acumulacao_obs', nao_informado=True)

    if tipo_beneficio == 'PENSAO_MORTE':
        situacao_inst = calculo.situacao_instituidor_pensao if calculo else ''
        if situacao_inst == 'APOSENTADO':
            base_label = 'Base de cálculo correta — último contracheque do aposentado falecido'
        elif situacao_inst == 'EM_ATIVIDADE':
            base_label = 'Base de cálculo correta — última remuneração do cargo efetivo (servidor falecido em atividade)'
        else:
            base_label = 'Base de cálculo correta (informe a situação do instituidor acima)'
        calculo_rows = [
            _row(base_label, 'base_calculo_ok', 'base_calculo_obs'),
            _row('Reajuste aplicado corretamente', 'reajuste_ok', 'reajuste_obs'),
            teto_row,
        ]
    elif regime == 'MEDIA':
        reajuste_row = _row('Reajuste aplicado corretamente — índice INSS (Portaria MPS/MF)', 'reajuste_ok', 'reajuste_obs')
        reajuste_row['nota_inss'] = True
        calculo_rows = [
            _row('Média/integralidade calculada corretamente', 'media_integralidade_ok', 'media_integralidade_obs'),
            reajuste_row,
            teto_row,
        ]
    elif regime == 'PARIDADE':
        calculo_rows = [
            _row('Composição da remuneração correta', 'composicao_remuneracao_ok', 'composicao_remuneracao_obs'),
            teto_row,
        ]
    else:
        # Regime não definido ou revisão: exibe todos os itens relevantes
        calculo_rows = [
            _row('Base de cálculo correta', 'base_calculo_ok', 'base_calculo_obs'),
            _row('Composição da remuneração correta', 'composicao_remuneracao_ok', 'composicao_remuneracao_obs'),
            _row('Média/integralidade calculada corretamente', 'media_integralidade_ok', 'media_integralidade_obs'),
            _row('Reajuste aplicado corretamente', 'reajuste_ok', 'reajuste_obs'),
            teto_row,
        ]

    folha_rows = [
        {'label': 'Rubricas lançadas corretamente na folha',
         'field_ok': 'rubricas_ok', 'field_obs': 'rubricas_obs',
         'value_ok': folha.rubricas_ok if folha else None,
         'value_obs': folha.rubricas_obs if folha else ''},
        {'label': 'Reajuste aplicado corretamente na folha',
         'field_ok': 'reajuste_aplicado_ok', 'field_obs': 'reajuste_aplicado_obs',
         'value_ok': folha.reajuste_aplicado_ok if folha else None,
         'value_obs': folha.reajuste_aplicado_obs if folha else ''},
        {'label': 'Teto constitucional observado na folha',
         'field_ok': 'teto_constitucional_ok', 'field_obs': 'teto_constitucional_obs',
         'value_ok': folha.teto_constitucional_ok if folha else None,
         'value_obs': folha.teto_constitucional_obs if folha else ''},
    ]

    from processos.models import RegimeReajuste, MetodoReajuste
    from institutos.models import Instituto
    nota_tecnica = getattr(processo, 'nota_tecnica', None)

    # Tabela de reajuste para a aba de cálculo
    import json
    reajustes_qs = ReajusteINSS.objects.order_by('ano').values(
        'ano', 'vigencia', 'percentual_acima_minimo', 'percentual_piso', 'salario_minimo', 'teto_inss', 'base_legal'
    )
    reajustes_json = json.dumps([
        {
            'ano': r['ano'],
            'vigencia': r['vigencia'].strftime('%m/%Y') if r['vigencia'] else '',
            'pct': float(r['percentual_acima_minimo']),
            'pctPiso': float(r['percentual_piso']),
            'sm': float(r['salario_minimo']),
            'teto': float(r['teto_inss']),
            'legal': r['base_legal'],
        }
        for r in reajustes_qs
    ])

    # Certidões de tempo averbado para exibição na aba de elegibilidade
    from analise.auto_analise import _parse_anos
    from processos.models import _fmt_amd, _dias_para_amd
    certidoes = processo.certidoes_tempo.all()
    averbado_dias = processo.tempo_averbado_total_dias()
    averbado_display = processo.tempo_averbado_display() if averbado_dias else None
    anos_proprio = _parse_anos(dados_beneficio.tempo_contribuicao) if dados_beneficio and dados_beneficio.tempo_contribuicao else None
    total_contrib_anos = (anos_proprio or 0) + (averbado_dias / 365.0 if averbado_dias else 0)
    total_contrib_display = _fmt_amd(*_dias_para_amd(int(total_contrib_anos * 365))) if total_contrib_anos else None

    # Ano base sugerido: salvo no calculo ou derivado da data de concessão
    ano_base_sugerido = None
    if calculo and calculo.ano_base_reajuste:
        ano_base_sugerido = calculo.ano_base_reajuste
    elif processo.data_concessao:
        ano_base_sugerido = processo.data_concessao.year

    # Valor base sugerido: salvo no calculo ou valor_concedido do processo
    valor_base_sugerido = None
    if calculo and calculo.valor_base_reajuste:
        valor_base_sugerido = calculo.valor_base_reajuste
    elif dados_beneficio and dados_beneficio.valor_concedido:
        valor_base_sugerido = dados_beneficio.valor_concedido

    contracheque = getattr(processo, 'contracheque', None)
    if contracheque and contracheque.valor_vencimento:
        valor_atual_sugerido = contracheque.valor_vencimento
        ano_ref_contracheque = contracheque.mes_referencia.year
        mes_ref_contracheque = contracheque.mes_referencia.strftime('%m/%Y')
    else:
        valor_atual_sugerido = dados_beneficio.valor_pago_folha if dados_beneficio else None
        ano_ref_contracheque = None
        mes_ref_contracheque = None

    # Análise do triênio via demonstrativo (PARIDADE)
    analise_trienio = None
    if contracheque and regime == 'PARIDADE':
        analise_trienio = contracheque.analisar_trienio_demonstrativo()

    # Divergências da conferência de folha (automáticas + manuais)
    divergencias_folha = list(folha.divergencias.all()) if folha else []
    total_divergencia_maior = sum(d.valor for d in divergencias_folha if d.impacto == 'MAIOR')
    total_divergencia_menor = sum(d.valor for d in divergencias_folha if d.impacto == 'MENOR')

    return render(request, 'analise/analise.html', {
        'processo': processo,
        'aba_ativa': aba_ativa,
        'elegibilidade': elegibilidade,
        'calculo': calculo,
        'folha': folha,
        'nota_tecnica': nota_tecnica,
        'elegibilidade_rows': elegibilidade_rows,
        'calculo_rows': calculo_rows,
        'folha_rows': folha_rows,
        'resultado_choices': ResultadoAnalise.choices,
        'tipo_divergencia_choices': ConferenciaFolha.TipoDivergencia.choices,
        'classificacao_choices': AchadoAuditoria.Classificacao.choices,
        'institutos_list': Instituto.objects.filter(ativo=True).order_by('nome'),
        'reajustes_json': reajustes_json,
        'ano_base_sugerido': ano_base_sugerido,
        'valor_base_sugerido': valor_base_sugerido,
        'valor_atual_sugerido': valor_atual_sugerido,
        'tem_reajustes': bool(list(reajustes_qs)),
        'regime_reajuste_choices': RegimeReajuste.choices,
        'metodo_reajuste_choices': MetodoReajuste.choices,
        'dados_beneficio': dados_beneficio,
        'historico_reajuste': processo.historico_reajuste.all() if hasattr(processo, 'historico_reajuste') else [],
        'situacao_instituidor_pensao': calculo.situacao_instituidor_pensao if calculo else '',
        'eh_pensao': tipo_beneficio == 'PENSAO_MORTE',
        'situacao_instituidor_choices': [('EM_ATIVIDADE', 'Servidor falecido em atividade'), ('APOSENTADO', 'Aposentado falecido')],
        'contracheque': contracheque,
        'ano_ref_contracheque': ano_ref_contracheque,
        'mes_ref_contracheque': mes_ref_contracheque,
        'data_ref_folha': data_ref_folha,
        'valor_esperado': valor_esperado,
        'passos_reajuste': passos_reajuste,
        'eh_media': regime == 'MEDIA',
        'regime_paridade': regime == 'PARIDADE',
        'analise_trienio': analise_trienio,
        'divergencias_folha': divergencias_folha,
        'total_divergencia_maior': total_divergencia_maior,
        'total_divergencia_menor': total_divergencia_menor,
        'subsidio_prefeito': _get_subsidio_prefeito(processo),
        'is_procurador': 'procurador' in (processo.beneficiario.cargo or '').lower(),
        'teto_rgps_atual': ReajusteINSS.objects.order_by('-ano').values_list('teto_inss', flat=True).first(),
        'certidoes': certidoes,
        'averbado_dias': averbado_dias,
        'averbado_display': averbado_display,
        'anos_proprio': anos_proprio,
        'total_contrib_anos': round(total_contrib_anos, 2),
        'total_contrib_display': total_contrib_display,
        'analise_automatica': gerar_analise_tecnica(
            processo, elegibilidade, calculo, folha, dados_beneficio,
            valor_esperado, passos_reajuste, list(processo.achados.all()),
        ),
        'empresas': EmpresaAuditora.objects.filter(ativa=True),
    })


def pre_analise(request, processo_pk):
    """AJAX: executa pré-análise automática e retorna JSON."""
    processo = get_object_or_404(Processo.objects.select_related('beneficiario', 'dados_beneficio'), pk=processo_pk)
    regra_id = request.GET.get('regra_id')
    if not regra_id:
        return JsonResponse({'erro': 'regra_id não informado.'}, status=400)
    from institutos.models import RegraAposentadoria
    try:
        regra = RegraAposentadoria.objects.get(pk=regra_id)
    except RegraAposentadoria.DoesNotExist:
        return JsonResponse({'erro': 'Regra não encontrada.'}, status=404)

    # Vincula o instituto ao processo se ainda não estiver vinculado
    if not processo.instituto_id:
        processo.instituto = regra.instituto
        processo.save(update_fields=['instituto'])

    resultado = executar_pre_analise(processo, regra)

    # Serializa tuplas (bool|None, str) como dicts
    def serializar(secao):
        out = {}
        for k, v in secao.items():
            if isinstance(v, tuple):
                val, obs = v
                out[k] = {'valor': val, 'obs': obs}
            else:
                out[k] = v
        return out

    return JsonResponse({
        'elegibilidade': serializar(resultado['elegibilidade']),
        'calculo': serializar(resultado['calculo']),
        'folha': resultado['folha'],
    })


def excluir_achado(request, pk):
    achado = get_object_or_404(AchadoAuditoria, pk=pk)
    processo_pk = achado.processo_id
    achado.delete()
    messages.success(request, 'Achado excluído.')
    return redirect(f'/analise/{processo_pk}/?aba=achados')


def adicionar_divergencia(request, processo_pk):
    """POST: adiciona divergência manual à conferência de folha."""
    if request.method != 'POST':
        return redirect(f'/analise/{processo_pk}/?aba=folha')
    processo = get_object_or_404(Processo, pk=processo_pk)
    folha, _ = ConferenciaFolha.objects.get_or_create(processo=processo)
    tipo = request.POST.get('tipo', '').strip()
    impacto = request.POST.get('impacto', '').strip()
    descricao = request.POST.get('descricao', '').strip()
    base_legal = request.POST.get('base_legal', '').strip()
    try:
        valor = Decimal(request.POST.get('valor', '0').replace(',', '.'))
    except Exception:
        messages.error(request, 'Valor inválido.')
        return redirect(f'/analise/{processo_pk}/?aba=folha')
    if tipo not in [c[0] for c in DivergenciaFolha.Tipo.choices]:
        messages.error(request, 'Tipo de divergência inválido.')
        return redirect(f'/analise/{processo_pk}/?aba=folha')
    if impacto not in [c[0] for c in DivergenciaFolha.Impacto.choices]:
        messages.error(request, 'Impacto inválido.')
        return redirect(f'/analise/{processo_pk}/?aba=folha')
    DivergenciaFolha.objects.create(
        conferencia=folha, tipo=tipo, impacto=impacto,
        valor=valor, descricao=descricao, base_legal=base_legal,
        detectado_automaticamente=False,
    )
    from analise.utils import _recalcular_tipo_divergencia
    _recalcular_tipo_divergencia(folha)
    messages.success(request, 'Divergência registrada.')
    return redirect(f'/analise/{processo_pk}/?aba=folha')


def excluir_divergencia(request, pk):
    """POST: remove divergência manual da conferência de folha."""
    div = get_object_or_404(DivergenciaFolha, pk=pk)
    if div.detectado_automaticamente:
        messages.error(request, 'Divergências automáticas não podem ser removidas manualmente.')
        return redirect(f'/analise/{div.conferencia.processo_id}/?aba=folha')
    processo_pk = div.conferencia.processo_id
    folha = div.conferencia
    div.delete()
    from analise.utils import _recalcular_tipo_divergencia
    _recalcular_tipo_divergencia(folha)
    messages.success(request, 'Divergência removida.')
    return redirect(f'/analise/{processo_pk}/?aba=folha')


def gerar_achados_automaticos(request, processo_pk):
    """POST: gera AchadoAuditoria a partir das DivergenciaFolha pendentes de um processo."""
    if request.method != 'POST':
        return redirect(f'/analise/{processo_pk}/?aba=achados')
    processo = get_object_or_404(
        Processo.objects.select_related(
            'dados_beneficio', 'contracheque', 'instituto', 'conferenciafolha'
        ), pk=processo_pk
    )
    criados = gerar_achados_de_divergencias(processo)
    if criados:
        messages.success(request, f'{criados} achado(s) gerado(s) automaticamente.')
    else:
        messages.info(request, 'Nenhuma divergência nova para converter em achado.')
    return redirect(f'/analise/{processo_pk}/?aba=achados')


def gerar_todos_achados(request):
    """POST: gera AchadoAuditoria para todos os processos com divergências pendentes."""
    from analise.models import DivergenciaFolha
    if request.method != 'POST':
        return redirect('/processos/')

    # Processos com pelo menos uma divergência não convertida
    pks = (
        DivergenciaFolha.objects
        .filter(achado_gerado=False)
        .values_list('conferencia__processo_id', flat=True)
        .distinct()
    )
    processos = Processo.objects.filter(pk__in=pks).select_related(
        'dados_beneficio', 'contracheque', 'instituto', 'conferenciafolha'
    )

    total_criados = 0
    processos_afetados = 0
    for processo in processos:
        criados = gerar_achados_de_divergencias(processo)
        if criados:
            total_criados += criados
            processos_afetados += 1

    if total_criados:
        messages.success(
            request,
            f'{total_criados} achado(s) gerado(s) automaticamente em {processos_afetados} processo(s).'
        )
    else:
        messages.info(request, 'Nenhuma divergência pendente encontrada.')
    return redirect('/processos/')


def nota_tecnica_pdf(request, processo_pk):
    """Gera PDF da nota técnica do processo."""
    from weasyprint import HTML
    import io
    from datetime import date
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    processo = get_object_or_404(
        Processo.objects.select_related(
            'beneficiario', 'lote', 'instituto',
            'analiseelegibilidade', 'analisecalculo', 'conferenciafolha',
            'nota_tecnica', 'dados_beneficio', 'contracheque',
        ).prefetch_related('achados'),
        pk=processo_pk
    )
    nota = getattr(processo, 'nota_tecnica', None)

    recalcular_conferencia(processo)
    dados_beneficio = getattr(processo, 'dados_beneficio', None)
    valor_esperado, passos_reajuste = calcular_valor_esperado(processo)
    calculo_obj = getattr(processo, 'analisecalculo', None)
    if valor_esperado is None and dados_beneficio and dados_beneficio.regime_reajuste == 'PARIDADE':
        if calculo_obj and calculo_obj.valor_devido_mes_corrente:
            valor_esperado = calculo_obj.valor_devido_mes_corrente
        elif calculo_obj and calculo_obj.valor_reconstruido_ano:
            valor_esperado = calculo_obj.valor_reconstruido_ano

    eleg_obj  = getattr(processo, 'analiseelegibilidade', None)
    folha_obj = getattr(processo, 'conferenciafolha', None)
    achados_list = list(processo.achados.all())
    divergencias_pdf = list(folha_obj.divergencias.all()) if folha_obj else []
    eid = request.POST.get('empresa_auditora') or request.GET.get('empresa_auditora')
    if eid:
        empresa_auditora = EmpresaAuditora.objects.filter(pk=eid, ativa=True).first()
    else:
        empresa_auditora = (
            processo.instituto.empresa_auditora if processo.instituto else None
        ) or EmpresaAuditora.objects.filter(ativa=True).first()
    logo_base64 = None
    if empresa_auditora and empresa_auditora.logo:
        try:
            import base64
            with open(empresa_auditora.logo.path, 'rb') as _f:
                _data = base64.b64encode(_f.read()).decode('ascii')
            _ext = empresa_auditora.logo.name.rsplit('.', 1)[-1].lower()
            _mime = 'image/png' if _ext == 'png' else 'image/jpeg'
            logo_base64 = f'data:{_mime};base64,{_data}'
        except Exception:
            pass
    ctx = {
        'processo': processo,
        'nota': nota,
        'elegibilidade': eleg_obj,
        'calculo': calculo_obj,
        'folha': folha_obj,
        'dados_beneficio': dados_beneficio,
        'valor_esperado': valor_esperado,
        'passos_reajuste': passos_reajuste,
        'achados': achados_list,
        'divergencias_folha': divergencias_pdf,
        'empresa_auditora': empresa_auditora,
        'logo_base64': logo_base64,
        'data_geracao': date.today().strftime('%d/%m/%Y'),
        'analise_automatica': gerar_analise_tecnica(
            processo, eleg_obj, calculo_obj, folha_obj, dados_beneficio,
            valor_esperado, passos_reajuste, achados_list,
        ),
    }
    html = render_to_string('analise/nota_tecnica_pdf.html', ctx)
    buf = io.BytesIO()
    HTML(string=html).write_pdf(buf)
    response = HttpResponse(buf.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="nota_tecnica_{processo.numero}.pdf"'
    return response


def _atualizar_status_processo(processo):
    """Atualiza status do processo baseado nas análises realizadas."""
    from processos.models import StatusProcesso
    tem_analise = (
        hasattr(processo, 'analiseelegibilidade') or
        hasattr(processo, 'analisecalculo') or
        hasattr(processo, 'conferenciafolha')
    )

    elegibilidade = getattr(processo, 'analiseelegibilidade', None)
    calculo = getattr(processo, 'analisecalculo', None)
    folha = getattr(processo, 'conferenciafolha', None)
    todas_ok = elegibilidade and calculo and folha

    if todas_ok:
        processo.status_processo = StatusProcesso.CONCLUIDO
    elif tem_analise:
        processo.status_processo = StatusProcesso.EM_ANALISE
    processo.save(update_fields=['status_processo'])
