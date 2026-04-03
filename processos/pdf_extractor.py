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
        'idade_concessao': '',
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
        r'(?:requerente|benefici[aá]rio|servidor|nome)\s*:?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][^\n]{5,60})',
    ]
    for padrao in padroes_nome:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            nome = m.group(1).strip()
            if len(nome) > 3:
                dados['nome_beneficiario'] = nome
                break

    # Matrícula
    m = re.search(r'matr[íi]cula\s*:?\s*(\d[\w\-\.]{1,20})', texto, re.IGNORECASE)
    if m:
        dados['matricula'] = m.group(1).strip()

    # Município
    padroes_municipio = [
        r'munic[íi]pio\s*(?:de|:)?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][A-Za-záéíóúãõâêîôû\s]{3,50}?)(?:\n|,|[-–]|UF|/)',
        r'cidade\s*:?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][A-Za-záéíóúãõâêîôû\s]{3,40})',
    ]
    for padrao in padroes_municipio:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['municipio'] = m.group(1).strip()
            break

    # Cargo
    padroes_cargo = [
        r'cargo\s*:?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][^\n]{3,80})',
        r'fun[çc][ãa]o\s*:?\s*([A-ZÁÉÍÓÚÃÕÂÊÎÔÛ][^\n]{3,60})',
    ]
    for padrao in padroes_cargo:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['cargo'] = m.group(1).strip()
            break

    # Tipo de benefício
    texto_lower = texto.lower()
    if any(x in texto_lower for x in ['aposentadoria por invalidez', 'incapacidade permanente', 'invalidez']):
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
    padroes_data = [
        r'(?:data\s+de\s+concess[ãa]o|conced[io]do\s+em|concedida\s+em|concedida\s+a\s+partir)\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
        r'concess[ãa]o\s*:?\s*(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4})',
    ]
    for padrao in padroes_data:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['data_concessao'] = parse_data(m.group(1))
            break

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
    ]
    for padrao in padroes_valor:
        m = re.search(padrao, texto, re.IGNORECASE)
        if m:
            dados['valor_concedido'] = parse_valor(m.group(1))
            break

    # Tempo de contribuição
    m = re.search(r'tempo\s+de\s+contribui[çc][ãa]o\s*:?\s*(\d+\s*anos?\s*(?:e\s*\d+\s*meses?)?)', texto, re.IGNORECASE)
    if m:
        dados['tempo_contribuicao'] = m.group(1).strip()

    # Tempo de serviço público
    m = re.search(r'tempo\s+de\s+servi[çc]o\s+p[úu]blico\s*:?\s*(\d+\s*anos?\s*(?:e\s*\d+\s*meses?)?)', texto, re.IGNORECASE)
    if m:
        dados['tempo_servico_publico'] = m.group(1).strip()

    # Idade na concessão
    m = re.search(r'(?:idade|anos?\s+de\s+idade)\s*(?:na\s+concess[ãa]o)?\s*:?\s*(\d{2})\s*anos?', texto, re.IGNORECASE)
    if m:
        dados['idade_concessao'] = m.group(1)

    # Se número do processo não encontrado, usa nome do arquivo
    if not dados['numero_processo'] and nome_arquivo:
        base = re.sub(r'\.pdf$', '', nome_arquivo, flags=re.IGNORECASE)
        dados['numero_processo'] = base[:50]

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
