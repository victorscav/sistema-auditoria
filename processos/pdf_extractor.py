"""
Módulo de extração de dados de PDFs de processos previdenciários.
Usa pdfplumber para extrair texto e regex para identificar campos.
"""
import re
import io
from datetime import datetime


def extrair_texto_pdf(arquivo):
    """Extrai todo o texto de um PDF usando pdfplumber."""
    try:
        import pdfplumber
        texto_completo = []
        with pdfplumber.open(arquivo) as pdf:
            for pagina in pdf.pages:
                texto = pagina.extract_text()
                if texto:
                    texto_completo.append(texto)
        return '\n'.join(texto_completo)
    except Exception as e:
        return ''


def limpar_cpf(cpf_str):
    """Normaliza CPF para formato XXX.XXX.XXX-XX."""
    if not cpf_str:
        return ''
    digits = re.sub(r'\D', '', cpf_str)
    if len(digits) == 11:
        return f'{digits[:3]}.{digits[3:6]}.{digits[6:9]}-{digits[9:]}'
    return cpf_str.strip()


def parse_data(data_str):
    """Tenta parsear uma string de data em vários formatos."""
    if not data_str:
        return ''
    data_str = data_str.strip()
    formatos = ['%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d.%m.%Y']
    for fmt in formatos:
        try:
            return datetime.strptime(data_str, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return data_str


def parse_valor(valor_str):
    """Converte string de valor monetário para número."""
    if not valor_str:
        return ''
    # Remove R$, espaços, pontos de milhar e converte vírgula para ponto
    valor_str = re.sub(r'R\$\s*', '', valor_str)
    valor_str = re.sub(r'\.(?=\d{3})', '', valor_str)
    valor_str = valor_str.replace(',', '.').strip()
    try:
        float(valor_str)
        return valor_str
    except ValueError:
        return ''


def extrair_campos(texto, nome_arquivo=''):
    """
    Extrai campos relevantes do texto de um processo previdenciário.
    Retorna um dicionário com os campos extraídos.
    """
    dados = {
        'numero_processo': '',
        'nome_beneficiario': '',
        'cpf': '',
        'matricula': '',
        'municipio': '',
        'cargo': '',
        'tipo_beneficio': '',
        'data_concessao': '',
        'data_publicacao': '',
        'regra_aplicada': '',
        'base_calculo': '',
        'valor_concedido': '',
        'valor_pago_folha': '',
        'tempo_contribuicao': '',
        'tempo_servico_publico': '',
        'tempo_carreira': '',
        'tempo_no_cargo': '',
        'marco_temporal_ingresso': '',
        'idade_concessao': '',
        'regime_reajuste': '',
        'observacoes': '',
    }

    if not texto:
        return dados

    linhas = texto.split('\n')

    # Número do processo
    padroes_processo = [
        r'\b(?:processo|proc)\b\.?\s*(?:n[°º\.])?\s*:?\s*([A-Z0-9][\w\-\/\.]{3,30})',
        r'\b(?:requerimento|req)\b\.?\s*n[°º]?\s*:?\s*([A-Z0-9][\w\-\/\.]{3,20})',
        r'\b(\d{4,6}\/\d{4})\b',
        r'\b(\d{5,10}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4})\b',  # formato TJ
    ]
    for padrao in padroes_processo:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['numero_processo'] = m.group(1).strip()
            break

    # CPF
    m = re.search(r'\b(\d{3}[\.\s]?\d{3}[\.\s]?\d{3}[\-\s]?\d{2})\b', texto)
    if m:
        dados['cpf'] = limpar_cpf(m.group(1))

    # Nome do beneficiário - busca após palavras-chave
    padroes_nome = [
        r'(?:requerente|benefici[aá]rio|servidor|nome|interessado)\s*:?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][A-ZÁÉÍÓÚÃÕÂÊÎÔÛa-záéíóúãõâêîôû\s]{5,60}?)(?:\n|,|CPF|Matrícula|nascid)',
        r'(?:requerente|benefici[aá]rio|servidor|nome)\s*:?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][A-ZÁÉÍÓÚÃÕÂÊÎÔÛa-záéíóúãõâêîôû\s]{5,60}?)(?:\n|,|CPF|Matrícula|nascid|$)',
    ]
    for padrao in padroes_nome:
        m = re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)
        if m:
            nome = m.group(1).strip()
            # Remove partículas soltas no final (artigos/preposições como "a", "o", "e", "de")
            nome = re.sub(r'\s+[a-záéíóúãõâêîôû]{1,3}\s*$', '', nome).strip()
            if len(nome) > 3:
                dados['nome_beneficiario'] = nome
                break

    # Matrícula
    padroes_matricula = [
        r'matr[íi]cula\s*n[º°]?\s*:?\s*(\d[\w\-\.]{1,20})',
        r'matr[íi]cula\s*:?\s*n[º°]?\s*(\d[\w\-\.]{1,20})',
        r'matr[íi]cula\s*:?\s*(\d[\w\-\.]{1,20})',
    ]
    for padrao in padroes_matricula:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['matricula'] = m.group(1).strip()
            break

    # Município — inclui padrão do cabeçalho "Município de X"
    padroes_municipio = [
        r'munic[íi]pio\s*(?:de|:)?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][A-Za-záéíóúãõâêîôû\s]{3,50}?)(?:\n|,|[-–]|UF|/)',
        r'cidade\s*:?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][A-Za-záéíóúãõâêîôû\s]{3,40})',
        r'Prefeitura\s+Municipal\s+de\s+([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][A-Za-záéíóúãõâêîôû ]{3,40})',
    ]
    for padrao in padroes_municipio:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            # Remove lixo de OCR após a primeira linha
            val = m.group(1).split('\n')[0].strip().rstrip(',').strip()
            dados['municipio'] = val
            break

    # Cargo — prioriza padrões específicos do Ato antes dos genéricos
    padroes_cargo = [
        # Ato: "servidor(a) NOME, CARGO, Matricula"
        r'servidor[a]?\s+[A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][^,\n]+,\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][^,\n]{3,60}),\s*[Mm]atri',
        # Ato: "investida no cargo de CARGO"
        r'investida?\s+no\s+cargo\s+de\s+([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][^\n,]{3,80})',
        # Genérico com label "cargo:"
        r'\bcargo\s*:\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][^\n]{3,80})',
    ]
    for padrao in padroes_cargo:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['cargo'] = m.group(1).strip().rstrip(',').strip()
            break

    # Tipo de benefício
    texto_lower = texto.lower()
    if any(x in texto_lower for x in ['aposentadoria por invalidez', 'incapacidade permanente', 'invalidez permanente', 'invalidez']):
        dados['tipo_beneficio'] = 'APOS_INCAPACIDADE'
    elif any(x in texto_lower for x in ['aposentadoria compulsória', 'compulsória', '75 anos', 'setenta e cinco']):
        dados['tipo_beneficio'] = 'APOS_COMPULSORIA'
    elif any(x in texto_lower for x in ['pensão por morte', 'pensao por morte', 'pensionista']):
        dados['tipo_beneficio'] = 'PENSAO_MORTE'
    elif any(x in texto_lower for x in ['revisão', 'reenquadramento', 'revisao']):
        dados['tipo_beneficio'] = 'REVISAO_REENQUADRAMENTO'
    elif any(x in texto_lower for x in ['aposentadoria voluntária', 'aposentadoria voluntaria', 'aposentador']):
        dados['tipo_beneficio'] = 'APOS_VOLUNTARIA'

    # Data de concessão
    meses_pt = {'janeiro':'01','fevereiro':'02','março':'03','marco':'03','abril':'04',
                'maio':'05','junho':'06','julho':'07','agosto':'08','setembro':'09',
                'outubro':'10','novembro':'11','dezembro':'12'}
    padroes_data = [
        r'(?:data\s+de\s+concess[ãa]o|conced[io]do\s+em|concedida\s+em|concedida\s+a\s+partir)\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'concess[ãa]o\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'validade\s+a\s+partir\s+de\s+(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
    ]
    for padrao in padroes_data:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['data_concessao'] = parse_data(m.group(1))
            break
    # Fallback: data da portaria ("Portaria Nº X de DD de MÊS de AAAA")
    if not dados['data_concessao']:
        m = re.search(
            r'PORTARIA\s+N[º°]?\s*\d+\s+DE\s+(\d{1,2})\s+DE\s+'
            r'(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)'
            r'\s+DE\s+(\d{4})',
            texto, re.IGNORECASE
        )
        if m:
            dia = m.group(1).zfill(2)
            mes = meses_pt.get(m.group(2).lower().replace('ç','c'), '01')
            ano = m.group(3)
            dados['data_concessao'] = f'{ano}-{mes}-{dia}'

    # Data de publicação
    m = re.search(r'(?:publicado|publicada|publica[çc][ãa]o|D\.O\.)\s*(?:em|:)?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})', texto, re.IGNORECASE)
    if m:
        dados['data_publicacao'] = parse_data(m.group(1))

    # Regra/emenda constitucional
    padroes_regra = [
        r'(E\.?C\.?\s*\d+\/\d+)',
        r'(emenda\s+constitucional\s+n[°º]?\s*\d+)',
        r'(art\.\s*\d+[º°]?\s*da\s+(?:CF|Constituição)[^\n]{0,60})',
        r'(regra\s+de\s+transi[çc][ãa]o[^\n]{0,60})',
    ]
    for padrao in padroes_regra:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['regra_aplicada'] = m.group(1).strip()
            break

    # Valores monetários
    padroes_base_calc = [
        r'(?:base\s+de\s+c[áa]lculo|proventos\s+de\s+base)\s*:?\s*R?\$?\s*([\d\.]+,\d{2})',
    ]
    for padrao in padroes_base_calc:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['base_calculo'] = parse_valor(m.group(1))
            break

    padroes_valor = [
        r'(?:valor\s+(?:do\s+)?benefício|valor\s+concedido|proventos)\s*:?\s*R?\$?\s*([\d\.]+,\d{2})',
        r'(?:valor\s+total)\s*:?\s*R?\$?\s*([\d\.]+,\d{2})',
        # Padrão do Ato de Mangaratiba: R$ ou RS$ no final de linha da tabela de proventos
        r'R[S]?\$\s*([\d\.]+,\d{2})\s*$',
    ]
    for padrao in padroes_valor:
        m = re.search(padrao, texto, re.IGNORECASE | re.MULTILINE)
        if m:
            dados['valor_concedido'] = parse_valor(m.group(1))
            break

    # Base de cálculo = valor concedido quando não identificada separadamente
    if not dados['base_calculo'] and dados['valor_concedido']:
        dados['base_calculo'] = dados['valor_concedido']

    # Tempo de contribuição
    m = re.search(r'tempo\s+de\s+contribui[çc][ãa]o\s*:?\s*(\d+\s*anos?\s*(?:e\s*\d+\s*meses?)?)', texto, re.IGNORECASE)
    if m:
        dados['tempo_contribuicao'] = m.group(1).strip()

    # Tempo de serviço público
    m = re.search(r'tempo\s+de\s+servi[çc]o\s+p[úu]blico\s*:?\s*(\d+\s*anos?\s*(?:e\s*\d+\s*meses?)?)', texto, re.IGNORECASE)
    if m:
        dados['tempo_servico_publico'] = m.group(1).strip()

    # Tempo de carreira (certidão de tempo de serviço)
    padroes_carreira = [
        r'tempo\s+(?:total\s+)?(?:de|na)\s+carreira\s*:?\s*(\d+\s*anos?\s*(?:[,e]\s*\d+\s*m[eê]ses?)?(?:\s*[,e]\s*\d+\s*dias?)?)',
        r'tempo\s+de\s+servi[çc]o\s+na\s+carreira\s*:?\s*(\d+\s*anos?\s*(?:[,e]\s*\d+\s*m[eê]ses?)?(?:\s*[,e]\s*\d+\s*dias?)?)',
    ]
    for padrao in padroes_carreira:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['tempo_carreira'] = m.group(1).strip()
            break

    # Tempo no cargo (certidão de tempo de serviço)
    padroes_cargo_tempo = [
        r'tempo\s+no\s+exerc[íi]cio\s+(?:do\s+)?cargo\s*(?:efetivo)?\s*:?\s*(\d+\s*anos?\s*(?:[,e]\s*\d+\s*m[eê]ses?)?(?:\s*[,e]\s*\d+\s*dias?)?)',
        r'tempo\s+no\s+cargo\s*(?:efetivo)?\s*:?\s*(\d+\s*anos?\s*(?:[,e]\s*\d+\s*m[eê]ses?)?(?:\s*[,e]\s*\d+\s*dias?)?)',
        r'exerc[íi]cio\s+no\s+cargo\s*:?\s*(\d+\s*anos?\s*(?:[,e]\s*\d+\s*m[eê]ses?)?(?:\s*[,e]\s*\d+\s*dias?)?)',
    ]
    for padrao in padroes_cargo_tempo:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['tempo_no_cargo'] = m.group(1).strip()
            break

    # Marco temporal de ingresso no serviço público
    padroes_ingresso = [
        r'(?:data\s+de\s+ingresso|ingresso\s+no\s+servi[çc]o\s+p[úu]blico|data\s+de\s+admiss[ãa]o)\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'ingressou\s+(?:no\s+servi[çc]o\s+p[úu]blico\s+)?(?:em\s+)?(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'admitid[oa]\s+(?:em|a\s+partir\s+de)\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'data\s+de\s+posse\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
    ]
    for padrao in padroes_ingresso:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['marco_temporal_ingresso'] = parse_data(m.group(1))
            break

    # Idade na concessão
    m = re.search(r'(?:idade|anos?\s+de\s+idade)\s*(?:na\s+concess[ãa]o)?\s*:?\s*(\d{2})\s*anos?', texto, re.IGNORECASE)
    if m:
        dados['idade_concessao'] = m.group(1)

    # Regime de reajuste
    # Prioridade: expressão explícita "com/sem paridade" → referência à EC/artigo de reajuste
    if re.search(r'\bsem\s+paridade\b', texto, re.IGNORECASE):
        dados['regime_reajuste'] = 'MEDIA'
    elif re.search(r'\bcom\s+paridade\b', texto, re.IGNORECASE):
        dados['regime_reajuste'] = 'PARIDADE'
    elif re.search(r'art(?:igo)?\.?\s*7[º°]?\s+da\s+EC\s+41', texto, re.IGNORECASE):
        # Art. 7º EC 41/03 = regra de transição com paridade
        dados['regime_reajuste'] = 'PARIDADE'
    elif re.search(r'art(?:igo)?\.?\s*3[º°]?\s+da\s+EC\s+47', texto, re.IGNORECASE):
        # Art. 3º EC 47/05 = regra de transição com paridade
        dados['regime_reajuste'] = 'PARIDADE'
    elif re.search(r'art(?:igo)?\.?\s*40[,\s]*[§8]\s*8[º°]', texto, re.IGNORECASE):
        # Art. 40, §8 CF/88 = reajuste pelo INSS (sem paridade)
        dados['regime_reajuste'] = 'MEDIA'

    # Se número do processo não encontrado, usa nome do arquivo
    if not dados['numero_processo'] and nome_arquivo:
        base = re.sub(r'\.pdf$', '', nome_arquivo, flags=re.IGNORECASE)
        dados['numero_processo'] = base[:50]

    return dados


def extrair_dados_contracheque(texto, tipo='INATIVO'):
    """
    Extrai campos do ContrachequeAuditoria a partir do texto OCR de um contracheque.
    tipo: 'ATIVO' (servidor em atividade) ou 'INATIVO' (aposentado/pensionista).
    Retorna dicionário com os campos extraídos.
    """
    dados = {
        'mes_referencia': None,
        'valor_vencimento': None,
        'ultima_remuneracao_cargo': None,
        'lei_reajuste_municipal': '',
        'percentual_reajuste_lei': None,
        'data_vigencia_reajuste': None,
        'observacoes': '',
    }

    if not texto:
        return dados

    # ── Mês de referência ───────────────────────────────────────────────────
    meses = {
        'janeiro': 1, 'fevereiro': 2, 'março': 3, 'marco': 3,
        'abril': 4, 'maio': 5, 'junho': 6, 'julho': 7,
        'agosto': 8, 'setembro': 9, 'outubro': 10,
        'novembro': 11, 'dezembro': 12,
    }
    m = re.search(
        r'(janeiro|fevereiro|mar[çc]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro)'
        r'\s+de\s+(\d{4})',
        texto, re.IGNORECASE
    )
    if m:
        from datetime import date
        nome_mes = m.group(1).lower().replace('ç', 'c')
        num_mes = meses.get(nome_mes, 1)
        ano = int(m.group(2))
        dados['mes_referencia'] = date(ano, num_mes, 1)

    def _parse_valor(raw):
        """Converte string de valor OCR para decimal (ex: '3.778,92' ou '3.994 32')."""
        if not raw:
            return None
        # Normaliza espaço antes dos centavos (OCR às vezes lê '3.994 32' em vez de '3.994,32')
        raw = re.sub(r'(\d)\s+(\d{2})$', r'\1,\2', raw.strip())
        raw = raw.replace('.', '').replace(',', '.')
        try:
            return str(round(float(raw), 2))
        except ValueError:
            return None

    def _valor(padrao):
        """Extrai e converte o primeiro valor que case com o padrão."""
        hit = re.search(padrao, texto, re.IGNORECASE)
        return _parse_valor(hit.group(1)) if hit else None

    if tipo == 'INATIVO':
        # Linha do SALÁRIO DO MÊS: "1601  SALÁRIO DO MÊS  30,00  3.994,32"
        # Pula a referência (dias) e pega o valor de vencimento no final da linha
        dados['valor_vencimento'] = (
            _valor(r'(?:1601|SAL[AÁ]RIO\s+DO\s+M[EÊ]S)\s+[\d,.]+\s+([\d.,]+(?:\s\d{2})?)')
            or _valor(r'Total\s+Vencimentos\s+([\d.,]+(?:\s\d{2})?)')
        )
    else:
        # Contracheque ativo: linha VENCIMENTO tem formato "1001 VENCIMENTO * 30,00 3.778,92"
        # A referência (dias) vem antes do valor — pega o ÚLTIMO valor numérico da linha
        m = re.search(r'(?:1001|VENCIMENTO\b)[^\n]+', texto, re.IGNORECASE)
        if m:
            valores = re.findall(r'\d[\d.]*,\d{2}', m.group())
            if valores:
                dados['ultima_remuneracao_cargo'] = _parse_valor(valores[-1])

        # Lei de reajuste: "Lei nº NNNN de DD/MM/AAAA"
        lei = re.search(r'Lei\s+n[º°\.]\s*(\d[\d\.\/]+\s+de\s+\d{2}\/\d{2}\/\d{4})', texto, re.IGNORECASE)
        if lei:
            dados['lei_reajuste_municipal'] = 'Lei nº ' + lei.group(1).strip()

    return dados


def processar_pdfs(arquivos):
    """
    Processa uma lista de arquivos PDF e retorna lista de dicionários com dados extraídos.
    """
    resultados = []
    for arquivo in arquivos:
        nome = arquivo.name if hasattr(arquivo, 'name') else 'processo'
        texto = extrair_texto_pdf(arquivo)
        dados = extrair_campos(texto, nome)
        resultados.append(dados)
    return resultados
