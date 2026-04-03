from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse

from processos.models import Processo, ReajusteINSS
from .models import (
    AnaliseElegibilidade, AnaliseCalculo, ConferenciaFolha,
    AchadoAuditoria, ResultadoAnalise, NotaTecnica
)
from .auto_analise import executar_pre_analise


def _parse_bool(value):
    if value == 'true':
        return True
    if value == 'false':
        return False
    return None


def analise(request, processo_pk):
    processo = get_object_or_404(Processo.objects.select_related('beneficiario'), pk=processo_pk)
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
            def safe_decimal(v):
                if not v:
                    return None
                try:
                    return float(v.replace(',', '.'))
                except Exception:
                    return None

            fields = {
                'valor_concedido': safe_decimal(request.POST.get('valor_concedido')),
                'valor_pago_folha': safe_decimal(request.POST.get('valor_pago_folha')),
                'rubricas_ok': _parse_bool(request.POST.get('rubricas_ok')),
                'rubricas_obs': request.POST.get('rubricas_obs', ''),
                'reajuste_aplicado_ok': _parse_bool(request.POST.get('reajuste_aplicado_ok')),
                'reajuste_aplicado_obs': request.POST.get('reajuste_aplicado_obs', ''),
                'teto_constitucional_ok': _parse_bool(request.POST.get('teto_constitucional_ok')),
                'teto_constitucional_obs': request.POST.get('teto_constitucional_obs', ''),
                'tipo_divergencia': request.POST.get('tipo_divergencia', 'SEM_DIVERGENCIA'),
                'impacto_financeiro_estimado': safe_decimal(request.POST.get('impacto_financeiro_estimado')),
                'resultado': request.POST.get('resultado', ResultadoAnalise.INDETERMINADO),
                'auditor': request.user if request.user.is_authenticated else None,
            }
            ConferenciaFolha.objects.update_or_create(processo=processo, defaults=fields)
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
         'value_obs': elegibilidade.marco_temporal_obs if elegibilidade else ''},
    ]

    calculo_rows = [
        {'label': 'Base de cálculo correta',
         'field_ok': 'base_calculo_ok', 'field_obs': 'base_calculo_obs',
         'value_ok': calculo.base_calculo_ok if calculo else None,
         'value_obs': calculo.base_calculo_obs if calculo else ''},
        {'label': 'Composição da remuneração correta',
         'field_ok': 'composicao_remuneracao_ok', 'field_obs': 'composicao_remuneracao_obs',
         'value_ok': calculo.composicao_remuneracao_ok if calculo else None,
         'value_obs': calculo.composicao_remuneracao_obs if calculo else ''},
        {'label': 'Média/integralidade calculada corretamente',
         'field_ok': 'media_integralidade_ok', 'field_obs': 'media_integralidade_obs',
         'value_ok': calculo.media_integralidade_ok if calculo else None,
         'value_obs': calculo.media_integralidade_obs if calculo else ''},
        {'label': 'Cotas familiares corretas (pensões)',
         'field_ok': 'cotas_familiares_ok', 'field_obs': 'cotas_familiares_obs',
         'value_ok': calculo.cotas_familiares_ok if calculo else None,
         'value_obs': calculo.cotas_familiares_obs if calculo else ''},
        {'label': 'Teto/acumulação verificado',
         'field_ok': 'teto_acumulacao_ok', 'field_obs': 'teto_acumulacao_obs',
         'value_ok': calculo.teto_acumulacao_ok if calculo else None,
         'value_obs': calculo.teto_acumulacao_obs if calculo else ''},
        {'label': 'Reajuste aplicado corretamente',
         'field_ok': 'reajuste_ok', 'field_obs': 'reajuste_obs',
         'value_ok': calculo.reajuste_ok if calculo else None,
         'value_obs': calculo.reajuste_obs if calculo else ''},
        {'label': 'Redutor aplicado corretamente (quando cabível)',
         'field_ok': 'redutor_ok', 'field_obs': 'redutor_obs',
         'value_ok': calculo.redutor_ok if calculo else None,
         'value_obs': calculo.redutor_obs if calculo else ''},
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
        'ano', 'percentual_acima_minimo', 'percentual_piso', 'salario_minimo', 'teto_inss', 'base_legal'
    )
    reajustes_json = json.dumps([
        {
            'ano': r['ano'],
            'pct': float(r['percentual_acima_minimo']),
            'pctPiso': float(r['percentual_piso']),
            'sm': float(r['salario_minimo']),
            'teto': float(r['teto_inss']),
            'legal': r['base_legal'],
        }
        for r in reajustes_qs
    ])

    dados_beneficio = getattr(processo, 'dados_beneficio', None)

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

    valor_atual_sugerido = dados_beneficio.valor_pago_folha if dados_beneficio else None

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
        'certidoes': certidoes,
        'averbado_dias': averbado_dias,
        'averbado_display': averbado_display,
        'anos_proprio': anos_proprio,
        'total_contrib_anos': round(total_contrib_anos, 2),
        'total_contrib_display': total_contrib_display,
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


def nota_tecnica_pdf(request, processo_pk):
    """Gera PDF da nota técnica do processo."""
    from xhtml2pdf import pisa
    import io
    from datetime import date
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    processo = get_object_or_404(
        Processo.objects.select_related(
            'beneficiario', 'lote', 'instituto',
            'analiseelegibilidade', 'analisecalculo', 'conferenciafolha', 'nota_tecnica'
        ).prefetch_related('achados'),
        pk=processo_pk
    )
    nota = getattr(processo, 'nota_tecnica', None)

    ctx = {
        'processo': processo,
        'nota': nota,
        'elegibilidade': getattr(processo, 'analiseelegibilidade', None),
        'calculo': getattr(processo, 'analisecalculo', None),
        'folha': getattr(processo, 'conferenciafolha', None),
        'achados': processo.achados.all(),
        'data_geracao': date.today().strftime('%d/%m/%Y'),
    }
    html = render_to_string('analise/nota_tecnica_pdf.html', ctx)
    buf = io.BytesIO()
    pisa.CreatePDF(io.StringIO(html), dest=buf)
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
