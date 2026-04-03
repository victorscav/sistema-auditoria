from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse

from .models import Instituto, RegraAposentadoria
from processos.models import TipoBeneficio


def lista_institutos(request):
    institutos = Instituto.objects.prefetch_related('regras').all()
    return render(request, 'institutos/lista.html', {'institutos': institutos})


def detalhe_instituto(request, pk):
    instituto = get_object_or_404(Instituto.objects.prefetch_related('regras'), pk=pk)
    regras_municipais = instituto.regras.filter(norma_federal=False)
    regras_federais = (
        RegraAposentadoria.objects.filter(norma_federal=True, ativa=True)
        .order_by('tipo_beneficio', 'vigente_desde')
        if not instituto.aderiu_ec103_2019 else RegraAposentadoria.objects.none()
    )
    return render(request, 'institutos/detalhe.html', {
        'instituto': instituto,
        'regras_municipais': regras_municipais,
        'regras_federais': regras_federais,
    })


def novo_instituto(request):
    if request.method == 'POST':
        instituto = Instituto(
            nome=request.POST.get('nome', '').strip(),
            cnpj=request.POST.get('cnpj', '').strip(),
            estado=request.POST.get('estado', '').strip().upper(),
            municipio=request.POST.get('municipio', '').strip(),
            lei_organica=request.POST.get('lei_organica', '').strip(),
            ativo=request.POST.get('ativo') == 'on',
            aderiu_ec103_2019=request.POST.get('aderiu_ec103_2019') == 'on',
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        instituto.save()
        messages.success(request, f'Instituto "{instituto.nome}" criado com sucesso.')
        return redirect('institutos:detalhe', pk=instituto.pk)
    return render(request, 'institutos/form_instituto.html', {'acao': 'Novo'})


def editar_instituto(request, pk):
    instituto = get_object_or_404(Instituto, pk=pk)
    if request.method == 'POST':
        instituto.nome = request.POST.get('nome', '').strip()
        instituto.cnpj = request.POST.get('cnpj', '').strip()
        instituto.estado = request.POST.get('estado', '').strip().upper()
        instituto.municipio = request.POST.get('municipio', '').strip()
        instituto.lei_organica = request.POST.get('lei_organica', '').strip()
        instituto.ativo = request.POST.get('ativo') == 'on'
        instituto.aderiu_ec103_2019 = request.POST.get('aderiu_ec103_2019') == 'on'
        instituto.observacoes = request.POST.get('observacoes', '').strip()
        instituto.save()
        messages.success(request, 'Instituto atualizado.')
        return redirect('institutos:detalhe', pk=instituto.pk)
    return render(request, 'institutos/form_instituto.html', {'acao': 'Editar', 'instituto': instituto})


def nova_regra(request, instituto_pk):
    instituto = get_object_or_404(Instituto, pk=instituto_pk)
    if request.method == 'POST':
        def _int(v):
            try:
                return int(v) if v else None
            except (ValueError, TypeError):
                return None

        def _dec(v):
            try:
                return float(v.replace(',', '.')) if v else None
            except (ValueError, TypeError):
                return None

        def _bool_or_none(v):
            if v == 'true':
                return True
            if v == 'false':
                return False
            return None

        regra = RegraAposentadoria(
            instituto=instituto,
            tipo_beneficio=request.POST.get('tipo_beneficio'),
            norma_base=request.POST.get('norma_base', '').strip(),
            vigente_desde=request.POST.get('vigente_desde'),
            vigente_ate=request.POST.get('vigente_ate') or None,
            ativa=request.POST.get('ativa') == 'on',
            idade_minima_homem=_int(request.POST.get('idade_minima_homem')),
            idade_minima_mulher=_int(request.POST.get('idade_minima_mulher')),
            tempo_contribuicao_homem=_int(request.POST.get('tempo_contribuicao_homem')),
            tempo_contribuicao_mulher=_int(request.POST.get('tempo_contribuicao_mulher')),
            tempo_servico_publico=_int(request.POST.get('tempo_servico_publico')),
            tempo_carreira=_int(request.POST.get('tempo_carreira')),
            tempo_no_cargo=_int(request.POST.get('tempo_no_cargo')),
            integralidade=_bool_or_none(request.POST.get('integralidade')),
            proporcionalidade_formula=request.POST.get('proporcionalidade_formula', '').strip(),
            teto_remuneratorio=_dec(request.POST.get('teto_remuneratorio')),
            criterio_reajuste=request.POST.get('criterio_reajuste', '').strip(),
            cota_inicial_percentual=_dec(request.POST.get('cota_inicial_percentual')),
            cota_por_dependente_percentual=_dec(request.POST.get('cota_por_dependente_percentual')),
            reversibilidade=_bool_or_none(request.POST.get('reversibilidade')),
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        regra.save()
        messages.success(request, 'Regra criada com sucesso.')
        return redirect('institutos:detalhe', pk=instituto_pk)
    return render(request, 'institutos/form_regra.html', {
        'acao': 'Nova',
        'instituto': instituto,
        'tipo_beneficio_choices': TipoBeneficio.choices,
    })


def editar_regra(request, pk):
    regra = get_object_or_404(RegraAposentadoria, pk=pk)
    if request.method == 'POST':
        def _int(v):
            try:
                return int(v) if v else None
            except (ValueError, TypeError):
                return None

        def _dec(v):
            try:
                return float(v.replace(',', '.')) if v else None
            except (ValueError, TypeError):
                return None

        def _bool_or_none(v):
            if v == 'true':
                return True
            if v == 'false':
                return False
            return None

        regra.tipo_beneficio = request.POST.get('tipo_beneficio')
        regra.norma_base = request.POST.get('norma_base', '').strip()
        regra.vigente_desde = request.POST.get('vigente_desde')
        regra.vigente_ate = request.POST.get('vigente_ate') or None
        regra.ativa = request.POST.get('ativa') == 'on'
        regra.idade_minima_homem = _int(request.POST.get('idade_minima_homem'))
        regra.idade_minima_mulher = _int(request.POST.get('idade_minima_mulher'))
        regra.tempo_contribuicao_homem = _int(request.POST.get('tempo_contribuicao_homem'))
        regra.tempo_contribuicao_mulher = _int(request.POST.get('tempo_contribuicao_mulher'))
        regra.tempo_servico_publico = _int(request.POST.get('tempo_servico_publico'))
        regra.tempo_carreira = _int(request.POST.get('tempo_carreira'))
        regra.tempo_no_cargo = _int(request.POST.get('tempo_no_cargo'))
        regra.integralidade = _bool_or_none(request.POST.get('integralidade'))
        regra.proporcionalidade_formula = request.POST.get('proporcionalidade_formula', '').strip()
        regra.teto_remuneratorio = _dec(request.POST.get('teto_remuneratorio'))
        regra.criterio_reajuste = request.POST.get('criterio_reajuste', '').strip()
        regra.cota_inicial_percentual = _dec(request.POST.get('cota_inicial_percentual'))
        regra.cota_por_dependente_percentual = _dec(request.POST.get('cota_por_dependente_percentual'))
        regra.reversibilidade = _bool_or_none(request.POST.get('reversibilidade'))
        regra.observacoes = request.POST.get('observacoes', '').strip()
        regra.save()
        messages.success(request, 'Regra atualizada.')
        return redirect('institutos:detalhe', pk=regra.instituto_id)
    return render(request, 'institutos/form_regra.html', {
        'acao': 'Editar',
        'instituto': regra.instituto,
        'regra': regra,
        'tipo_beneficio_choices': TipoBeneficio.choices,
    })


def regras_por_tipo(request):
    """AJAX: retorna regras de um instituto filtradas por tipo_beneficio."""
    instituto_id = request.GET.get('instituto_id')
    tipo = request.GET.get('tipo_beneficio')
    if not instituto_id:
        return JsonResponse({'regras': []})
    qs = RegraAposentadoria.objects.filter(instituto_id=instituto_id, ativa=True)
    if tipo:
        qs = qs.filter(tipo_beneficio=tipo)
    data = [{'id': r.pk, 'label': str(r)} for r in qs]
    return JsonResponse({'regras': data})
