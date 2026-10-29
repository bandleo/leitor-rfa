"""ler-rfa visualizar: servidor local (só biblioteca padrão) da página do leitor e da API que ela usa.

uso: ler-rfa visualizar [arquivo.rfa] [--porta 8765] [--sem-navegador]

Rotas:
  GET  /                        a página (leitor_rfa/web, gerada por `npm run build` em web/)
  POST /api/ler                 corpo = bytes do .rfa; cabeçalho X-Nome = nome do arquivo (codificado como URL)
                                → {id, nome, familia (familia.json v1), miniatura: bool}
  GET  /api/<id>                a mesma resposta de novo
  GET  /api/<id>/modelo.glb     o 3D (B-rep salvo pelo Revit), com o que o Revit oculta marcado; feito uma vez
  GET  /api/<id>/miniatura.png  a miniatura gravada pelo Revit
  GET  /api/<id>/bimcraft.zip   a família do BIMCraft (<nome>.json) e os dados de texto e o relatório (<nome>-dados.json)

Só escuta em 127.0.0.1. Os .rfa recebidos ficam numa pasta temporária, apagada ao sair: nada sai da máquina.
O 3D começa num processo à parte assim que o arquivo chega, junto com a leitura dos dados (os dois são Python
puro: em threads um esperaria o outro), e fica pronto perto de quando a página o pede.
"""
import argparse
import hashlib
import io
import json
import mimetypes
import pathlib
import re
import shutil
import sys
import tempfile
import threading
import traceback
import urllib.parse
import webbrowser
import zipfile
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .bimcraft import converter
from .documento import ler_com_miniatura
from .malha import para_glb, partes

WEB = pathlib.Path(__file__).with_name("web")
OLE = bytes.fromhex("D0CF11E0A1B11AE1")
LIMITE = 300 * 1024 * 1024  # bytes de um .rfa recebido
ID = re.compile(r"^[0-9a-f]{16}$")
TIPOS = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".json": "application/json",
         ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8"}


def nome_seguro(bruto):
    """Nome de arquivo vindo do navegador (X-Nome, codificado como URL) → só o nome, sem pasta nem caracteres
    proibidos no Windows, terminando em .rfa."""
    nome = re.split(r"[\\/]", urllib.parse.unquote(bruto or ""))[-1]
    nome = re.sub(r'[<>:"|?*\x00-\x1f]', "_", nome).strip(" .")
    if not nome:
        return "familia.rfa"
    if not nome.lower().endswith(".rfa"):
        nome = nome[:120] + ".rfa"
    return nome if len(nome) <= 124 else nome[:120] + nome[-4:]


class ErroPedido(Exception):
    def __init__(self, status, mensagem):
        super().__init__(mensagem)
        self.status = status


def _glb_do_arquivo(caminho):
    return para_glb(partes(pathlib.Path(caminho), incluir_ocultas=True))


def _pronto():
    return True


class Biblioteca:
    """As famílias recebidas nesta execução, por id (16 primeiros hex do sha256 do arquivo)."""

    def __init__(self, processos=True):
        self.pasta = pathlib.Path(tempfile.mkdtemp(prefix="leitor-rfa-"))
        self.itens = {}
        self.trava = threading.Lock()
        self.processos = None
        if processos:
            try:
                self.processos = ProcessPoolExecutor(max_workers=1)
                self.processos.submit(_pronto)  # sobe o processo já: no Windows abrir um custa ~1 s
            except (OSError, ValueError, NotImplementedError):
                self.processos = None

    def ler(self, dados, nome):
        if not dados.startswith(OLE):
            raise ErroPedido(HTTPStatus.BAD_REQUEST, "não é um .rfa: o arquivo do Revit é um contêiner OLE")
        sha = hashlib.sha256(dados).hexdigest()
        i = sha[:16]
        with self.trava:
            item = self.itens.get(i)
            if item is None:
                caminho = self.pasta / f"{i}.rfa"
                caminho.write_bytes(dados)
                item = self.itens[i] = {"caminho": caminho, "sha256": sha, "trava": threading.Lock()}
                if self.processos is not None:
                    try:
                        item["futuro"] = self.processos.submit(_glb_do_arquivo, str(caminho))
                    except (BrokenProcessPool, RuntimeError):
                        self.processos = None
        with item["trava"]:
            if item.get("nome") != nome:
                try:
                    doc, png = ler_com_miniatura(item["caminho"], nome_arquivo=nome)
                except Exception as exc:  # o que vier de um arquivo ruim vira uma mensagem para a página
                    traceback.print_exc()
                    raise ErroPedido(HTTPStatus.UNPROCESSABLE_ENTITY, f"não foi possível ler a família: {exc}") from exc
                doc["origem"]["caminho"] = nome
                item.update(nome=nome, doc=doc, png=png, bimcraft=None)
            return self.resposta(i)

    def item(self, i):
        item = self.itens.get(i) if ID.match(i or "") else None
        if item is None or "doc" not in item:
            raise ErroPedido(HTTPStatus.NOT_FOUND, "família não encontrada (leia o .rfa de novo)")
        return item

    def resposta(self, i):
        item = self.item(i)
        return {"id": i, "nome": item["nome"], "familia": item["doc"], "miniatura": item["png"] is not None}

    def glb(self, i):
        item = self.item(i)
        with item["trava"]:
            if item.get("glb") is None:
                futuro = item.pop("futuro", None)
                try:
                    item["glb"] = futuro.result() if futuro is not None else None
                except BrokenProcessPool:
                    item["glb"] = None
                if item["glb"] is None:
                    item["glb"] = _glb_do_arquivo(item["caminho"])
            return item["glb"]

    def miniatura(self, i):
        png = self.item(i)["png"]
        if png is None:
            raise ErroPedido(HTTPStatus.NOT_FOUND, "o arquivo não traz miniatura")
        return png

    def bimcraft(self, i):
        item = self.item(i)
        with item["trava"]:
            if item.get("bimcraft") is None:
                familia, rel = converter(item["doc"])
                base = pathlib.PurePath(item["nome"]).stem
                dados = {"entrada": item["nome"], "rfa_sha256": item["sha256"], **rel}
                saida = io.BytesIO()
                with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as z:
                    z.writestr(f"{base}.json", json.dumps(familia, ensure_ascii=False, indent=1))
                    z.writestr(f"{base}-dados.json", json.dumps(dados, ensure_ascii=False, indent=1))
                item["bimcraft"] = (f"{base}-bimcraft.zip", saida.getvalue())
            return item["bimcraft"]

    def fechar(self):
        if self.processos is not None:
            self.processos.shutdown(wait=True, cancel_futures=True)
        shutil.rmtree(self.pasta, ignore_errors=True)


class Pedido(BaseHTTPRequestHandler):
    server_version = "leitor-rfa"
    protocol_version = "HTTP/1.1"

    def log_message(self, formato, *args):
        if not self.server.silencioso:
            sys.stderr.write(f"ler-rfa visualizar: {formato % args}\n")

    def do_GET(self):
        self._tratar(self._get)

    def do_POST(self):
        self._tratar(self._post)

    def _tratar(self, fn):
        try:
            fn(urllib.parse.urlsplit(self.path).path)
        except ErroPedido as exc:
            self._json({"erro": str(exc)}, exc.status)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:  # erro do leitor: a página recebe a mensagem em vez de uma conexão cortada
            traceback.print_exc()
            self._json({"erro": f"falha interna: {exc}"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def _get(self, rota):
        bib = self.server.biblioteca
        m = re.fullmatch(r"/api/([^/]*)(?:/(modelo\.glb|miniatura\.png|bimcraft\.zip))?", rota)
        if m:
            i, recurso = m.groups()
            if recurso is None:
                return self._json(bib.resposta(i))
            if recurso == "modelo.glb":
                return self._enviar(bib.glb(i), "model/gltf-binary")
            if recurso == "miniatura.png":
                return self._enviar(bib.miniatura(i), "image/png")
            nome, dados = bib.bimcraft(i)
            return self._enviar(dados, "application/zip",
                                {"Content-Disposition": f"attachment; filename*=UTF-8''{urllib.parse.quote(nome)}"})
        if rota.startswith("/api/"):
            raise ErroPedido(HTTPStatus.NOT_FOUND, "rota desconhecida")
        self._estatico(rota)

    def _post(self, rota):
        if rota != "/api/ler":
            raise ErroPedido(HTTPStatus.NOT_FOUND, "rota desconhecida")
        tamanho = self.headers.get("Content-Length")
        if tamanho is None:
            raise ErroPedido(HTTPStatus.LENGTH_REQUIRED, "falta o tamanho do arquivo")
        if int(tamanho) > LIMITE:
            raise ErroPedido(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"arquivo maior que {LIMITE // 2**20} MB")
        dados = self.rfile.read(int(tamanho))
        self._json(self.server.biblioteca.ler(dados, nome_seguro(self.headers.get("X-Nome"))))

    def _estatico(self, rota):
        raiz = self.server.pasta_web.resolve()
        relativo = urllib.parse.unquote(rota).lstrip("/") or "index.html"
        alvo = (raiz / relativo).resolve()
        if raiz not in alvo.parents or not alvo.is_file():
            if not (raiz / "index.html").is_file():
                raise ErroPedido(HTTPStatus.SERVICE_UNAVAILABLE, "página não empacotada: rode `npm run build` em web/")
            raise ErroPedido(HTTPStatus.NOT_FOUND, "não encontrado")
        tipo = TIPOS.get(alvo.suffix.lower()) or mimetypes.guess_type(alvo.name)[0] or "application/octet-stream"
        self._enviar(alvo.read_bytes(), tipo)

    def _json(self, obj, status=HTTPStatus.OK):
        self._enviar(json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status=status)

    def _enviar(self, dados, tipo, cabecalhos=None, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (cabecalhos or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)


def criar_servidor(porta=8765, pasta_web=WEB, silencioso=True, processos=True):
    srv = ThreadingHTTPServer(("127.0.0.1", porta), Pedido)
    srv.daemon_threads = True
    srv.biblioteca, srv.pasta_web, srv.silencioso = Biblioteca(processos), pathlib.Path(pasta_web), silencioso
    return srv


def main(argv=None):
    p = argparse.ArgumentParser(prog="ler-rfa visualizar",
                                description="Abre no navegador a página do leitor: solte um .rfa, veja os dados e o 3D, "
                                            "exporte a família BIMCraft. Tudo local.")
    p.add_argument("arquivo", nargs="?", help="um .rfa para já abrir")
    p.add_argument("--porta", type=int, default=8765, help="porta local (padrão 8765; 0 = qualquer livre)")
    p.add_argument("--sem-navegador", action="store_true", help="não abre o navegador")
    a = p.parse_args(argv)
    try:
        srv = criar_servidor(a.porta, silencioso=False)
    except OSError:
        srv = criar_servidor(0, silencioso=False)  # porta ocupada: qualquer outra livre
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    if a.arquivo:
        caminho = pathlib.Path(a.arquivo)
        try:
            r = srv.biblioteca.ler(caminho.read_bytes(), nome_seguro(urllib.parse.quote(caminho.name)))
        except (OSError, ErroPedido) as exc:
            print(f"ler-rfa visualizar: {exc}", file=sys.stderr)
            srv.server_close()
            srv.biblioteca.fechar()
            return 1
        url += f"#{r['id']}"
    print(f"ler-rfa visualizar: {url}  (Ctrl+C para sair)", flush=True)
    if not a.sem_navegador:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        srv.biblioteca.fechar()
    return 0
