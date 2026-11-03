"""Gera relatórios da B3 fictícios, nos mesmos formatos dos reais. Nenhum dado real entra nos testes."""

import io
from datetime import date, timedelta

from openpyxl import Workbook

INSTITUTION = "NU INVESTIMENTOS S.A. - CTVM"

STOCK_HEADER = [
    "Produto",
    "Instituição",
    "Conta",
    "Código de Negociação",
    "CNPJ da Empresa",
    "Código ISIN / Distribuição",
    "Tipo",
    "Escriturador",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Preço de Fechamento",
    "Valor Atualizado",
]
FUND_HEADER = [
    "Produto",
    "Instituição",
    "Conta",
    "Código de Negociação",
    "CNPJ do Fundo",
    "Código ISIN / Distribuição",
    "Tipo",
    "Administrador",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Preço de Fechamento",
    "Valor Atualizado",
]
BDR_HEADER = [
    "Produto",
    "Instituição",
    "Conta",
    "Código de Negociação",
    "Código ISIN / Distribuição",
    "Tipo",
    "Escriturador",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Preço de Fechamento",
    "Valor Atualizado",
]
RF_HEADER = [
    "Produto",
    "Instituição",
    "Emissor",
    "Código",
    "Indexador",
    "Tipo de regime",
    "Data de Emissão",
    "Vencimento",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Contraparte",
    "Preço Atualizado MTM",
    "Valor Atualizado MTM",
    "Preço Atualizado CURVA",
    "Valor Atualizado CURVA",
    "Preço Atualizado FECHAMENTO",
    "Valor Atualizado FECHAMENTO",
]
TD_HEADER = [
    "Produto",
    "Instituição",
    "Código ISIN",
    "Indexador",
    "Vencimento",
    "Quantidade",
    "Quantidade Disponível",
    "Quantidade Indisponível",
    "Motivo",
    "Valor Aplicado",
    "Valor bruto",
    "Valor líquido",
    "Valor Atualizado",
]
MOVEMENT_HEADER = [
    "Entrada/Saída",
    "Data",
    "Movimentação",
    "Produto",
    "Instituição",
    "Quantidade",
    "Preço unitário",
    "Valor da Operação",
]

TOTAL_VALUE = 4580.0
NEAR_MATURITY_DAYS = 20
FAR_MATURITY_DAYS = 400


def br(day):
    return day.strftime("%d/%m/%Y")


def _workbook(sheets):
    workbook = Workbook()
    workbook.remove(workbook.active)
    for title, rows in sheets.items():
        sheet = workbook.create_sheet(title)
        for row in rows:
            sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _stock(code, quantity, close):
    return [
        f"{code} - EMPRESA {code}",
        INSTITUTION,
        "1",
        code,
        "00000000000191",
        "BRTEST - 1",
        "ON",
        "BANCO",
        quantity,
        quantity,
        "-",
        "-",
        close,
        quantity * close,
    ]


def _fund(code, quantity, close, kind="Cotas"):
    return [
        f"{code} - FUNDO {code}",
        INSTITUTION,
        "1",
        code,
        "00000000000191",
        "BRTEST - 1",
        kind,
        "ADM",
        quantity,
        quantity,
        "-",
        "-",
        close,
        quantity * close,
    ]


def _bdr(code, quantity, close):
    return [
        f"{code} - EMPRESA {code}",
        INSTITUTION,
        "1",
        code,
        "BRTEST - 1",
        "BDR",
        "BANCO",
        quantity,
        quantity,
        "-",
        "-",
        close,
        quantity * close,
    ]


def _cdb(code, issuer, index, issued, maturity, value, kind="CDB"):
    return [
        f"{kind} - {issuer}",
        INSTITUTION,
        issuer,
        code,
        index,
        "DEPOSITADO",
        br(issued),
        br(maturity),
        1,
        1,
        "-",
        "-",
        "-",
        "-",
        "-",
        value,
        value,
        "-",
        "-",
    ]


def position_report(today=None):
    """Patrimônio de R$ 4.580,00: BANK3 200, AGUA3 100, LOGI11 300, SHOP11 100, INDX11 160, TECH34 80, RF 3.640."""
    today = today or date.today()
    near = today + timedelta(days=NEAR_MATURITY_DAYS)
    far = today + timedelta(days=FAR_MATURITY_DAYS)
    issued = today - timedelta(days=365)
    return _workbook(
        {
            "Acoes": [STOCK_HEADER, _stock("BANK3", 10, 20.0), _stock("AGUA3", 10, 10.0)],
            "BDR": [BDR_HEADER, _bdr("TECH34", 2, 40.0)],
            "ETF": [FUND_HEADER, _fund("INDX11", 2, 80.0, "Ações")],
            "Fundo de Investimento": [FUND_HEADER, _fund("LOGI11", 3, 100.0), _fund("SHOP11", 2, 50.0)],
            "Renda Fixa": [
                RF_HEADER,
                _cdb("CDBFICT1", "BANCO ALFA S/A", "PREFIXADO", issued, near, 1100.0),
                _cdb("CDBFICT2", "BANCO BETA S/A", "IPCA", issued, far, 1540.0),
            ],
            "Tesouro Direto": [
                TD_HEADER,
                [
                    "Tesouro Selic 2099",
                    INSTITUTION,
                    "BRSTNFICT",
                    "SELIC",
                    "01/03/2099",
                    0.5,
                    0.5,
                    0,
                    "-",
                    900.0,
                    1000.0,
                    990.0,
                    1000.0,
                ],
            ],
        }
    )


def position_filename(today=None):
    return f"posicao-{(today or date.today()).isoformat()}-10-00-00.xlsx"


def _move(day, kind, product, quantity, price="-", value="-", direction="Credito"):
    return [direction, br(day), kind, product, INSTITUTION, quantity, price, value]


def movement_rows(today=None):
    """Histórico coerente com `position_report`, com compra, venda, desdobro, proventos e renda fixa."""
    today = today or date.today()
    start = today - timedelta(days=365)
    rows = [
        _move(start, "Transferência - Liquidação", "BANK3 - EMPRESA BANK3", 5, 16.0, 80.0),
        _move(start + timedelta(days=40), "Transferência - Liquidação", "BANK3 - EMPRESA BANK3", 7, 15.0, 105.0),
        _move(
            start + timedelta(days=60), "Transferência - Liquidação", "BANK3 - EMPRESA BANK3", 2, 18.0, 36.0, "Debito"
        ),
        _move(start, "Transferência - Liquidação", "AGUA3 - EMPRESA AGUA3", 5, 16.0, 80.0),
        _move(start + timedelta(days=50), "Desdobro", "AGUA3 - EMPRESA AGUA3", 5),
        _move(start, "Transferência - Liquidação", "LOGI11 - FUNDO LOGI11", 3, 90.0, 270.0),
        _move(start, "Transferência - Liquidação", "SHOP11 - FUNDO SHOP11", 2, 45.0, 90.0),
        _move(start, "Transferência - Liquidação", "INDX11 - FUNDO INDX11", 2, 70.0, 140.0),
        _move(start, "Transferência - Liquidação", "TECH34 - EMPRESA TECH34", 2, 35.0, 70.0),
        _move(start, "COMPRA / VENDA", "CDB - CDBFICT1 - BANCO ALFA S/A", 1, 1000.0, 1000.0),
        _move(start, "COMPRA / VENDA", "CDB - CDBFICT2 - BANCO BETA S/A", 1, 1400.0, 1400.0),
        _move(start, "Compra", "Tesouro Selic 2099", 0.5, 1800.0, 900.0),
        _move(today - timedelta(days=400), "Rendimento", "LOGI11 - FUNDO LOGI11", 3, 1.0, 3.0),
        _move(today - timedelta(days=40), "Rendimento", "LOGI11 - FUNDO LOGI11", 3, 1.0, 3.0),
        _move(today - timedelta(days=10), "Dividendo", "BANK3 - EMPRESA BANK3", 10, 1.0, 10.0),
        _move(today - timedelta(days=12), "Juros Sobre Capital Próprio", "BANK3 - EMPRESA BANK3", 10, 0.5, 5.0),
    ]
    return rows


def movement_report(rows=None):
    return _workbook({"Movimentação": [MOVEMENT_HEADER, *(rows if rows is not None else movement_rows())]})


MOVEMENT_FILENAME = "movimentacao-teste.xlsx"
