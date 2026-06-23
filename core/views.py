import json
from django.shortcuts import render
from django.db.models import Count
from processos.models import Processo, Lote, StatusProcesso, TipoBeneficio
from analise.models import AchadoAuditoria, ResultadoAnalise


def dashboard(request):
    total_processos = Processo.objects.count()
    total_analisados = Processo.objects.filter(status_processo=StatusProcesso.CONCLUIDO).count()
    total_pendentes = Processo.objects.filter(status_processo=StatusProcesso.PENDENTE).count()

    # Carrega todos os processos com seus relacionamentos em uma única query
    todos_processos = Processo.objects.prefetch_related(
        'analiseelegibilidade', 'analisecalculo', 'conferenciafolha'
    )

    # Grafico por tipo de beneficio
    tipo_counts = Processo.objects.values('tipo_beneficio').annotate(total=Count('id'))
    tipo_labels = []
    tipo_values = []
    for item in tipo_counts:
        tipo_labels.append(dict(TipoBeneficio.choices).get(item['tipo_beneficio'], item['tipo_beneficio']))
        tipo_values.append(item['total'])

    dados_grafico_beneficio = json.dumps({'labels': tipo_labels, 'values': tipo_values})

    # Grafico conformidade — percorre apenas uma vez, sem queries adicionais
    conf_labels = ['Conforme', 'Com Ressalvas', 'Não Conforme', 'Indeterminado']
    conf_values = [0, 0, 0, 0]
    total_nao_conformes = 0
    for p in todos_processos:
        r = p.get_resultado_analise()
        if r == 'CONFORME':
            conf_values[0] += 1
        elif r == 'RESSALVAS':
            conf_values[1] += 1
        elif r == 'NAO_CONFORME':
            conf_values[2] += 1
            total_nao_conformes += 1
        elif r is None:
            conf_values[3] += 1

    dados_grafico_conformidade = json.dumps({'labels': conf_labels, 'values': conf_values})

    lotes_ativos = Lote.objects.exclude(status='CONCLUIDO')[:5]
    ultimos_processos = Processo.objects.select_related('beneficiario').order_by('-data_cadastro')[:10]

    return render(request, 'core/dashboard.html', {
        'total_processos': total_processos,
        'total_analisados': total_analisados,
        'total_pendentes': total_pendentes,
        'total_nao_conformes': total_nao_conformes,
        'dados_grafico_beneficio': dados_grafico_beneficio,
        'dados_grafico_conformidade': dados_grafico_conformidade,
        'lotes_ativos': lotes_ativos,
        'ultimos_processos': ultimos_processos,
    })
