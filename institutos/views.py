from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse

from .models import Instituto, RegraAposentadoria, LeiMunicipalReajuste, EmpresaAuditora
from processos.models import TipoBeneficio


def lista_institutos(request):
    institutos = Instituto.objects.prefetch_related('regras').all()
    return render(request, 'institutos/lista.html', {'institutos': institutos})


def detalhe_instituto(request, pk):
    instituto = get_object_or_404(Instituto.objects.prefetch_related('regras', 'leis_reajuste'), pk=pk)
    regras_municipais = instituto.regras.filter(norma_federal=False)
    regras_federais = (
        instituto.regras.filter(norma_federal=True, ativa=True)
        .order_by('tipo_beneficio', 'vigente_desde')
        if not instituto.aderiu_ec103_2019 else RegraAposentadoria.objects.none()
    )
    leis_municipais = instituto.leis_reajuste.all()
    return render(request, 'institutos/detalhe.html', {
        'instituto': instituto,
        'regras_municipais': regras_municipais,
        'regras_federais': regras_federais,
        'leis_municipais': leis_municipais,
    })


def novo_instituto(request):
    if request.method == 'POST':
        def _dec(v):
            try:
                return float(str(v).replace(',', '.')) if v else None
            except (ValueError, TypeError):
                return None

        instituto = Instituto(
            nome=request.POST.get('nome', '').strip(),
            cnpj=request.POST.get('cnpj', '').strip(),
            estado=request.POST.get('estado', '').strip().upper(),
            municipio=request.POST.get('municipio', '').strip(),
            lei_organica=request.POST.get('lei_organica', '').strip(),
            ativo=request.POST.get('ativo') == 'on',
            aderiu_ec103_2019=request.POST.get('aderiu_ec103_2019') == 'on',
            subsidio_prefeito=_dec(request.POST.get('subsidio_prefeito')),
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        if 'logo' in request.FILES:
            instituto.logo = request.FILES['logo']
        instituto.save()
        messages.success(request, f'Instituto "{instituto.nome}" criado com sucesso.')
        return redirect('institutos:detalhe', pk=instituto.pk)
    return render(request, 'institutos/form_instituto.html', {'acao': 'Novo'})


def editar_instituto(request, pk):
    instituto = get_object_or_404(Instituto, pk=pk)
    if request.method == 'POST':
        def _dec(v):
            try:
                return float(str(v).replace(',', '.')) if v else None
            except (ValueError, TypeError):
                return None

        instituto.nome = request.POST.get('nome', '').strip()
        instituto.cnpj = request.POST.get('cnpj', '').strip()
        instituto.estado = request.POST.get('estado', '').strip().upper()
        instituto.municipio = request.POST.get('municipio', '').strip()
        instituto.lei_organica = request.POST.get('lei_organica', '').strip()
        instituto.ativo = request.POST.get('ativo') == 'on'
        instituto.aderiu_ec103_2019 = request.POST.get('aderiu_ec103_2019') == 'on'
        instituto.subsidio_prefeito = _dec(request.POST.get('subsidio_prefeito'))
        instituto.observacoes = request.POST.get('observacoes', '').strip()
        if 'logo' in request.FILES:
            if instituto.logo:
                instituto.logo.delete(save=False)
            instituto.logo = request.FILES['logo']
        elif request.POST.get('remover_logo') == '1' and instituto.logo:
            instituto.logo.delete(save=False)
            instituto.logo = None
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


def nova_lei(request, instituto_pk):
    instituto = get_object_or_404(Instituto, pk=instituto_pk)
    if request.method == 'POST':
        def _dec(v):
            try:
                return float(str(v).replace(',', '.')) if v else None
            except (ValueError, TypeError):
                return None

        lei = LeiMunicipalReajuste(
            instituto=instituto,
            numero=request.POST.get('numero', '').strip(),
            descricao=request.POST.get('descricao', '').strip(),
            data_publicacao=request.POST.get('data_publicacao'),
            data_vigencia=request.POST.get('data_vigencia'),
            percentual=_dec(request.POST.get('percentual')),
            base_indice=request.POST.get('base_indice', '').strip(),
            base_legal=request.POST.get('base_legal', '').strip(),
            aplica_inativos=request.POST.get('aplica_inativos') == 'on',
            aplica_pensoes=request.POST.get('aplica_pensoes') == 'on',
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        if 'arquivo' in request.FILES:
            lei.arquivo = request.FILES['arquivo']
        lei.save()
        messages.success(request, f'Lei nº {lei.numero} cadastrada com sucesso.')
        return redirect('institutos:detalhe', pk=instituto_pk)
    return render(request, 'institutos/form_lei.html', {'acao': 'Nova', 'instituto': instituto})


def editar_lei(request, pk):
    lei = get_object_or_404(LeiMunicipalReajuste, pk=pk)
    if request.method == 'POST':
        def _dec(v):
            try:
                return float(str(v).replace(',', '.')) if v else None
            except (ValueError, TypeError):
                return None

        lei.numero = request.POST.get('numero', '').strip()
        lei.descricao = request.POST.get('descricao', '').strip()
        lei.data_publicacao = request.POST.get('data_publicacao')
        lei.data_vigencia = request.POST.get('data_vigencia')
        lei.percentual = _dec(request.POST.get('percentual'))
        lei.base_indice = request.POST.get('base_indice', '').strip()
        lei.base_legal = request.POST.get('base_legal', '').strip()
        lei.aplica_inativos = request.POST.get('aplica_inativos') == 'on'
        lei.aplica_pensoes = request.POST.get('aplica_pensoes') == 'on'
        lei.observacoes = request.POST.get('observacoes', '').strip()
        if 'arquivo' in request.FILES:
            lei.arquivo = request.FILES['arquivo']
        lei.save()
        messages.success(request, 'Lei atualizada.')
        return redirect('institutos:detalhe', pk=lei.instituto_id)
    return render(request, 'institutos/form_lei.html', {'acao': 'Editar', 'lei': lei, 'instituto': lei.instituto})


def excluir_lei(request, pk):
    lei = get_object_or_404(LeiMunicipalReajuste, pk=pk)
    instituto_pk = lei.instituto_id
    lei.delete()
    messages.success(request, 'Lei excluída.')
    return redirect('institutos:detalhe', pk=instituto_pk)


def lista_empresas(request):
    empresas = EmpresaAuditora.objects.all()
    return render(request, 'institutos/empresas.html', {'empresas': empresas})


def nova_empresa(request):
    if request.method == 'POST':
        nome  = request.POST.get('nome', '').strip()
        sigla = request.POST.get('sigla', '').strip()
        cnpj  = request.POST.get('cnpj', '').strip()
        ativa = request.POST.get('ativa') == 'on'
        empresa = EmpresaAuditora(nome=nome, sigla=sigla, cnpj=cnpj, ativa=ativa)
        if 'logo' in request.FILES:
            empresa.logo = request.FILES['logo']
        empresa.save()
        messages.success(request, f'Empresa "{empresa}" cadastrada.')
        return redirect('institutos:empresas')
    return render(request, 'institutos/empresa_form.html', {})


def editar_empresa(request, pk):
    empresa = get_object_or_404(EmpresaAuditora, pk=pk)
    if request.method == 'POST':
        empresa.nome  = request.POST.get('nome', '').strip()
        empresa.sigla = request.POST.get('sigla', '').strip()
        empresa.cnpj  = request.POST.get('cnpj', '').strip()
        empresa.ativa = request.POST.get('ativa') == 'on'
        if 'logo' in request.FILES:
            if empresa.logo:
                empresa.logo.delete(save=False)
            empresa.logo = request.FILES['logo']
        elif request.POST.get('remover_logo') == '1' and empresa.logo:
            empresa.logo.delete(save=False)
            empresa.logo = None
        empresa.save()
        messages.success(request, f'Empresa "{empresa}" atualizada.')
        return redirect('institutos:empresas')
    return render(request, 'institutos/empresa_form.html', {'empresa': empresa})


def excluir_empresa(request, pk):
    empresa = get_object_or_404(EmpresaAuditora, pk=pk)
    if request.method == 'POST':
        nome = str(empresa)
        if empresa.logo:
            empresa.logo.delete(save=False)
        empresa.delete()
        messages.success(request, f'Empresa "{nome}" excluída.')
    return redirect('institutos:empresas')


_TIPOS_EQUIVALENTES = {
    'APOS_VOLUNTARIA_IDADE_TC': ['APOS_VOLUNTARIA_IDADE_TC', 'APOS_VOLUNTARIA', 'APOS_VOLUNTARIA_PROP'],
    'APOS_VOLUNTARIA':          ['APOS_VOLUNTARIA', 'APOS_VOLUNTARIA_IDADE_TC'],
    'APOS_VOLUNTARIA_PROP':     ['APOS_VOLUNTARIA_PROP', 'APOS_VOLUNTARIA_IDADE_TC'],
    'APOS_VOLUNTARIA_POR_IDADE':['APOS_VOLUNTARIA_POR_IDADE', 'APOS_VOLUNTARIA_PROP_IDADE', 'APOS_VOLUNTARIA_PROP'],
    'APOS_VOLUNTARIA_PROP_IDADE':['APOS_VOLUNTARIA_PROP_IDADE', 'APOS_VOLUNTARIA_POR_IDADE', 'APOS_VOLUNTARIA_PROP'],
    'APOS_INCAPACIDADE':        ['APOS_INCAPACIDADE', 'APOS_INVALIDEZ_PERMANENTE'],
    'APOS_INVALIDEZ_PERMANENTE':['APOS_INVALIDEZ_PERMANENTE', 'APOS_INCAPACIDADE'],
}


def regras_por_tipo(request):
    """AJAX: retorna regras de um instituto filtradas por tipo_beneficio."""
    instituto_id  = request.GET.get('instituto_id')
    tipo          = request.GET.get('tipo_beneficio')
    regime_req    = request.GET.get('regime_reajuste', '')   # PARIDADE | MEDIA | ''
    if not instituto_id:
        return JsonResponse({'regras': []})

    try:
        instituto = Instituto.objects.get(pk=instituto_id)
    except Instituto.DoesNotExist:
        return JsonResponse({'regras': []})

    qs = RegraAposentadoria.objects.filter(instituto_id=instituto_id, ativa=True)
    if tipo:
        tipos_busca = _TIPOS_EQUIVALENTES.get(tipo, [tipo])
        qs = qs.filter(tipo_beneficio__in=tipos_busca)

    regras = list(qs)

    # Regras compatíveis com o regime do processo ficam no topo.
    # PARIDADE → criterio_reajuste contém "PARIDADE"; MEDIA → contém índice (INPC/IPCA/INSS).
    def _regime_score(r):
        cr = (r.criterio_reajuste or '').upper()
        if regime_req == 'PARIDADE':
            return 0 if 'PARIDADE' in cr else 1
        if regime_req == 'MEDIA':
            return 0 if 'PARIDADE' not in cr else 1
        return 0  # sem preferência

    # Institutos que não aderiram à EC 103/2019 seguem as normas federais anteriores
    # (EC 47/2005, EC 41/2003, CF/88). Essas normas têm prioridade na seleção automática,
    # mas match exato de tipo e compatibilidade de regime vêm antes de equivalência/federal.
    if not instituto.aderiu_ec103_2019:
        regras.sort(key=lambda r: (
            0 if r.tipo_beneficio == tipo else 1,  # match exato antes de equivalentes
            _regime_score(r),                       # regra compatível com regime do processo
            0 if r.norma_federal else 1,            # federais antes de municipais
            -(r.vigente_desde.toordinal()),         # mais recente primeiro
        ))

    data = [{'id': r.pk, 'label': str(r), 'federal': r.norma_federal} for r in regras]
    return JsonResponse({'regras': data, 'aderiu_ec103': instituto.aderiu_ec103_2019})
