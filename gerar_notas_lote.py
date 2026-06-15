"""
Gera notas técnicas em PDF para todos os processos CONCLUÍDOS
do lote 2025-2026 de Mangaratiba.

Uso:
    python gerar_notas_lote.py
    python gerar_notas_lote.py --lote "2025-2026"
    python gerar_notas_lote.py --municipio "Mangaratiba"
    python gerar_notas_lote.py --saida "C:/minha/pasta"
"""
import sys
import os
import io
import base64
import argparse
from datetime import date
from pathlib import Path

# ─── Setup Django ────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sistema_auditoria.settings')

import django
django.setup()

# ─── Imports após setup ───────────────────────────────────────────────────────
from django.template.loader import render_to_string
from weasyprint import HTML

from processos.models import Processo, StatusProcesso
from analise.models import NotaTecnica
from analise.utils import calcular_valor_esperado, recalcular_conferencia, gerar_analise_tecnica
from institutos.models import EmpresaAuditora


def nome_arquivo_seguro(texto: str) -> str:
    """Remove/substitui caracteres inválidos para nome de arquivo."""
    for c in r'\/:*?"<>|':
        texto = texto.replace(c, '_')
    return texto.strip()


def gerar_pdf_processo(processo) -> bytes:
    """Replica a lógica da view nota_tecnica_pdf sem precisar de request."""
    nota = getattr(processo, 'nota_tecnica', None)

    recalcular_conferencia(processo)
    dados_beneficio = getattr(processo, 'dados_beneficio', None)
    valor_esperado, passos_reajuste = calcular_valor_esperado(processo)
    calculo_obj = getattr(processo, 'analisecalculo', None)
    if valor_esperado is None and dados_beneficio and getattr(dados_beneficio, 'regime_reajuste', None) == 'PARIDADE':
        if calculo_obj and calculo_obj.valor_devido_mes_corrente:
            valor_esperado = calculo_obj.valor_devido_mes_corrente
        elif calculo_obj and calculo_obj.valor_reconstruido_ano:
            valor_esperado = calculo_obj.valor_reconstruido_ano

    eleg_obj  = getattr(processo, 'analiseelegibilidade', None)
    folha_obj = getattr(processo, 'conferenciafolha', None)
    achados_list    = list(processo.achados.all())
    divergencias_pdf = list(folha_obj.divergencias.all()) if folha_obj else []

    empresa_auditora = (
        processo.instituto.empresa_auditora if processo.instituto else None
    ) or EmpresaAuditora.objects.filter(ativa=True).first()

    logo_base64 = None
    if empresa_auditora and empresa_auditora.logo:
        try:
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
    return buf.getvalue()


def main():
    parser = argparse.ArgumentParser(description='Gera notas técnicas PDF em lote')
    parser.add_argument('--lote',      default='2025-2026', help='Número (parcial) do lote')
    parser.add_argument('--municipio', default='Mangaratiba', help='Filtro por município do beneficiário (parcial, ignora case)')
    parser.add_argument('--saida',     default=None, help='Pasta de destino (padrão: notas_pdf/ ao lado deste script)')
    args = parser.parse_args()

    pasta_saida = Path(args.saida) if args.saida else BASE_DIR / 'notas_tecnicas_mangaratiba'
    pasta_saida.mkdir(parents=True, exist_ok=True)

    # ─── Busca processos ──────────────────────────────────────────────────────
    qs = (
        Processo.objects
        .select_related(
            'beneficiario', 'lote', 'instituto',
            'analiseelegibilidade', 'analisecalculo', 'conferenciafolha',
            'nota_tecnica', 'dados_beneficio', 'contracheque',
        )
        .prefetch_related('achados')
        .filter(status_processo=StatusProcesso.CONCLUIDO)
    )

    if args.lote:
        qs = qs.filter(lote__numero__icontains=args.lote)

    if args.municipio:
        qs = qs.filter(beneficiario__municipio__icontains=args.municipio)

    total = qs.count()
    if total == 0:
        print(f'\n[!] Nenhum processo encontrado com lote "{args.lote}" e município "{args.municipio}" com status CONCLUÍDO.')
        print('    Verifique os filtros ou rode sem --municipio para ver todos do lote.')
        return

    print(f'\n{"─"*60}')
    print(f'  Lote filtrado : {args.lote}')
    print(f'  Município     : {args.municipio}')
    print(f'  Status        : CONCLUÍDO')
    print(f'  Total         : {total} processo(s)')
    print(f'  Destino       : {pasta_saida}')
    print(f'{"─"*60}\n')

    ok = 0
    erros = []
    for i, proc in enumerate(qs, 1):
        nome_benef = nome_arquivo_seguro(proc.beneficiario.nome)
        num_proc   = nome_arquivo_seguro(proc.numero)

        pasta_pessoa = pasta_saida / nome_benef
        pasta_pessoa.mkdir(parents=True, exist_ok=True)

        filename = f'nota_tecnica_{num_proc}.pdf'
        caminho  = pasta_pessoa / filename

        try:
            pdf_bytes = gerar_pdf_processo(proc)
            caminho.write_bytes(pdf_bytes)
            print(f'  [{i:02d}/{total:02d}] OK  →  {nome_benef}/{filename}')
            ok += 1
        except Exception as e:
            msg = f'  [{i:02d}/{total:02d}] ERRO — {proc.numero} ({proc.beneficiario.nome}): {e}'
            print(msg)
            erros.append(msg)

    print(f'\n{"─"*60}')
    print(f'  Gerados com sucesso : {ok}')
    if erros:
        print(f'  Com erro            : {len(erros)}')
        for e in erros:
            print(f'    {e}')
    print(f'  Pasta de saída      : {pasta_saida}')
    print(f'{"─"*60}\n')


if __name__ == '__main__':
    main()
