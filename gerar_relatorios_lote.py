# -*- coding: utf-8 -*-
"""
Gera todos os relatórios e notas técnicas do lote Mangaratiba,
salvando tudo em uma pasta com a data de geração.
"""
import sys, os, io
from datetime import date
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_auditoria.settings')

import django
django.setup()

from pypdf import PdfWriter

from processos.models import Processo, Lote, TipoBeneficio
from analise.models import ConferenciaFolha, AchadoAuditoria
from analise.utils import recalcular_conferencia
from institutos.models import EmpresaAuditora
from relatorios.views import (
    _render_pdf, _instituto_nome, _stats,
    _resultado, _resultado_display, _logo_base64, _fundamentacao_combinada,
)

# Importa a função de nota técnica já existente
from gerar_notas_lote import gerar_pdf_processo


# ── Pasta de saída ────────────────────────────────────────────────────────────
from datetime import datetime as _dt
hoje_fmt = date.today().strftime('%d/%m/%Y')
hoje     = _dt.now().strftime('%Y%m%d_%H%M')
PASTA    = BASE_DIR / f'relatorios_mangaratiba_{hoje}'
PASTA.mkdir(parents=True, exist_ok=True)
print(f'\nPasta de saída: {PASTA}\n{"─"*60}')


# ── Busca lote e empresa ──────────────────────────────────────────────────────
lote = Lote.objects.filter(
    numero__icontains='2025-2026',
    processo__beneficiario__municipio__icontains='Mangaratiba',
).distinct().first()

if not lote:
    print('[ERRO] Lote Mangaratiba 2025-2026 não encontrado.')
    sys.exit(1)

lote_id  = lote.pk
empresa  = EmpresaAuditora.objects.filter(ativa=True).first()
logo_b64 = _logo_base64(empresa)
lab      = lote.numero

print(f'Lote    : {lab}  (id={lote_id})')
print(f'Empresa : {empresa.nome if empresa else "—"}')


# ── Helper ────────────────────────────────────────────────────────────────────
def salvar(nome, template, ctx):
    caminho = PASTA / nome
    pdf = _render_pdf(template, ctx)
    caminho.write_bytes(pdf)
    print(f'  OK  {nome:<55} ({len(pdf)//1024:>4} KB)')


# Base queryset reutilizado nos relatórios
QS_BASE = Processo.objects.select_related(
    'beneficiario', 'lote', 'instituto',
    'analiseelegibilidade', 'analisecalculo', 'conferenciafolha',
    'dados_beneficio', 'contracheque',
).prefetch_related('achados').filter(lote_id=lote_id)


# ─────────────────────────────────────────────────────────────────────────────
# 1. PLANILHA ANALÍTICA
# ─────────────────────────────────────────────────────────────────────────────
print('\n[1/6] Planilha Analítica...')
processos1 = list(QS_BASE)
for p in processos1:
    recalcular_conferencia(p)
total, n_c, n_r, n_nc, n_p, perc = _stats(processos1)
salvar('01_planilha_analitica.pdf', 'relatorios/pdf_analitico.html', {
    'processos': processos1,
    'lote_label': lab,
    'data_geracao': hoje_fmt,
    'n_conformes': n_c, 'n_ressalvas': n_r,
    'n_nao_conformes': n_nc, 'n_pendentes': n_p,
    'instituto_nome': _instituto_nome(QS_BASE),
    'empresa_auditora': empresa,
    'logo_base64': logo_b64,
})


# ─────────────────────────────────────────────────────────────────────────────
# 2. DIVERGÊNCIAS FINANCEIRAS
# ─────────────────────────────────────────────────────────────────────────────
print('\n[2/6] Divergências Financeiras...')
divs_qs = (
    ConferenciaFolha.objects
    .exclude(tipo_divergencia='SEM_DIVERGENCIA')
    .select_related('processo__beneficiario', 'processo__lote', 'auditor')
    .filter(processo__lote_id=lote_id)
)
divergencias = list(divs_qs)
total_impacto = round(sum(
    float(f.impacto_financeiro_estimado)
    for f in divergencias if f.impacto_financeiro_estimado
), 2)
salvar('02_divergencias_financeiras.pdf', 'relatorios/pdf_divergencias.html', {
    'divergencias': divergencias,
    'total_impacto': total_impacto,
    'lote_label': lab,
    'data_geracao': hoje_fmt,
    'instituto_nome': _instituto_nome(QS_BASE),
    'empresa_auditora': empresa,
    'logo_base64': logo_b64,
})


# ─────────────────────────────────────────────────────────────────────────────
# 3. INDICADORES DE CONFORMIDADE
# ─────────────────────────────────────────────────────────────────────────────
print('\n[3/6] Indicadores de Conformidade...')
por_tipo = []
for tipo_val, tipo_label in TipoBeneficio.choices:
    sub = [p for p in processos1 if p.tipo_beneficio == tipo_val]
    t = len(sub)
    if not t:
        continue
    c  = sum(1 for p in sub if p.get_resultado_analise() == 'CONFORME')
    r  = sum(1 for p in sub if p.get_resultado_analise() == 'RESSALVAS')
    nc = sum(1 for p in sub if p.get_resultado_analise() == 'NAO_CONFORME')
    pe = sum(1 for p in sub if p.get_resultado_analise() is None)
    por_tipo.append({'label': tipo_label, 'total': t, 'conformes': c,
                     'ressalvas': r, 'nao_conformes': nc, 'pendentes': pe,
                     'perc': round(c / t * 100, 1)})
salvar('03_indicadores_conformidade.pdf', 'relatorios/pdf_indicadores.html', {
    'total': total, 'n_conformes': n_c, 'n_ressalvas': n_r,
    'n_nao_conformes': n_nc, 'n_pendentes': n_p, 'perc_conformidade': perc,
    'por_tipo': por_tipo, 'por_lote': [],
    'lote_label': lab,
    'data_geracao': hoje_fmt,
    'instituto_nome': _instituto_nome(QS_BASE),
    'empresa_auditora': empresa,
    'logo_base64': logo_b64,
})


# ─────────────────────────────────────────────────────────────────────────────
# 4. CONFERÊNCIA DA FOLHA DE INATIVOS
# ─────────────────────────────────────────────────────────────────────────────
print('\n[4/6] Conferência da Folha de Inativos...')
rows = []
for p in processos1:
    folha = getattr(p, 'conferenciafolha', None)
    dados = getattr(p, 'dados_beneficio', None)
    div   = folha.divergencia_valor if folha else None
    rows.append({
        'obj': p, 'folha': folha, 'dados': dados,
        'divergencia_valor': round(float(div), 2) if div is not None else None,
        'tem_divergencia': bool(folha and folha.tipo_divergencia != 'SEM_DIVERGENCIA'),
        'resultado': _resultado(p),
        'resultado_display': _resultado_display(p),
        'recomendacoes': '; '.join(a.recomendacao for a in p.achados.all() if a.recomendacao),
    })
salvar('04_conferencia_folha_inativos.pdf', 'relatorios/pdf_folha_inativos.html', {
    'processos': rows,
    'has_recomendacoes': any(r['recomendacoes'] for r in rows),
    'lote_label': lab,
    'data_geracao': hoje_fmt,
    'instituto_nome': _instituto_nome(QS_BASE),
    'empresa_auditora': empresa,
    'logo_base64': logo_b64,
})


# ─────────────────────────────────────────────────────────────────────────────
# 5. RECOMENDAÇÕES TÉCNICAS
# ─────────────────────────────────────────────────────────────────────────────
print('\n[5/6] Recomendações Técnicas...')
achados_qs = AchadoAuditoria.objects.select_related(
    'processo__beneficiario', 'processo__lote', 'processo__instituto'
).filter(processo__lote_id=lote_id).order_by('processo__numero', '-data_registro')
achados = list(achados_qs)
for a in achados:
    a.fundamentacao_combinada = _fundamentacao_combinada(a)
salvar('05_recomendacoes_tecnicas.pdf', 'relatorios/pdf_recomendacoes.html', {
    'achados': achados,
    'lote_label': lab,
    'data_geracao': hoje_fmt,
    'instituto_nome': _instituto_nome(QS_BASE),
    'empresa_auditora': empresa,
    'logo_base64': logo_b64,
})


# ─────────────────────────────────────────────────────────────────────────────
# 6. RELATÓRIO FINAL DO LOTE
# ─────────────────────────────────────────────────────────────────────────────
print('\n[6/6] Relatório Final do Lote...')
processos6 = [{
    'obj': p,
    'eleg': getattr(p, 'analiseelegibilidade', None),
    'calc': getattr(p, 'analisecalculo', None),
    'folha': getattr(p, 'conferenciafolha', None),
    'dados': getattr(p, 'dados_beneficio', None),
    'resultado': _resultado(p),
    'resultado_display': _resultado_display(p),
} for p in processos1]
divs6 = [p.conferenciafolha for p in processos1
         if getattr(p, 'conferenciafolha', None)
         and p.conferenciafolha.tipo_divergencia != 'SEM_DIVERGENCIA']
total_impacto6 = round(sum(
    float(f.impacto_financeiro_estimado) for f in divs6 if f.impacto_financeiro_estimado
), 2)
achados6_qs = AchadoAuditoria.objects.select_related(
    'processo__beneficiario', 'processo__lote', 'processo__instituto'
).filter(processo__lote_id=lote_id).order_by('processo__numero')
achados6 = list(achados6_qs)
for a in achados6:
    a.fundamentacao_combinada = _fundamentacao_combinada(a)
label_file = lab.replace('/', '-')
salvar(f'06_relatorio_final_{label_file}.pdf', 'relatorios/pdf_final_lote.html', {
    'lote': lote, 'lote_label': lab,
    'data_geracao': hoje_fmt,
    'total': total, 'n_conformes': n_c, 'n_ressalvas': n_r,
    'n_nao_conformes': n_nc, 'n_pendentes': n_p, 'perc_conformidade': perc,
    'n_divergencias': len(divs6), 'total_impacto': total_impacto6,
    'total_achados': len(achados6),
    'n_achados_nc': sum(1 for a in achados6 if a.classificacao == 'NAO_CONFORME'),
    'n_achados_rec': sum(1 for a in achados6 if a.recomendacao),
    'processos': processos6, 'divergencias': divs6, 'achados': achados6,
    'instituto_nome': _instituto_nome(QS_BASE),
    'empresa_auditora': empresa,
    'logo_base64': logo_b64,
})


# ─────────────────────────────────────────────────────────────────────────────
# NOTAS TÉCNICAS — gera individualmente e consolida em um único PDF
# ─────────────────────────────────────────────────────────────────────────────
print('\n[Notas] Gerando notas técnicas...')
qs_notas = (
    Processo.objects
    .select_related(
        'beneficiario', 'lote', 'instituto',
        'analiseelegibilidade', 'analisecalculo', 'conferenciafolha',
        'nota_tecnica', 'dados_beneficio', 'contracheque',
    )
    .prefetch_related('achados')
    .filter(lote_id=lote_id)
    .order_by('numero')
)

writer = PdfWriter()
ok = 0
erros = []
total_notas = qs_notas.count()

for i, proc in enumerate(qs_notas, 1):
    try:
        pdf_bytes = gerar_pdf_processo(proc)
        writer.append(io.BytesIO(pdf_bytes))
        print(f'  [{i:02d}/{total_notas}] OK  {proc.numero} — {proc.beneficiario.nome}')
        ok += 1
    except Exception as e:
        msg = f'[{i:02d}/{total_notas}] ERRO {proc.numero}: {e}'
        print(f'  {msg}')
        erros.append(msg)

consolidado = PASTA / 'notas_tecnicas_consolidadas.pdf'
with open(consolidado, 'wb') as f:
    writer.write(f)
sz = consolidado.stat().st_size // 1024
print(f'\n  Consolidado: notas_tecnicas_consolidadas.pdf  ({sz} KB)')


# ── Resumo final ──────────────────────────────────────────────────────────────
print(f'\n{"─"*60}')
print(f'  Relatórios gerados  : 6')
print(f'  Notas técnicas      : {ok}/{total_notas}' + (f'  ({len(erros)} erro(s))' if erros else ''))
if erros:
    for e in erros:
        print(f'    {e}')
print(f'\n  Arquivos na pasta:')
for a in sorted(PASTA.glob('*.pdf')):
    print(f'    {a.name:<55} {a.stat().st_size//1024:>5} KB')
print(f'\n  Pasta: {PASTA}')
print(f'{"─"*60}\n')
