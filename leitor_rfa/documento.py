"""Monta o documento no esquema v1 do extrator, com a cobertura do leitor."""
import datetime as dt
import hashlib
import pathlib

from .cobertura import Cobertura
from .contenedor import abrir
from .compressao import ErroCompressao, inflar_stream, preparar
from .elementos import montar_elementos
from .elemtable import ErroElemTable, ler_elemtable
from .esquema import ErroEsquema, ler_esquema
from .formas import ler_formas
from .grafo import ErroGrafo
from .parametros import ler_parametros
from .referencias import ler_aninhadas, ler_cotas, ler_planos
from .registros import ErroRegistro, objetos
from .info_basica import ler_info_basica
from .miniatura import extrair_png
from .partatom import ErroPartAtom, ler_partatom
from .segmentos import ErroSegmento, percorrer_particao


def _sha256(caminho):
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _partatom(bruto, doc, cob):
    if bruto is None:
        cob.marcar("familia", "parcial", "nome = nome do arquivo; sem PartAtom, a categoria virá das partições")
        cob.marcar("tipos", "nao_decifrado", "arquivo sem PartAtom; os tipos dependem das partições, ainda não decifradas nesta versão")
        return
    try:
        pa = ler_partatom(bruto)
    except ErroPartAtom as exc:
        cob.erro("familia", exc)
        cob.marcar("familia", "parcial", "nome = nome do arquivo; PartAtom ilegível")
        cob.marcar("tipos", "nao_decifrado", "PartAtom ilegível")
        return
    doc["tipos"] = {nome: {} for nome in pa.tipos}
    doc["partatom"] = {
        "titulo": pa.titulo,
        "categoria": pa.categoria,
        "omniclass": pa.omniclass,
        "versao_produto": pa.versao_produto,
        "tipos": {t: {p.nome: {"valor": p.valor, "unidade": p.unidade, "tipo": p.tipo, "guid": p.guid,
                               "tipo_parametro": p.tipo_parametro} for p in ps}
                  for t, ps in pa.tipos.items()},
    }
    cob.versao_partatom = pa.versao_produto
    cob.marcar("familia", "parcial",
               "nome = nome do arquivo (regra do Revit); categoria no idioma em que o arquivo foi salvo, "
               "em partatom.categoria")
    nota = "nomes dos tipos do PartAtom; os valores vêm das partições (os do PartAtom são de exibição, em partatom.tipos)"
    if list(pa.tipos) == [doc["familia"]["nome"]]:
        nota += ("; parte única com o nome da família: pode ser o tipo implícito de uma família sem tipos "
                 "(o PartAtom não distingue; as partições confirmam)")
    cob.marcar("tipos", "parcial", nota)


def _miniatura(bruto, cob):
    if bruto is None:
        cob.marcar("miniatura", "ausente", "arquivo sem RevitPreview4.0")
        return None
    png = extrair_png(bruto)
    if png is None:
        cob.marcar("miniatura", "nao_decifrado", "RevitPreview4.0 sem PNG completo")
    else:
        cob.marcar("miniatura", "decifrado", f"PNG de {len(png)} B")
    return png


def _esquema(bruto, cob):
    if bruto is None:
        cob.marcar("esquema", "ausente", "arquivo sem Formats/Latest")
        return None
    try:
        e = ler_esquema(inflar_stream("Formats/Latest", bruto))
    except (ErroCompressao, ErroEsquema) as exc:
        cob.erro("esquema", exc)
        cob.marcar("esquema", "nao_decifrado", str(exc)[:300])
        return None
    cob.variante_esquema = e.variante
    cob.esquema = {"classes": len(e.classes), "sha256": e.sha256}
    cob.marcar("esquema", "decifrado", f"{len(e.classes)} classes, variante {e.variante}")
    return e


def _particoes(c, esquema, cob):
    nomes = [n for n in c.streams() if n.startswith("Partitions/")]
    if not nomes:
        cob.marcar("particoes", "ausente", "arquivo sem Partitions")
        return
    if esquema is None:
        cob.marcar("particoes", "nao_decifrado", "sem esquema não há etiquetas dos marcadores")
        return
    resumo = {"particoes": len(nomes), "lidas": 0, "grupos": 0, "segmentos": 0, "bytes_inflados": 0, "canais": {}}
    grupos = []
    for nome in nomes:
        try:
            p = percorrer_particao(preparar(nome, c.ler(nome)), esquema)
        except ErroSegmento as exc:
            cob.erro("particoes", ErroSegmento(f"{nome}: {exc}"))
            continue
        resumo["lidas"] += 1
        grupos.extend(p.grupos)
        resumo["grupos"] += len(p.grupos)
        resumo["segmentos"] += p.segmentos
        resumo["bytes_inflados"] += p.bytes_inflados
        for g in p.grupos:
            resumo["canais"][str(g.canal)] = resumo["canais"].get(str(g.canal), 0) + 1
    cob.particoes = resumo
    estado = "decifrado" if resumo["lidas"] == len(nomes) else "parcial" if resumo["lidas"] else "nao_decifrado"
    cob.marcar("particoes", estado,
               f"enquadramento: {resumo['lidas']}/{len(nomes)} partições até o marcador final, {resumo['grupos']} grupos, "
               f"{resumo['segmentos']} segmentos")
    return grupos if estado == "decifrado" else None


def _elementos(c, esquema, grupos, cob):
    if esquema is None or grupos is None:
        cob.marcar("elementos", "nao_decifrado", "sem esquema ou sem partições legíveis até o fim")
        return
    try:
        et = ler_elemtable(inflar_stream("Global/ElemTable", c.ler("Global/ElemTable")), esquema)
        bruto_latest = c.ler("Global/Latest")
        el = montar_elementos(grupos, et, esquema, inflar_stream("Global/Latest", bruto_latest) if bruto_latest else b"")
    except (ErroCompressao, ErroElemTable, ErroRegistro) as exc:
        cob.erro("elementos", exc)
        cob.marcar("elementos", "nao_decifrado", str(exc)[:300])
        return
    doc = el.documento()
    cob.elementos = {"largura_id": el.largura_id, "registros": len(et.donos), "com_classe": len(el.classe),
                     "documento": len(doc), "raiz": el.raiz, "contagens": el.contagens(), "por_classe": el.por_classe()}
    if el.raiz is None:
        cob.marcar("elementos", "parcial", "família raiz não identificada; contagens do documento vazias")
        return None
    cob.marcar("elementos", "decifrado", f"{len(el.classe)} elementos com classe, {len(doc)} do documento principal")
    corpos = {o.id: o.corpo for g in grupos if g.canal == 102 and g.chave_conteudo is None
              for o in objetos(g.dados, et.largura_id)}
    return el, corpos


def _parametros(lidos, esquema, doc, cob):
    """Preenche parâmetros e tipos; devolve {id do parâmetro: nome} para os rótulos das cotas."""
    if lidos is None:
        return {}
    el, corpos = lidos
    try:
        r = ler_parametros(corpos, el.raiz, esquema, doc["familia"]["nome"])
    except (ErroGrafo, KeyError, TypeError) as exc:
        cob.erro("parametros", exc)
        cob.marcar("parametros", "nao_decifrado", f"{type(exc).__name__}: {str(exc)[:200]}")
        return {}
    doc["parametros"] = r["parametros"]
    doc["familia"]["categoria_id"] = r["categoria_id"]
    cob.parametros_inferidos = r["inferidos"]
    do_arquivo = len(r["parametros"]) - len(r["inferidos"])
    nota = (f"{do_arquivo} do arquivo + {len(r['inferidos'])} inferidos (acrescentados pelo Revit 2025 por "
            f"categoria/IFC, em parametros_inferidos)")
    if r["desconhecidos"]:
        nota += f"; {len(r['desconhecidos'])} embutidos sem nome conhecido: {r['desconhecidos'][:5]}"
    if r["grupos_sem_rotulo"]:
        nota += (f"; grupo nulo: o Revit 2022+ grava o grupo como ForgeTypeId, sem tabela de rótulo "
                 f"({', '.join(r['grupos_sem_rotulo'][:4])})")
    cob.marcar("parametros", "parcial" if r["desconhecidos"] or r["grupos_sem_rotulo"] else "decifrado", nota)
    doc["tipos"] = r["tipos"]
    cob.marcar("tipos", "decifrado", "nomes e valores da FamilyTypeTable (bruto em unidade interna; "
                                     "valores de material e dos parâmetros inferidos ainda não)")
    return r["nomes"]


def _referencias(lidos, esquema, doc, cob, nomes):
    if lidos is None:
        return
    el, corpos = lidos
    try:
        doc["planos_referencia"] = ler_planos(el, corpos, esquema)
    except (ErroGrafo, KeyError) as exc:
        cob.erro("planos_referencia", exc)
        cob.marcar("planos_referencia", "nao_decifrado", f"{type(exc).__name__}: {str(exc)[:200]}")
    else:
        cob.marcar("planos_referencia", "parcial", "nome e referência; extremos (inicio_mm/fim_mm) ainda não")
    doc["cotas"], falhas = ler_cotas(el, corpos, esquema, nomes)
    if falhas:
        cob.marcar("cotas", "parcial", f"{len(doc['cotas'])} lidas; {len(falhas)} sem decodificação do grafo: {falhas[:5]}")
    else:
        cob.marcar("cotas", "decifrado", f"{len(doc['cotas'])} cotas: rótulo, valor (lineares de um segmento) e nº de referências")
    doc["aninhadas"], falhas = ler_aninhadas(el, corpos, esquema)
    sem_categoria = sum(a["categoria"] is None for a in doc["aninhadas"])
    if falhas or sem_categoria:
        cob.marcar("aninhadas", "parcial", f"{len(falhas)} instâncias sem símbolo/família legível {falhas[:5]}; "
                                           f"{sem_categoria} grupos com categoria fora da tabela aprendida")
    else:
        n = sum(a["quantidade"] for a in doc["aninhadas"])
        cob.marcar("aninhadas", "decifrado", f"{len(doc['aninhadas'])} grupos, {n} instâncias: família, tipo, "
                                             "categoria (tabela aprendida), compartilhada, quantidade")


def _formas(lidos, esquema, doc, cob, nomes):
    if lidos is None:
        return
    el, corpos = lidos
    doc["formas"], falhas = ler_formas(el, corpos, esquema, nomes)
    n = len(doc["formas"])
    if falhas:
        cob.marcar("formas", "parcial", f"{n - len(falhas)}/{n} formas lidas; sem decodificação: {falhas[:5]}")
    else:
        cob.marcar("formas", "decifrado", f"{n} formas: tipo, sólido, material, início/fim (extrusão) e esboço "
                                          "(extrusão e revolução, tesselado como o Revit)")


def ler_com_miniatura(caminho, nome_arquivo=None):
    """Lê o .rfa e devolve (documento, png | None). `nome_arquivo`: nome com que a família está na biblioteca, quando o arquivo
    lido é uma cópia renomeada (o nome da família no Revit é o nome do arquivo)."""
    caminho = pathlib.Path(caminho)
    cob = Cobertura()
    nome = pathlib.PureWindowsPath(nome_arquivo).stem if nome_arquivo else caminho.stem
    doc = {
        "versao_esquema": 1,
        "origem": {"caminho": str(caminho), "sha256": _sha256(caminho), "tamanho": caminho.stat().st_size},
        "extraido_em": dt.datetime.now().astimezone().isoformat(),
        "familia": {"nome": nome, "categoria": None, "categoria_id": None, "posicionamento": None},
        "parametros": [],
        "tipos": {},
        "aninhadas": [],
        "planos_referencia": [],
        "cotas": [],
        "formas": [],
        "geometria": None,
        "importacoes": None,
        "ifc": None,
        "partatom": None,
    }
    with abrir(caminho) as c:
        info = ler_info_basica(c.ler("BasicFileInfo"))
        cob.versao_formato, cob.build = info.versao_formato, info.build
        _partatom(c.ler("PartAtom"), doc, cob)
        png = _miniatura(c.ler("RevitPreview4.0"), cob)
        esquema = _esquema(c.ler("Formats/Latest"), cob)
        grupos = _particoes(c, esquema, cob)
        lidos = _elementos(c, esquema, grupos, cob)
        nomes = _parametros(lidos, esquema, doc, cob)
        _referencias(lidos, esquema, doc, cob, nomes)
        _formas(lidos, esquema, doc, cob, nomes)
    doc["cobertura"] = cob.como_dict()
    return doc, png


def ler(caminho, nome_arquivo=None):
    return ler_com_miniatura(caminho, nome_arquivo)[0]
