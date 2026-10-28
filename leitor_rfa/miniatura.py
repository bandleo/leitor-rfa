"""Miniatura: o RevitPreview4.0 traz um cabeçalho e, depois, um PNG inteiro."""
ASSINATURA = b"\x89PNG\r\n\x1a\n"


def extrair_png(dados):
    """PNG da assinatura até o fim do chunk IEND (+4 B de CRC), ou None."""
    if not dados:
        return None
    inicio = dados.find(ASSINATURA)
    if inicio < 0:
        return None
    iend = dados.find(b"IEND", inicio + len(ASSINATURA))
    if iend < 0 or iend + 8 > len(dados):
        return None
    return dados[inicio:iend + 8]
