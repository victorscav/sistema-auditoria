import io
import base64
from datetime import date
from django.shortcuts import render
from django.http import HttpResponse
from django.template.loader import render_to_string

from processos.models import Processo, Lote, TipoBeneficio
from analise.models import ConferenciaFolha, ResultadoAnalise, AchadoAuditoria
from analise.utils import recalcular_conferencia
from institutos.models import RegraAposentadoria, EmpresaAuditora


def _logo_base64(empresa):
    """Retorna data URI do logo da empresa, ou None se não houver."""
    if not empresa or not empresa.logo:
        return None
    try:
        with open(empresa.logo.path, 'rb') as f:
            data = base64.b64encode(f.read()).decode('ascii')
        ext = empresa.logo.name.rsplit('.', 1)[-1].lower()
        mime = 'image/png' if ext == 'png' else 'image/jpeg'
        return f'data:{mime};base64,{data}'
    except Exception:
        return None


def _get_empresa(request):
    """Resolve a empresa auditora a partir do POST ou do único registro ativo."""
    eid = request.POST.get('empresa_auditora') or request.GET.get('empresa_auditora')
    if eid:
        return EmpresaAuditora.objects.filter(pk=eid, ativa=True).first()
    return EmpresaAuditora.objects.filter(ativa=True).first()


def _fundamentacao_combinada(achado):
    """
    Combina normas_aplicaveis do achado com a norma_base da regra municipal
    ativa do instituto/tipo_beneficio do processo.
    Retorna a string de fundamentação legal completa para o relatório.
    """
    norma = achado.normas_aplicaveis or ''
    processo = achado.processo
    if not processo.instituto_id:
        return norma
    regra = (
        RegraAposentadoria.objects
        .filter(
            instituto_id=processo.instituto_id,
            tipo_beneficio=processo.tipo_beneficio,
            norma_federal=False,
            ativa=True,
        )
        .order_by('-vigente_desde')
        .first()
    )
    if regra:
        combinada = f'{norma} c/c {regra.norma_base}' if norma else regra.norma_base
    else:
        combinada = norma
    return combinada


# ── PDF helper ───────────────────────────────────────────────────────────────

def _render_pdf(template_name, context):
    """Renderiza template HTML como PDF e retorna bytes."""
    from weasyprint import HTML
    html = render_to_string(template_name, context)
    buf = io.BytesIO()
    HTML(string=html).write_pdf(buf)
    return buf.getvalue()


def _pdf_response(pdf_bytes, filename):
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Shared helpers ────────────────────────────────────────────────────────────

def _lote_filter(request, qs, field='lote_id'):
    lote_id = request.POST.get('lote') or None
    if lote_id:
        qs = qs.filter(**{field: lote_id})
    return qs, lote_id


def _lote_label(lote_id):
    if not lote_id:
        return 'Todos os lotes'
    try:
        return Lote.objects.get(pk=lote_id).numero
    except Lote.DoesNotExist:
        return '—'


def _instituto_nome(processos_qs):
    p = processos_qs.select_related('instituto').filter(instituto__isnull=False).first()
    if p and p.instituto:
        return p.instituto.nome
    return ''


_RESULTADO_LABELS = {
    'CONFORME':     'Conforme',
    'RESSALVAS':    'Conforme com Ressalvas',
    'NAO_CONFORME': 'Não Conforme',
    'INDETERMINADO':'Indeterminado',
}

def _resultado(p):
    return p.get_resultado_analise() or 'PENDENTE'

def _resultado_display(p):
    return _RESULTADO_LABELS.get(p.get_resultado_analise(), 'Pendente')


def _stats(processos):
    n_c = sum(1 for p in processos if p.get_resultado_analise() == 'CONFORME')
    n_r = sum(1 for p in processos if p.get_resultado_analise() == 'RESSALVAS')
    n_nc = sum(1 for p in processos if p.get_resultado_analise() == 'NAO_CONFORME')
    n_p = sum(1 for p in processos if p.get_resultado_analise() is None)
    total = len(processos)
    perc = round(n_c / total * 100, 1) if total else 0
    return total, n_c, n_r, n_nc, n_p, perc


# ── Index view ────────────────────────────────────────────────────────────────

def index(request):
    processos = Processo.objects.all()
    conformes = sum(1 for p in processos if p.get_resultado_analise() == 'CONFORME')
    ressalvas = sum(1 for p in processos if p.get_resultado_analise() == 'RESSALVAS')
    nao_conformes = sum(1 for p in processos if p.get_resultado_analise() == 'NAO_CONFORME')
    pendentes = sum(1 for p in processos if p.get_resultado_analise() is None)
    divergencias = ConferenciaFolha.objects.exclude(tipo_divergencia='SEM_DIVERGENCIA').count()

    stats = {
        'total': processos.count(),
        'conformes': conformes,
        'ressalvas': ressalvas,
        'nao_conformes': nao_conformes,
        'pendentes': pendentes,
        'divergencias': divergencias,
    }

    return render(request, 'relatorios/index.html', {
        'lotes': Lote.objects.all(),
        'empresas': EmpresaAuditora.objects.filter(ativa=True),
        'stats': stats,
    })


# ── 1. Planilha Analítica ─────────────────────────────────────────────────────

def relatorio_analitico(request):
    qs = Processo.objects.select_related(
        'beneficiario', 'lote', 'instituto',
        'analiseelegibilidade', 'analisecalculo', 'conferenciafolha', 'dados_beneficio',
        'contracheque',
    )
    qs, lote_id = _lote_filter(request, qs)
    processos = list(qs)
    for p in processos:
        recalcular_conferencia(p)
    total, n_c, n_r, n_nc, n_p, perc = _stats(processos)

    empresa = _get_empresa(request)
    ctx = {
        'processos': processos,
        'lote_label': _lote_label(lote_id),
        'data_geracao': date.today().strftime('%d/%m/%Y'),
        'n_conformes': n_c,
        'n_ressalvas': n_r,
        'n_nao_conformes': n_nc,
        'n_pendentes': n_p,
        'instituto_nome': _instituto_nome(qs),
        'empresa_auditora': empresa,
        'logo_base64': _logo_base64(empresa),
    }
    return _pdf_response(_render_pdf('relatorios/pdf_analitico.html', ctx), 'planilha_analitica.pdf')


# ── 2. Divergências Financeiras ───────────────────────────────────────────────

def relatorio_divergencias(request):
    lote_id = request.POST.get('lote') or None
    # Recalcula todos os processos do lote antes de filtrar divergências
    proc_qs = Processo.objects.select_related(
        'dados_beneficio', 'conferenciafolha', 'contracheque', 'instituto',
    )
    if lote_id:
        proc_qs = proc_qs.filter(lote_id=lote_id)
    for p in proc_qs:
        recalcular_conferencia(p)

    qs = ConferenciaFolha.objects.exclude(
        tipo_divergencia='SEM_DIVERGENCIA'
    ).select_related('processo__beneficiario', 'processo__lote', 'auditor')
    if lote_id:
        qs = qs.filter(processo__lote_id=lote_id)

    divergencias = list(qs)
    total_impacto = sum(
        float(f.impacto_financeiro_estimado) for f in divergencias
        if f.impacto_financeiro_estimado
    )

    inst_qs = Processo.objects.filter(lote_id=lote_id) if lote_id else Processo.objects.all()
    empresa = _get_empresa(request)
    ctx = {
        'divergencias': divergencias,
        'total_impacto': round(total_impacto, 2),
        'lote_label': _lote_label(lote_id),
        'data_geracao': date.today().strftime('%d/%m/%Y'),
        'instituto_nome': _instituto_nome(inst_qs),
        'empresa_auditora': empresa,
        'logo_base64': _logo_base64(empresa),
    }
    return _pdf_response(_render_pdf('relatorios/pdf_divergencias.html', ctx), 'divergencias_financeiras.pdf')


# ── 3. Indicadores de Conformidade ───────────────────────────────────────────

def relatorio_indicadores(request):
    qs = Processo.objects.select_related('beneficiario', 'lote')
    qs, lote_id = _lote_filter(request, qs)
    processos = list(qs)
    total, n_c, n_r, n_nc, n_p, perc = _stats(processos)

    por_tipo = []
    for tipo_val, tipo_label in TipoBeneficio.choices:
        sub = [p for p in processos if p.tipo_beneficio == tipo_val]
        t = len(sub)
        if t == 0:
            continue
        c = sum(1 for p in sub if p.get_resultado_analise() == 'CONFORME')
        r = sum(1 for p in sub if p.get_resultado_analise() == 'RESSALVAS')
        nc = sum(1 for p in sub if p.get_resultado_analise() == 'NAO_CONFORME')
        pe = sum(1 for p in sub if p.get_resultado_analise() is None)
        por_tipo.append({
            'label': tipo_label, 'total': t,
            'conformes': c, 'ressalvas': r, 'nao_conformes': nc, 'pendentes': pe,
            'perc': round(c / t * 100, 1),
        })

    # por lote (só quando exibindo todos)
    por_lote = []
    if not lote_id:
        for lote in Lote.objects.all():
            sub = [p for p in processos if p.lote_id == lote.pk]
            t = len(sub)
            if t == 0:
                continue
            c = sum(1 for p in sub if p.get_resultado_analise() == 'CONFORME')
            r = sum(1 for p in sub if p.get_resultado_analise() == 'RESSALVAS')
            nc = sum(1 for p in sub if p.get_resultado_analise() == 'NAO_CONFORME')
            por_lote.append({
                'numero': lote.numero, 'total': t,
                'conformes': c, 'ressalvas': r, 'nao_conformes': nc,
                'perc': round(c / t * 100, 1),
            })

    empresa = _get_empresa(request)
    ctx = {
        'total': total, 'n_conformes': n_c, 'n_ressalvas': n_r,
        'n_nao_conformes': n_nc, 'n_pendentes': n_p, 'perc_conformidade': perc,
        'por_tipo': por_tipo, 'por_lote': por_lote,
        'lote_label': _lote_label(lote_id),
        'data_geracao': date.today().strftime('%d/%m/%Y'),
        'instituto_nome': _instituto_nome(qs),
        'empresa_auditora': empresa,
        'logo_base64': _logo_base64(empresa),
    }
    return _pdf_response(_render_pdf('relatorios/pdf_indicadores.html', ctx), 'indicadores_conformidade.pdf')


# ── 4. Conferência da Folha de Inativos ──────────────────────────────────────

def relatorio_folha_inativos(request):
    qs = Processo.objects.select_related(
        'beneficiario', 'lote', 'instituto',
        'conferenciafolha', 'dados_beneficio', 'contracheque',
    ).prefetch_related('achados')
    qs, lote_id = _lote_filter(request, qs)

    rows = []
    for p in qs:
        recalcular_conferencia(p)
        folha = getattr(p, 'conferenciafolha', None)
        dados = getattr(p, 'dados_beneficio', None)
        div = folha.divergencia_valor if folha else None
        recomendacoes = '; '.join(a.recomendacao for a in p.achados.all() if a.recomendacao)
        rows.append({
            'obj': p,
            'folha': folha,
            'dados': dados,
            'divergencia_valor': round(float(div), 2) if div is not None else None,
            'tem_divergencia': bool(folha and folha.tipo_divergencia != 'SEM_DIVERGENCIA'),
            'resultado': _resultado(p),
            'resultado_display': _resultado_display(p),
            'recomendacoes': recomendacoes,
        })

    empresa = _get_empresa(request)
    ctx = {
        'processos': rows,
        'has_recomendacoes': any(r['recomendacoes'] for r in rows),
        'lote_label': _lote_label(lote_id),
        'data_geracao': date.today().strftime('%d/%m/%Y'),
        'instituto_nome': _instituto_nome(qs),
        'empresa_auditora': empresa,
        'logo_base64': _logo_base64(empresa),
    }
    return _pdf_response(_render_pdf('relatorios/pdf_folha_inativos.html', ctx), 'conferencia_folha_inativos.pdf')


# ── 5. Recomendações Técnicas ─────────────────────────────────────────────────

def relatorio_recomendacoes(request):
    qs = AchadoAuditoria.objects.select_related(
        'processo__beneficiario', 'processo__lote', 'processo__instituto'
    ).order_by('processo__numero', '-data_registro')
    lote_id = request.POST.get('lote') or None
    if lote_id:
        qs = qs.filter(processo__lote_id=lote_id)

    achados = list(qs)
    for a in achados:
        a.fundamentacao_combinada = _fundamentacao_combinada(a)

    inst_qs = Processo.objects.filter(lote_id=lote_id) if lote_id else Processo.objects.all()
    empresa = _get_empresa(request)
    ctx = {
        'achados': achados,
        'lote_label': _lote_label(lote_id),
        'data_geracao': date.today().strftime('%d/%m/%Y'),
        'instituto_nome': _instituto_nome(inst_qs),
        'empresa_auditora': empresa,
        'logo_base64': _logo_base64(empresa),
    }
    return _pdf_response(_render_pdf('relatorios/pdf_recomendacoes.html', ctx), 'recomendacoes_tecnicas.pdf')


# ── 6. Relatório Final Consolidado por Lote ───────────────────────────────────

def relatorio_final_lote(request):
    lote_id = request.POST.get('lote') or None
    lote = None
    if lote_id:
        try:
            lote = Lote.objects.get(pk=lote_id)
        except Lote.DoesNotExist:
            pass

    qs = Processo.objects.select_related(
        'beneficiario', 'lote', 'instituto',
        'analiseelegibilidade', 'analisecalculo', 'conferenciafolha', 'dados_beneficio',
        'contracheque',
    ).prefetch_related('achados')
    if lote:
        qs = qs.filter(lote=lote)

    processos_raw = list(qs)
    for p in processos_raw:
        recalcular_conferencia(p)
    total, n_c, n_r, n_nc, n_p, perc = _stats(processos_raw)

    # Processos enriquecidos para templates
    processos = []
    for p in processos_raw:
        processos.append({
            'obj': p,
            'eleg': getattr(p, 'analiseelegibilidade', None),
            'calc': getattr(p, 'analisecalculo', None),
            'folha': getattr(p, 'conferenciafolha', None),
            'dados': getattr(p, 'dados_beneficio', None),
            'resultado': _resultado(p),
            'resultado_display': _resultado_display(p),
        })

    divergencias = [
        p.conferenciafolha for p in processos_raw
        if getattr(p, 'conferenciafolha', None) and
           p.conferenciafolha.tipo_divergencia != 'SEM_DIVERGENCIA'
    ]
    total_impacto = round(sum(
        float(f.impacto_financeiro_estimado) for f in divergencias
        if f.impacto_financeiro_estimado
    ), 2)

    achados_qs = AchadoAuditoria.objects.select_related(
        'processo__beneficiario', 'processo__lote', 'processo__instituto'
    ).filter(processo__in=processos_raw).order_by('processo__numero')
    achados = list(achados_qs)
    for a in achados:
        a.fundamentacao_combinada = _fundamentacao_combinada(a)

    lote_label = lote.numero if lote else 'Todos os lotes'

    empresa = _get_empresa(request)
    ctx = {
        'lote': lote,
        'lote_label': lote_label,
        'data_geracao': date.today().strftime('%d/%m/%Y'),
        'total': total,
        'n_conformes': n_c, 'n_ressalvas': n_r,
        'n_nao_conformes': n_nc, 'n_pendentes': n_p,
        'perc_conformidade': perc,
        'n_divergencias': len(divergencias),
        'total_impacto': total_impacto,
        'total_achados': len(achados),
        'n_achados_nc': sum(1 for a in achados if a.classificacao == 'NAO_CONFORME'),
        'n_achados_rec': sum(1 for a in achados if a.recomendacao),
        'processos': processos,
        'divergencias': divergencias,
        'achados': list(achados),
        'instituto_nome': _instituto_nome(qs),
        'empresa_auditora': empresa,
        'logo_base64': _logo_base64(empresa),
    }
    fname = f"relatorio_final_{lote_label.replace('/', '-')}.pdf"
    return _pdf_response(_render_pdf('relatorios/pdf_final_lote.html', ctx), fname)
