import re
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.http import HttpResponse

from .models import (Processo, Beneficiario, DadosBeneficio, Lote, TipoBeneficio,
                      StatusProcesso, StatusLote, ReajusteINSS, ContrachequeAuditoria,
                      RegimeReajuste, CertidaoTempoContribuicao, OrigemTempo,
                      ContribuicaoPrevidenciaria, DocumentoProcesso, TipoDocumento,
                      _dias_para_amd)
from .pdf_extractor import processar_pdfs, extrair_dados_contracheque
from .excel_utils import gerar_planilha_padronizada, ler_planilha_padronizada
from analise.utils import recalcular_conferencia


def _parse_date_field(value):
    if not value:
        return None
    value = str(value).strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M:%S'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value).date()
    except (ValueError, TypeError):
        return None


def lista_processos(request):
    qs = Processo.objects.select_related('beneficiario', 'lote').order_by('-data_cadastro')

    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(
            Q(numero__icontains=q) |
            Q(beneficiario__nome__icontains=q) |
            Q(beneficiario__cpf__icontains=q)
        )

    tipo = request.GET.get('tipo', '')
    if tipo:
        qs = qs.filter(tipo_beneficio=tipo)

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status_processo=status)

    lote_id = request.GET.get('lote', '')
    if lote_id:
        qs = qs.filter(lote_id=lote_id)

    paginator = Paginator(qs, 50)
    page = request.GET.get('page', 1)
    processos = paginator.get_page(page)

    from analise.models import DivergenciaFolha
    divergencias_pendentes = DivergenciaFolha.objects.filter(achado_gerado=False).count()

    return render(request, 'processos/lista.html', {
        'processos': processos,
        'tipos_beneficio': TipoBeneficio.choices,
        'status_choices': StatusProcesso.choices,
        'lotes': Lote.objects.all(),
        'divergencias_pendentes': divergencias_pendentes,
    })


def detalhe_processo(request, pk):
    processo = get_object_or_404(Processo.objects.select_related('beneficiario', 'lote', 'contracheque', 'dados_beneficio'), pk=pk)
    dados = getattr(processo, 'dados_beneficio', None)
    contracheque = getattr(processo, 'contracheque', None)
    regime = dados.regime_reajuste if dados else RegimeReajuste.NAO_DEFINIDO
    tabelas_inss = list(ReajusteINSS.objects.order_by('-ano').values(
        'ano', 'vigencia', 'percentual_acima_minimo', 'percentual_piso',
        'salario_minimo', 'teto_inss', 'base_legal'
    ))
    certidoes = processo.certidoes_tempo.all()
    total_averbado_dias = processo.tempo_averbado_total_dias()
    total_averbado_display = processo.tempo_averbado_display()

    # Contribuições previdenciárias (regime MÉDIA)
    contribuicoes = processo.contribuicoes.order_by('competencia')
    media_simples = processo.media_contribuicoes_simples()
    media_80 = processo.media_contribuicoes_80()

    documentos = processo.documentos.all()

    return render(request, 'processos/detalhe.html', {
        'processo': processo,
        'contracheque': contracheque,
        'regime': regime,
        'regime_media': regime == RegimeReajuste.MEDIA,
        'regime_paridade': regime == RegimeReajuste.PARIDADE,
        'instituto': processo.instituto,
        'tabelas_inss': tabelas_inss,
        'solicitar_contracheque': contracheque is None,
        'certidoes': certidoes,
        'total_averbado_dias': total_averbado_dias,
        'total_averbado_display': total_averbado_display,
        'origem_choices': OrigemTempo.choices,
        'contribuicoes': contribuicoes,
        'media_simples': media_simples,
        'media_80': media_80,
        'documentos': documentos,
        'tipo_documento_choices': TipoDocumento.choices,
    })


def salvar_contracheque(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    if request.method != 'POST':
        return redirect('processos:detalhe', pk=pk)

    def _dec(v):
        try:
            return float(str(v).replace(',', '.')) if v else None
        except (ValueError, TypeError):
            return None

    mes_ref_raw = request.POST.get('mes_referencia') or ''
    if not mes_ref_raw:
        messages.error(request, 'Informe o mês de referência do contracheque.')
        return redirect('processos:detalhe', pk=pk)
    # input type="month" envia YYYY-MM; DateField precisa de YYYY-MM-DD
    if len(mes_ref_raw) == 7:
        mes_ref = mes_ref_raw + '-01'
    else:
        mes_ref = mes_ref_raw

    ContrachequeAuditoria.objects.update_or_create(
        processo=processo,
        defaults={
            'mes_referencia': mes_ref,
            'valor_vencimento': _dec(request.POST.get('valor_vencimento')),
            'ultima_remuneracao_cargo': _dec(request.POST.get('ultima_remuneracao_cargo')),
            'vencimento_base_paradigma': _dec(request.POST.get('vencimento_base_paradigma')),
            'percentual_trienio': _dec(request.POST.get('percentual_trienio')),
            'lei_reajuste_municipal': request.POST.get('lei_reajuste_municipal', '').strip(),
            'percentual_reajuste_lei': _dec(request.POST.get('percentual_reajuste_lei')),
            'data_vigencia_reajuste': request.POST.get('data_vigencia_reajuste') or None,
            'observacoes': request.POST.get('observacoes', '').strip(),
        }
    )

    # Recalcula divergência de folha automaticamente após atualizar o contracheque.
    processo.refresh_from_db()
    try:
        from analise.utils import recalcular_conferencia
        recalcular_conferencia(processo, salvar=True)
    except Exception:
        pass

    messages.success(request, 'Dados do contracheque registrados. Conferência de folha recalculada.')
    return redirect('processos:detalhe', pk=pk)


def _make_input(field_type, name, value='', extra='', required=False):
    req = 'required' if required else ''
    val = str(value) if value is not None else ''
    return f'<input type="{field_type}" name="{name}" value="{val}" class="form-control form-control-sm" {extra} {req}>'


def _make_select(name, choices, current=''):
    opts = ''.join(
        '<option value="{}" {}>{}</option>'.format(
            v, 'selected' if str(v) == str(current) else '', l
        )
        for v, l in choices
    )
    return f'<select name="{name}" class="form-select form-select-sm">{opts}</select>'


def _build_form_fields(beneficiario=None, processo=None, dados=None):
    b = beneficiario

    beneficiario_fields = [
        {'label': 'Nome Completo', 'html': _make_input('text', 'nome', b.nome if b else '', required=True)},
        {'label': 'CPF', 'html': _make_input('text', 'cpf', b.cpf if b else '', required=True)},
        {'label': 'Matricula', 'html': _make_input('text', 'matricula', b.matricula if b else '')},
        {'label': 'Municipio', 'html': _make_input('text', 'municipio', b.municipio if b else '')},
        {'label': 'Cargo/Funcao', 'html': _make_input('text', 'cargo', b.cargo if b else '')},
    ]

    lote_choices = [('', '-- Sem lote --')] + [(l.pk, l.numero) for l in Lote.objects.all()]
    observacoes_val = processo.observacoes if processo else ''
    processo_fields = [
        {'label': 'Numero do Processo', 'html': _make_input('text', 'numero', processo.numero if processo else '', required=True)},
        {'label': 'Tipo de Beneficio', 'html': _make_select('tipo_beneficio', TipoBeneficio.choices, processo.tipo_beneficio if processo else '')},
        {'label': 'Status', 'html': _make_select('status_processo', StatusProcesso.choices, processo.status_processo if processo else StatusProcesso.PENDENTE)},
        {'label': 'Data de Concessao', 'html': _make_input('date', 'data_concessao', processo.data_concessao if processo else '')},
        {'label': 'Data de Publicacao', 'html': _make_input('date', 'data_publicacao', processo.data_publicacao if processo else '')},
        {'label': 'Lote', 'html': _make_select('lote', lote_choices, processo.lote_id if processo else '')},
        {'label': 'Observacoes', 'html': f'<textarea name="observacoes" class="form-control form-control-sm" rows="3">{observacoes_val}</textarea>'},
    ]

    from .models import RegimeReajuste
    regime_atual = dados.regime_reajuste if dados else RegimeReajuste.NAO_DEFINIDO
    dados_fields = [
        {'label': 'Base de Calculo (R$)', 'html': _make_input('number', 'base_calculo', dados.base_calculo if dados else '', 'step="0.01"')},
        {'label': 'Valor Concedido (R$)', 'html': _make_input('number', 'valor_concedido', dados.valor_concedido if dados else '', 'step="0.01"')},
        {'label': 'Valor Pago na Folha (R$)', 'html': _make_input('number', 'valor_pago_folha', dados.valor_pago_folha if dados else '', 'step="0.01"')},
        {'label': 'Tempo de Contribuicao', 'html': _make_input('text', 'tempo_contribuicao', dados.tempo_contribuicao if dados else '')},
        {'label': 'Tempo de Servico Publico', 'html': _make_input('text', 'tempo_servico_publico', dados.tempo_servico_publico if dados else '')},
        {'label': 'Tempo de Carreira', 'html': _make_input('text', 'tempo_carreira', dados.tempo_carreira if dados else '', 'placeholder="Ex: 10 anos e 3 meses"')},
        {'label': 'Tempo no Cargo', 'html': _make_input('text', 'tempo_no_cargo', dados.tempo_no_cargo if dados else '', 'placeholder="Ex: 5 anos e 1 mes"')},
        {'label': 'Marco Temporal de Ingresso', 'html': _make_input('date', 'marco_temporal_ingresso', dados.marco_temporal_ingresso if dados else '')},
        {'label': 'Idade na Concessao', 'html': _make_input('number', 'idade_concessao', dados.idade_concessao if dados else '')},
        {'label': 'Regra Aplicada', 'html': _make_input('text', 'regra_aplicada', dados.regra_aplicada if dados else '')},
        {'label': 'Regime de Reajuste', 'html': _make_select('regime_reajuste', RegimeReajuste.choices, regime_atual)},
    ]

    return beneficiario_fields, processo_fields, dados_fields


def _salvar_processo_from_post(request, processo_existente=None):
    cpf = request.POST.get('cpf', '').strip()
    nome = request.POST.get('nome', '').strip()
    numero = request.POST.get('numero', '').strip()

    if not cpf or not nome or not numero:
        return None, 'Campos obrigatorios: numero do processo, nome e CPF.'

    beneficiario, _ = Beneficiario.objects.get_or_create(cpf=cpf, defaults={'nome': nome})
    beneficiario.nome = nome
    beneficiario.matricula = request.POST.get('matricula', '')
    beneficiario.municipio = request.POST.get('municipio', '')
    beneficiario.cargo = request.POST.get('cargo', '')
    beneficiario.carreira = request.POST.get('carreira', '')
    beneficiario.save()

    lote_id = request.POST.get('lote') or None

    if processo_existente:
        processo = processo_existente
        processo.numero = numero
        processo.beneficiario = beneficiario
        processo.tipo_beneficio = request.POST.get('tipo_beneficio', processo.tipo_beneficio)
        processo.status_processo = request.POST.get('status_processo', processo.status_processo)
        processo.data_concessao = _parse_date_field(request.POST.get('data_concessao')) or processo.data_concessao
        processo.data_publicacao = _parse_date_field(request.POST.get('data_publicacao')) or processo.data_publicacao
        processo.lote_id = lote_id
        processo.observacoes = request.POST.get('observacoes', '')
        processo.save()
    else:
        processo, _ = Processo.objects.get_or_create(
            numero=numero,
            defaults={
                'beneficiario': beneficiario,
                'tipo_beneficio': request.POST.get('tipo_beneficio', 'APOS_VOLUNTARIA'),
                'status_processo': request.POST.get('status_processo', StatusProcesso.PENDENTE),
                'data_concessao': _parse_date_field(request.POST.get('data_concessao')),
                'data_publicacao': _parse_date_field(request.POST.get('data_publicacao')),
                'lote_id': lote_id,
                'observacoes': request.POST.get('observacoes', ''),
            }
        )

    DadosBeneficio.objects.update_or_create(
        processo=processo,
        defaults={
            'base_calculo': request.POST.get('base_calculo') or None,
            'valor_concedido': request.POST.get('valor_concedido') or None,
            'valor_pago_folha': request.POST.get('valor_pago_folha') or None,
            'tempo_contribuicao': request.POST.get('tempo_contribuicao', ''),
            'tempo_servico_publico': request.POST.get('tempo_servico_publico', ''),
            'tempo_carreira': request.POST.get('tempo_carreira', ''),
            'tempo_no_cargo': request.POST.get('tempo_no_cargo', ''),
            'marco_temporal_ingresso': _parse_date_field(request.POST.get('marco_temporal_ingresso')),
            'idade_concessao': request.POST.get('idade_concessao') or None,
            'regra_aplicada': request.POST.get('regra_aplicada', ''),
            'regime_reajuste': request.POST.get('regime_reajuste', 'NAO_DEFINIDO'),
        }
    )

    processo.refresh_from_db()
    recalcular_conferencia(processo, salvar=True)

    return processo, None


def novo_processo(request):
    if request.method == 'POST':
        processo, erro = _salvar_processo_from_post(request)
        if erro:
            messages.error(request, erro)
        else:
            messages.success(request, f'Processo {processo.numero} salvo com sucesso.')
            return redirect('processos:detalhe', pk=processo.pk)

    bf, pf, df = _build_form_fields()
    return render(request, 'processos/form_processo.html', {
        'processo': None,
        'beneficiario_form': bf,
        'processo_form': pf,
        'dados_form': df,
    })


def editar_processo(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    if request.method == 'POST':
        p, erro = _salvar_processo_from_post(request, processo_existente=processo)
        if erro:
            messages.error(request, erro)
        else:
            messages.success(request, f'Processo {p.numero} atualizado.')
            return redirect('processos:detalhe', pk=p.pk)

    dados = getattr(processo, 'dados_beneficio', None)
    bf, pf, df = _build_form_fields(processo.beneficiario, processo, dados)
    return render(request, 'processos/form_processo.html', {
        'processo': processo,
        'beneficiario_form': bf,
        'processo_form': pf,
        'dados_form': df,
    })


def excluir_processo(request, pk):
    processo = get_object_or_404(Processo, pk=pk)
    if request.method == 'POST':
        numero = processo.numero
        processo.delete()
        messages.success(request, f'Processo {numero} excluído.')
        return redirect('processos:lista')
    return redirect('processos:detalhe', pk=pk)


def importar_pdf(request):
    if request.method == 'POST':
        pdfs = request.FILES.getlist('pdfs')
        if not pdfs:
            messages.error(request, 'Nenhum arquivo PDF enviado.')
            return redirect('processos:importar_pdf')

        dados_lista = processar_pdfs(pdfs)

        if not dados_lista:
            messages.error(request, 'Nao foi possivel extrair dados dos PDFs.')
            return redirect('processos:importar_pdf')

        planilha_bytes = gerar_planilha_padronizada(dados_lista)

        response = HttpResponse(
            planilha_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="processos_extraidos.xlsx"'
        return response

    return render(request, 'processos/importar_pdf.html')


def importar_planilha(request):
    resultado = None

    if request.method == 'POST':
        planilha = request.FILES.get('planilha')
        lote_id = request.POST.get('lote') or None
        contracheque_ativo   = request.FILES.get('contracheque_ativo')
        contracheque_inativo = request.FILES.get('contracheque_inativo')

        if not planilha:
            messages.error(request, 'Nenhuma planilha enviada.')
        else:
            try:
                registros, erros_leitura = ler_planilha_padronizada(planilha)
            except ValueError as e:
                messages.error(request, str(e))
                return render(request, 'processos/importar_planilha.html', {'lotes': Lote.objects.all()})

            criados = 0
            atualizados = 0
            erros = list(erros_leitura)

            tipos_validos = [t[0] for t in TipoBeneficio.choices]

            # Normaliza tipos vindos da planilha (hífens → underscores + aliases longos)
            TIPO_ALIAS = {
                'APOS_VOLUNTARIA_POR_IDADE_COM_PROVENTOS_PROPORCIONAIS': 'APOS_VOLUNTARIA_PROP_IDADE',
                'APOS_VOLUNTARIA_POR_IDADE_E_TEMPO_DE_CONTRIBUICAO':     'APOS_VOLUNTARIA_IDADE_TC',
                'APOS_VOLUNTARIA_POR_IDADE_E_TEMPO_DE_CONTRIBUI\u00c7\u00c3O': 'APOS_VOLUNTARIA_IDADE_TC',
            }

            def normalizar_tipo(raw):
                t = str(raw).strip().upper().replace('-', '_')
                return TIPO_ALIAS.get(t, t)

            def safe_decimal(val):
                if not val:
                    return None
                try:
                    v = str(val).replace(',', '.').strip()
                    float(v)
                    return v
                except Exception:
                    return None

            def safe_int(val):
                if not val:
                    return None
                try:
                    return int(str(val).split('.')[0])
                except Exception:
                    return None

            def safe_date(val):
                if not val:
                    return None
                from datetime import date, datetime
                if isinstance(val, date):
                    return val
                try:
                    return datetime.strptime(str(val).strip(), '%d/%m/%Y').date()
                except ValueError:
                    pass
                try:
                    return datetime.fromisoformat(str(val).strip()).date()
                except ValueError:
                    return None

            def _limpar_nome(nome):
                """Remove preposições/artigos soltos no início do nome extraído."""
                import re as _re
                nome = nome.strip()
                nome = _re.sub(r'^[a-záéíóúãõâêîôû]{1,3}\s+', '', nome, flags=_re.IGNORECASE)
                return nome.strip()

            for reg in registros:
                linha = reg['linha']
                dados = reg['dados']
                try:
                    cpf = dados['cpf'].strip()
                    nome = _limpar_nome(dados['nome_beneficiario'])
                    numero = dados['numero_processo'].strip() or f'IMP-{cpf[:9]}'

                    beneficiario, _ = Beneficiario.objects.get_or_create(cpf=cpf, defaults={'nome': nome})
                    beneficiario.nome = nome or beneficiario.nome
                    beneficiario.matricula = dados.get('matricula', '') or beneficiario.matricula
                    beneficiario.municipio = dados.get('municipio', '') or beneficiario.municipio
                    beneficiario.cargo = dados.get('cargo', '') or beneficiario.cargo
                    beneficiario.save()

                    tipo = normalizar_tipo(dados.get('tipo_beneficio', ''))
                    if tipo not in tipos_validos:
                        tipo = 'APOS_VOLUNTARIA'

                    data_concessao_val = _parse_date_field(dados.get('data_concessao'))
                    data_publicacao_val = _parse_date_field(dados.get('data_publicacao'))

                    processo, created = Processo.objects.get_or_create(
                        numero=numero,
                        defaults={
                            'beneficiario': beneficiario,
                            'tipo_beneficio': tipo,
                            'data_concessao': data_concessao_val,
                            'data_publicacao': data_publicacao_val,
                            'lote_id': lote_id,
                            'observacoes': dados.get('observacoes', ''),
                        }
                    )

                    if created:
                        criados += 1
                    else:
                        atualizados += 1
                        # Atualiza datas caso estejam nulas (podem ter sido importadas antes da correção)
                        update_fields = {}
                        if data_concessao_val and not processo.data_concessao:
                            update_fields['data_concessao'] = data_concessao_val
                        if data_publicacao_val and not processo.data_publicacao:
                            update_fields['data_publicacao'] = data_publicacao_val
                        if update_fields:
                            Processo.objects.filter(pk=processo.pk).update(**update_fields)

                    # Nunca sobrescreve dados de processo que pertence a outro lote.
                    # Evita que uma importação de um lote contamine dados de outro lote
                    # quando dois processos compartilham o mesmo número.
                    if not created and lote_id and processo.lote_id and str(processo.lote_id) != str(lote_id):
                        continue

                    regimes_validos = [r[0] for r in RegimeReajuste.choices]
                    regime = dados.get('regime_reajuste', '').strip().upper()
                    if regime not in regimes_validos:
                        regime = RegimeReajuste.NAO_DEFINIDO

                    # X na média indica paridade — não há média calculada
                    raw_media = dados.get('media_contribuicoes', '')
                    if str(raw_media).strip().upper() == 'X':
                        media_val = None
                        if regime == RegimeReajuste.NAO_DEFINIDO:
                            regime = RegimeReajuste.PARIDADE
                    else:
                        media_val = safe_decimal(raw_media)

                    DadosBeneficio.objects.update_or_create(
                        processo=processo,
                        defaults={
                            'base_calculo': safe_decimal(dados.get('base_calculo')),
                            'valor_concedido': safe_decimal(dados.get('valor_concedido')),
                            'valor_pago_folha': safe_decimal(dados.get('valor_pago_folha')),
                            'tempo_contribuicao': dados.get('tempo_contribuicao', ''),
                            'tempo_servico_publico': dados.get('tempo_servico_publico', ''),
                            'tempo_carreira': dados.get('tempo_carreira', ''),
                            'tempo_no_cargo': dados.get('tempo_no_cargo', ''),
                            'marco_temporal_ingresso': safe_date(dados.get('marco_temporal_ingresso')),
                            'media_contribuicoes': media_val,
                            'proporcionalidade_percentual': safe_decimal(dados.get('proporcionalidade_percentual')),
                            'idade_concessao': safe_int(dados.get('idade_concessao')),
                            'regra_aplicada': dados.get('regra_aplicada', ''),
                            'regime_reajuste': regime,
                        }
                    )
                    # ── Contracheque: campos digitados na planilha ────────────
                    dados_contracheque = {}

                    raw_mes = dados.get('contracheque_mes_ref', '')
                    if isinstance(raw_mes, str):
                        raw_mes = raw_mes.strip()
                    if raw_mes:
                        dados_contracheque['mes_referencia'] = safe_date(raw_mes)

                    v = safe_decimal(dados.get('contracheque_vencimento', ''))
                    if v:
                        dados_contracheque['valor_vencimento'] = v

                    v = safe_decimal(dados.get('contracheque_ultima_remuneracao', ''))
                    if v:
                        dados_contracheque['ultima_remuneracao_cargo'] = v

                    lei = dados.get('contracheque_lei_reajuste', '')
                    if isinstance(lei, str):
                        lei = lei.strip()
                    if lei:
                        dados_contracheque['lei_reajuste_municipal'] = lei

                    # Salva somente se a data de referência foi informada
                    if dados_contracheque.get('mes_referencia'):
                        ContrachequeAuditoria.objects.update_or_create(
                            processo=processo,
                            defaults={k: v for k, v in dados_contracheque.items() if v}
                        )

                    # Recalcula após salvar tanto DadosBeneficio quanto contracheque
                    processo.refresh_from_db()
                    recalcular_conferencia(processo, salvar=True)

                except Exception as e:
                    erros.append({'linha': linha, 'mensagem': str(e)})

            # ── Vincula PDFs de contracheque ao primeiro processo (OCR) ──────
            if registros and (contracheque_ativo or contracheque_inativo):
                primeiro_dados = registros[0]['dados']
                primeiro_num = primeiro_dados.get('numero_processo', '').strip()
                primeiro_cpf = primeiro_dados.get('cpf', '').strip()
                proc_alvo = None
                if primeiro_num:
                    proc_alvo = Processo.objects.filter(numero=primeiro_num).first()
                if proc_alvo is None and primeiro_cpf:
                    proc_alvo = Processo.objects.filter(beneficiario__cpf=primeiro_cpf).order_by('-data_cadastro').first()

                if proc_alvo:
                    def _ocr_contracheque(uploaded_file, tipo_str):
                        try:
                            import pytesseract, os as _os
                            from pdf2image import convert_from_bytes
                            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                            _os.environ['TESSDATA_PREFIX'] = r'C:\Users\vic_s\tessdata'
                            poppler = r'C:\Users\vic_s\poppler\poppler-24.08.0\Library\bin'
                            pdf_bytes = uploaded_file.read()
                            uploaded_file.seek(0)
                            pages = convert_from_bytes(pdf_bytes, dpi=200, poppler_path=poppler)
                            texto = pytesseract.image_to_string(pages[0], lang='por')
                            return extrair_dados_contracheque(texto, tipo=tipo_str)
                        except Exception:
                            return {}

                    ocr_dados = {}
                    if contracheque_ativo:
                        ocr_dados.update(_ocr_contracheque(contracheque_ativo, 'ATIVO'))
                        DocumentoProcesso.objects.update_or_create(
                            processo=proc_alvo,
                            tipo=TipoDocumento.CONTRACHEQUE_ATIVO,
                            defaults={'arquivo': contracheque_ativo, 'nome_original': contracheque_ativo.name}
                        )

                    if contracheque_inativo:
                        ocr_inativo = _ocr_contracheque(contracheque_inativo, 'INATIVO')
                        for k in ('mes_referencia', 'valor_vencimento', 'observacoes'):
                            if ocr_inativo.get(k):
                                ocr_dados[k] = ocr_inativo[k]
                        DocumentoProcesso.objects.update_or_create(
                            processo=proc_alvo,
                            tipo=TipoDocumento.CONTRACHEQUE_INATIVO,
                            defaults={'arquivo': contracheque_inativo, 'nome_original': contracheque_inativo.name}
                        )

                    if ocr_dados.get('mes_referencia'):
                        ContrachequeAuditoria.objects.update_or_create(
                            processo=proc_alvo,
                            defaults={k: v for k, v in ocr_dados.items() if v}
                        )

            resultado = {
                'tipo': 'success' if not erros else 'warning',
                'criados': criados,
                'atualizados': atualizados,
                'erros': erros,
            }
            if criados + atualizados > 0:
                messages.success(request, f'Importacao concluida: {criados} criados, {atualizados} atualizados.')

    return render(request, 'processos/importar_planilha.html', {
        'lotes': Lote.objects.all(),
        'resultado': resultado,
    })


def download_planilha_exemplo(request):
    dados = [
        {
            'numero_processo': 'RPPS-2024-001',
            'nome_beneficiario': 'Maria Aparecida Silva',
            'cpf': '123.456.789-00',
            'matricula': '00012345',
            'municipio': 'São Paulo',
            'cargo': 'Professora de Ensino Fundamental',
            'tipo_beneficio': 'APOS_VOLUNTARIA',
            'data_concessao': '15/03/2024',
            'data_publicacao': '20/03/2024',
            'regra_aplicada': 'Art. 40, §1º, III, a da CF/88 - Integralidade',
            'base_calculo': '8500.00',
            'valor_concedido': '8500.00',
            'valor_pago_folha': '8500.00',
            'tempo_contribuicao': '35 anos, 2 meses e 10 dias',
            'tempo_servico_publico': '35 anos e 2 meses',
            'tempo_carreira': '20 anos e 4 meses',
            'tempo_no_cargo': '5 anos e 1 mês',
            'marco_temporal_ingresso': '12/03/1989',
            'media_contribuicoes': '8320.45',
            'idade_concessao': '60',
            'observacoes': 'Aposentadoria voluntária por idade e tempo de contribuição. Regra de transição EC 103/2019.',
        },
        {
            'numero_processo': 'RPPS-2024-002',
            'nome_beneficiario': 'João Carlos Oliveira',
            'cpf': '987.654.321-00',
            'matricula': '00067890',
            'municipio': 'Campinas',
            'cargo': 'Agente Administrativo',
            'tipo_beneficio': 'APOS_COMPULSORIA',
            'data_concessao': '01/02/2024',
            'data_publicacao': '05/02/2024',
            'regra_aplicada': 'Art. 40, §1º, II da CF/88 - Compulsória aos 75 anos',
            'base_calculo': '5200.00',
            'valor_concedido': '5200.00',
            'valor_pago_folha': '5180.50',
            'tempo_contribuicao': '42 anos e 5 meses',
            'tempo_servico_publico': '42 anos',
            'tempo_carreira': '30 anos',
            'tempo_no_cargo': '10 anos',
            'marco_temporal_ingresso': '01/06/1982',
            'media_contribuicoes': '',
            'idade_concessao': '75',
            'observacoes': 'Aposentadoria compulsória por atingir 75 anos.',
        },
        {
            'numero_processo': 'RPPS-2024-003',
            'nome_beneficiario': 'Ana Paula Ferreira dos Santos',
            'cpf': '456.123.789-11',
            'matricula': '00034567',
            'municipio': 'Guarulhos',
            'cargo': 'Médica Sanitarista',
            'tipo_beneficio': 'PENSAO_MORTE',
            'data_concessao': '10/06/2024',
            'data_publicacao': '15/06/2024',
            'regra_aplicada': 'Art. 40, §7º da CF/88 - Pensão por Morte',
            'base_calculo': '12000.00',
            'valor_concedido': '9000.00',
            'valor_pago_folha': '9000.00',
            'tempo_contribuicao': '',
            'tempo_servico_publico': '',
            'tempo_carreira': '',
            'tempo_no_cargo': '',
            'marco_temporal_ingresso': '',
            'media_contribuicoes': '',
            'idade_concessao': '45',
            'observacoes': 'Pensão por morte do servidor titular. Cota de 75% do benefício.',
        },
    ]
    planilha_bytes = gerar_planilha_padronizada(dados)
    response = HttpResponse(
        planilha_bytes,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="planilha_exemplo.xlsx"'
    return response


def lotes(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'novo_lote':
            numero = request.POST.get('numero', '').strip()
            descricao = request.POST.get('descricao', '').strip()
            if numero:
                Lote.objects.create(numero=numero, descricao=descricao)
                messages.success(request, f'Lote {numero} criado.')
            else:
                messages.error(request, 'Numero do lote e obrigatorio.')
        return redirect('processos:lotes')

    return render(request, 'processos/lotes.html', {
        'lotes': Lote.objects.order_by('-data_criacao'),
    })


def lote_detalhe(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    processos = (
        Processo.objects
        .filter(lote=lote)
        .select_related('beneficiario', 'analiseelegibilidade', 'analisecalculo', 'conferenciafolha')
        .order_by('numero')
    )
    return render(request, 'processos/lote_detalhe.html', {
        'lote': lote,
        'processos': processos,
        'status_choices': StatusLote.choices,
    })


def editar_lote(request, pk):
    lote = get_object_or_404(Lote, pk=pk)
    if request.method == 'POST':
        lote.numero = request.POST.get('numero', lote.numero)
        lote.descricao = request.POST.get('descricao', lote.descricao)
        lote.status = request.POST.get('status', lote.status)
        lote.save()
        messages.success(request, f'Lote {lote.numero} atualizado.')
        return redirect('processos:lotes')

    return render(request, 'processos/editar_lote.html', {
        'lote': lote,
        'status_choices': StatusLote.choices,
    })


def certidoes_tempo(request, pk):
    """Adiciona ou exclui certidões de tempo de contribuição averbadas ao processo."""
    processo = get_object_or_404(Processo, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'excluir':
            ctc_pk = request.POST.get('ctc_pk')
            CertidaoTempoContribuicao.objects.filter(pk=ctc_pk, processo=processo).delete()
            messages.success(request, 'Certidão removida.')
            return redirect('processos:detalhe', pk=pk)

        # action == 'adicionar'
        def _int(v):
            try: return int(v or 0)
            except: return 0

        data_inicio_raw = request.POST.get('data_inicio_periodo') or None
        data_fim_raw    = request.POST.get('data_fim_periodo') or None

        cert_anos_post  = _int(request.POST.get('cert_anos'))
        cert_meses_post = _int(request.POST.get('cert_meses'))
        cert_dias_post  = _int(request.POST.get('cert_dias'))

        # Auto-calcular tempo certificado pelas datas quando os campos não foram preenchidos
        if cert_anos_post == 0 and cert_meses_post == 0 and cert_dias_post == 0:
            if data_inicio_raw and data_fim_raw:
                from datetime import date as _date
                try:
                    d_ini = _date.fromisoformat(data_inicio_raw)
                    d_fim = _date.fromisoformat(data_fim_raw)
                    total_dias_calc = max(0, (d_fim - d_ini).days + 1)
                    cert_anos_post, cert_meses_post, cert_dias_post = _dias_para_amd(total_dias_calc)
                except (ValueError, TypeError):
                    pass

        possui_conc = request.POST.get('possui_concomitancia') == 'on'
        CertidaoTempoContribuicao.objects.create(
            processo=processo,
            numero_certidao=request.POST.get('numero_certidao', '').strip(),
            orgao_emissor=request.POST.get('orgao_emissor', '').strip(),
            tipo_origem=request.POST.get('tipo_origem', 'INSS_RGPS'),
            data_inicio_periodo=data_inicio_raw,
            data_fim_periodo=data_fim_raw,
            data_emissao=request.POST.get('data_emissao') or None,
            cert_anos=cert_anos_post,
            cert_meses=cert_meses_post,
            cert_dias=cert_dias_post,
            possui_concomitancia=possui_conc,
            conc_anos=_int(request.POST.get('conc_anos')) if possui_conc else 0,
            conc_meses=_int(request.POST.get('conc_meses')) if possui_conc else 0,
            conc_dias=_int(request.POST.get('conc_dias')) if possui_conc else 0,
            descricao_concomitancia=request.POST.get('descricao_concomitancia', '').strip(),
            observacoes=request.POST.get('observacoes', '').strip(),
        )
        messages.success(request, 'Certidão de tempo adicionada.')
        return redirect('processos:detalhe', pk=pk)

    return redirect('processos:detalhe', pk=pk)


def contribuicoes_processo(request, pk):
    """Adiciona, edita ou exclui registros de contribuição previdenciária do processo."""
    processo = get_object_or_404(Processo, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'excluir':
            ContribuicaoPrevidenciaria.objects.filter(
                pk=request.POST.get('contrib_pk'), processo=processo
            ).delete()
            messages.success(request, 'Contribuição removida.')
            return redirect('processos:detalhe', pk=pk)

        # action == 'adicionar'
        from decimal import Decimal, InvalidOperation
        from datetime import datetime

        def _dec(v):
            try:
                return Decimal(str(v).replace(',', '.').strip())
            except (InvalidOperation, TypeError, ValueError):
                return None

        competencia_raw = request.POST.get('competencia', '').strip()
        # competencia vem como YYYY-MM do input[type=month]
        if len(competencia_raw) == 7:
            competencia_raw += '-01'
        try:
            competencia_date = datetime.fromisoformat(competencia_raw).date() if competencia_raw else None
        except ValueError:
            competencia_date = None

        if not competencia_date:
            messages.error(request, 'Competência inválida.')
            return redirect('processos:detalhe', pk=pk)

        salario = _dec(request.POST.get('salario_contribuicao'))
        if not salario:
            messages.error(request, 'Salário de contribuição obrigatório.')
            return redirect('processos:detalhe', pk=pk)

        indice = _dec(request.POST.get('indice_correcao')) or None
        valor_corrigido_manual = _dec(request.POST.get('valor_corrigido')) or None

        obj, created = ContribuicaoPrevidenciaria.objects.update_or_create(
            processo=processo,
            competencia=competencia_date,
            defaults={
                'salario_contribuicao': salario,
                'indice_correcao': indice,
                'valor_corrigido': valor_corrigido_manual,
                'observacoes': request.POST.get('observacoes', '').strip(),
            }
        )
        # Recalcula valor_corrigido pelo índice se não foi informado manualmente
        if indice and not valor_corrigido_manual:
            obj.valor_corrigido = (salario * indice).quantize(Decimal('0.01'))
            obj.save()

        messages.success(request, 'Contribuição registrada.' if created else 'Contribuição atualizada.')
        return redirect('processos:detalhe', pk=pk)

    return redirect('processos:detalhe', pk=pk)


def documentos_processo(request, pk):
    """Upload e exclusão de documentos (contracheques, etc.) vinculados a um processo."""
    processo = get_object_or_404(Processo, pk=pk)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'excluir':
            doc_pk = request.POST.get('doc_pk')
            doc = DocumentoProcesso.objects.filter(pk=doc_pk, processo=processo).first()
            if doc:
                doc.arquivo.delete(save=False)
                doc.delete()
                messages.success(request, 'Documento removido.')
            return redirect('processos:detalhe', pk=pk)

        # action == 'adicionar'
        arquivo = request.FILES.get('arquivo')
        tipo    = request.POST.get('tipo', TipoDocumento.OUTRO)
        if not arquivo:
            messages.error(request, 'Nenhum arquivo enviado.')
            return redirect('processos:detalhe', pk=pk)

        DocumentoProcesso.objects.update_or_create(
            processo=processo,
            tipo=tipo,
            defaults={
                'arquivo': arquivo,
                'nome_original': arquivo.name,
            }
        )
        messages.success(request, f'{dict(TipoDocumento.choices).get(tipo, tipo)} salvo com sucesso.')
        return redirect('processos:detalhe', pk=pk)

    return redirect('processos:detalhe', pk=pk)


def reajuste_inss(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'salvar':
            pk = request.POST.get('pk')
            try:
                ano = int(request.POST.get('ano', 0))
                obj = ReajusteINSS.objects.get(pk=pk) if pk else ReajusteINSS()
                obj.ano = ano
                obj.vigencia = request.POST.get('vigencia')
                obj.percentual_acima_minimo = request.POST.get('percentual_acima_minimo').replace(',', '.')
                obj.percentual_piso = request.POST.get('percentual_piso').replace(',', '.')
                obj.salario_minimo = request.POST.get('salario_minimo').replace(',', '.')
                obj.teto_inss = request.POST.get('teto_inss').replace(',', '.')
                obj.base_legal = request.POST.get('base_legal', '')
                obj.save()
                messages.success(request, f'Reajuste {obj.ano} salvo com sucesso.')
            except Exception as e:
                messages.error(request, f'Erro ao salvar: {e}')
        elif action == 'excluir':
            pk = request.POST.get('pk')
            try:
                obj = ReajusteINSS.objects.get(pk=pk)
                ano = obj.ano
                obj.delete()
                messages.success(request, f'Reajuste {ano} excluído.')
            except Exception as e:
                messages.error(request, f'Erro ao excluir: {e}')
        return redirect('processos:reajuste_inss')

    registros = ReajusteINSS.objects.order_by('ano')
    return render(request, 'processos/reajuste_inss.html', {'registros': registros})
