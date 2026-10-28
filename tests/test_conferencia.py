import json
import shutil

from leitor_rfa.conferencia import Resultado, agregar, comparar, conferir_partatom, esboco_igual, main


def cob(**estados):
    return {"versao_formato": 2012, "secoes": {k: {"estado": v} for k, v in estados.items()}}


def test_tipos_nomes_iguais():
    r = comparar({"tipos": {"A": {}, "B": {}}, "cobertura": cob(tipos="parcial")}, {"tipos": {"A": {}, "B": {}}})
    assert r["tipos.nomes"] == Resultado(2, 2, "parcial")


def test_tipo_a_mais_conta_contra():
    r = comparar({"tipos": {"A": {}, "X": {}}, "cobertura": cob(tipos="parcial")}, {"tipos": {"A": {}}})
    assert r["tipos.nomes"] == Resultado(1, 2, "parcial")


def test_secao_nao_decifrada_nao_conta_como_erro():
    r = comparar({"parametros": [], "cobertura": cob(parametros="nao_decifrado")}, {"parametros": [{"nome": "x"}]})
    assert r["parametros"].estado == "nao_decifrado" and r["parametros"].iguais == 0


def test_lista_nao_decifrada_nunca_vale_como_acerto():
    cota = {"rotulo": None, "valor_mm": None, "referencias": 2}
    r = comparar({"cotas": [cota], "cobertura": cob(cotas="nao_decifrado")}, {"cotas": [cota]})
    assert r["cotas"] == Resultado(0, 3, "nao_decifrado")


def test_cotas_campo_a_campo_com_tolerancia_em_mm():
    gab = {"cotas": [{"rotulo": None, "valor_mm": 34.87500000004967, "referencias": 2},
                     {"rotulo": "L", "valor_mm": None, "referencias": 3}]}
    doc = {"cotas": [{"rotulo": None, "valor_mm": 34.8750000000001, "referencias": 2},
                     {"rotulo": None, "valor_mm": None, "referencias": 3}], "cobertura": cob(cotas="decifrado")}
    assert comparar(doc, gab)["cotas"] == Resultado(5, 6, "decifrado")


def test_item_a_mais_na_lista_conta_contra():
    cota = {"rotulo": None, "valor_mm": None, "referencias": 2}
    r = comparar({"cotas": [cota, cota], "cobertura": cob(cotas="decifrado")}, {"cotas": [cota]})
    assert r["cotas"] == Resultado(3, 6, "decifrado")


def test_planos_nome_e_referencia_e_extremos_nd_enquanto_parcial():
    gab = {"planos_referencia": [{"nome": "A", "referencia": "Fraca", "inicio_mm": [1.0, 2.0, 3.0], "fim_mm": [4.0, 5.0, 6.0]}]}
    doc = {"planos_referencia": [{"nome": "A", "referencia": "Fraca", "inicio_mm": None, "fim_mm": None}],
           "cobertura": cob(planos_referencia="parcial")}
    r = comparar(doc, gab)
    assert r["planos_referencia"] == Resultado(2, 2, "parcial")
    assert r["planos.extremos"] == Resultado(0, 2, "nao_decifrado")


def test_extremos_comparados_quando_planos_decifrados():
    plano = {"nome": "A", "referencia": "Fraca", "inicio_mm": [1.0, 2.0, 3.0], "fim_mm": [4.0, 5.0, 6.0]}
    doc = {"planos_referencia": [dict(plano, fim_mm=[4.0, 5.0, 7.0])], "cobertura": cob(planos_referencia="decifrado")}
    assert comparar(doc, {"planos_referencia": [plano]})["planos.extremos"] == Resultado(1, 2, "decifrado")


def test_aninhadas_campo_a_campo():
    a = {"familia": "F", "tipo": "T", "categoria": "C", "compartilhada": True, "quantidade": 20}
    doc = {"aninhadas": [dict(a, quantidade=19)], "cobertura": cob(aninhadas="decifrado")}
    assert comparar(doc, {"aninhadas": [a]})["aninhadas"] == Resultado(4, 5, "decifrado")


def test_parametros_conta_campo_a_campo():
    p = {"nome": "D", "grupo": "G", "instancia": False, "compartilhado": True, "guid": "g",
         "tipo_dado": "t", "formula": None, "reporting": False}
    errado = dict(p, grupo="Outro")
    r = comparar({"parametros": [errado], "cobertura": cob(parametros="decifrado")}, {"parametros": [p]})
    assert r["parametros"] == Resultado(6, 7, "decifrado")


def test_formulas_compara_texto_normalizando_espacos():
    gab = {"parametros": [{"nome": "D", "formula": "R * 2"}, {"nome": "E", "formula": None}]}
    doc = {"parametros": [{"nome": "D", "formula": "R*2"}], "cobertura": cob(parametros="decifrado")}
    assert comparar(doc, gab)["formulas"] == Resultado(1, 1, "decifrado")


def test_tipos_valores_compara_bruto():
    gab = {"tipos": {"T": {"a": {"bruto": 0.5}, "b": {"bruto": "x"}}}}
    doc = {"tipos": {"T": {"a": {"bruto": 0.5}, "b": {"bruto": "y"}}}, "cobertura": cob(tipos="decifrado")}
    assert comparar(doc, gab)["tipos.valores"] == Resultado(1, 2, "decifrado")


def _doc_com_contagens(contagens, estado="decifrado"):
    c = cob(elementos=estado)
    c["elementos"] = {"contagens": contagens} if estado != "nao_decifrado" else None
    return {"cobertura": c}


GAB_CONTAGEM = {"planos_referencia": [{}] * 3, "cotas": [{}] * 2, "formas": [{"tipo": "Extrusion"}, {"tipo": "Sweep"}],
                "aninhadas": [{"quantidade": 2}, {"quantidade": 1}]}


def test_contagem_por_classe_igual():
    doc = _doc_com_contagens({"planos": 3, "cotas": 2, "aninhadas": 3, "formas": {"Extrusion": 1, "Sweep": 1}})
    r = comparar(doc, GAB_CONTAGEM)
    assert [r[k] for k in ("contagem.planos", "contagem.cotas", "contagem.formas", "contagem.aninhadas", "contagem.todas")] \
        == [Resultado(1, 1, "decifrado")] * 5


def test_contagem_por_classe_diferente_derruba_todas():
    doc = _doc_com_contagens({"planos": 3, "cotas": 1, "aninhadas": 3, "formas": {"Extrusion": 1, "Sweep": 1}})
    r = comparar(doc, GAB_CONTAGEM)
    assert r["contagem.cotas"] == Resultado(0, 1, "decifrado") and r["contagem.todas"] == Resultado(0, 1, "decifrado")


def test_contagem_sem_elementos_fica_nd():
    r = comparar(_doc_com_contagens(None, "nao_decifrado"), GAB_CONTAGEM)
    assert r["contagem.todas"] == Resultado(0, 1, "nao_decifrado")


def test_agregar_soma_por_versao():
    r1 = {"tipos.nomes": Resultado(2, 2, "parcial")}
    r2 = {"tipos.nomes": Resultado(1, 2, "parcial")}
    tab = agregar([(2012, r1), (2012, r2), (2018, r1)])
    assert tab[2012]["tipos.nomes"] == {"iguais": 3, "total": 4, "arquivos": 2, "estados": {"parcial": 2}}
    assert tab[2018]["tipos.nomes"]["iguais"] == 2


def test_main_sobre_pasta_de_gabarito(fixtura, tmp_path, capsys):
    for nome in ("r2012", "r2018"):
        d = tmp_path / "gab" / nome
        d.mkdir(parents=True)
        for arq in ("familia.rfa", "familia.json"):
            shutil.copy(fixtura(nome) / arq, d / arq)
    saida = tmp_path / "conf.json"
    assert main(["--gabarito", str(tmp_path / "gab"), "-o", str(saida)]) == 0
    rel = json.loads(saida.read_text(encoding="utf-8"))
    assert rel["arquivos"] == 2 and rel["erros"] == []
    nomes = [s["familia.nome"]["iguais"] for s in rel["por_versao"].values()]
    assert sum(nomes) == 2
    assert "tipos.nomes" in capsys.readouterr().out


QUADRADO = [[[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0], [10.0, 10.0, 0.0], [0.0, 0.0, 0.0]]]


def test_esboco_igual_nao_depende_do_inicio_nem_do_sentido():
    outro = [[[10.0, 10.0, 0.0], [10.0, 0.0, 0.0], [10.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [10.0, 10.0, 0.0]]]
    assert esboco_igual(outro, QUADRADO)


def test_esboco_tolera_0_1_mm():
    perto = [[[x + 0.05, y, z] for x, y, z in QUADRADO[0]]]
    longe = [[[x + 0.2, y, z] for x, y, z in QUADRADO[0]]]
    assert esboco_igual(perto, QUADRADO) and not esboco_igual(longe, QUADRADO)


def test_esboco_com_laco_ou_ponto_a_mais_e_diferente():
    assert not esboco_igual(QUADRADO + QUADRADO, QUADRADO)
    assert not esboco_igual([QUADRADO[0] + [[5.0, 5.0, 0.0]]], QUADRADO)
    assert esboco_igual([], [])


def test_conferencia_conta_formas_com_esboco_igual():
    forma = {"tipo": "Extrusion", "solido": True, "parametro_visivel": None, "parametro_material": None,
             "esboco_mm": QUADRADO, "inicio_mm": 0, "fim_mm": 10.0}
    doc = {"formas": [forma, dict(forma, esboco_mm=[])], "cobertura": cob(formas="decifrado")}
    r = comparar(doc, {"formas": [forma, forma]})
    assert r["formas"] == Resultado(12, 12, "decifrado")
    assert r["formas.esboco"] == Resultado(1, 2, "decifrado")



def _pa(valor, tipo_parametro="Text", unidade=None):
    return {"valor": valor, "unidade": unidade, "tipo": "shared", "guid": None, "tipo_parametro": tipo_parametro}


def _lido(bruto, mm=None):
    return {"bruto": bruto, "texto": None, "mm": mm}


def _doc_pa(pa_tipos, tipos):
    return {"partatom": {"tipos": pa_tipos}, "tipos": tipos, "cobertura": cob(tipos="decifrado")}


def test_partatom_confere_nomes_dos_tipos():
    r = conferir_partatom(_doc_pa({"A": {}, "B": {}}, {"A": {}, "C": {}}))
    assert r["tipos"] == Resultado(1, 3, "decifrado")


def test_partatom_comprimento_na_precisao_exibida():
    doc = _doc_pa({"T": {"R": _pa("8", "Length", "mm"), "L": _pa("0.25", "Length", "m"), "X": _pa("9", "Length", "mm")}},
                  {"T": {"R": _lido(0.0246, 7.5), "L": _lido(0.82, 250.0), "X": _lido(0.0246, 7.5)}})
    r = conferir_partatom(doc)
    assert r["valores"] == Resultado(2, 3, "decifrado")


def test_partatom_texto_numero_e_sim_nao():
    doc = _doc_pa({"T": {"a": _pa("Fabricante X"), "b": _pa("0.58", "Number"), "c": _pa("Yes", "Yes/No"), "d": _pa("Não", "Yes/No")}},
                  {"T": {"a": _lido("Fabricante X"), "b": _lido(0.58), "c": _lido(1), "d": _lido(1)}})
    assert conferir_partatom(doc)["valores"] == Resultado(3, 4, "decifrado")


def test_partatom_separa_o_que_nao_da_para_comparar():
    doc = _doc_pa({"T": {"Manufacturer": _pa("Fabricante X"), "Mat": _pa("Aço", "Material"), "Q": _pa("2", "Flow", "L/s")}},
                  {"T": {"Mat": _lido(None), "Q": _lido(0.07)}})
    r = conferir_partatom(doc)
    assert r["valores"] == Resultado(0, 0, "decifrado")
    assert r["fora"] == {"sem_par": 1, "sem_valor_lido": 1, "unidade_sem_conversao": 1}


def test_sem_partatom_nada_a_conferir():
    assert conferir_partatom({"partatom": None, "tipos": {}, "cobertura": cob(tipos="decifrado")}) is None


def test_partatom_valor_com_a_unidade_no_texto():
    doc = _doc_pa({"T": {"Raio": _pa("9 cm", "Comprimento", "cm"), "E": _pa("-4 cm", "Comprimento", "cm")}},
                  {"T": {"Raio": _lido(0.295, 90.0), "E": _lido(-0.131, -40.0)}})
    assert conferir_partatom(doc)["valores"] == Resultado(2, 2, "decifrado")


def test_partatom_tipo_implicito_com_nome_interno():
    pa = {"00112233445566778899aabbccddeeff": {"a": _pa("x")}}
    doc = dict(_doc_pa(pa, {"Fam": {"a": _lido("x")}}), familia={"nome": "Fam"})
    r = conferir_partatom(doc)
    assert r["tipos"] == Resultado(0, 0, "decifrado") and r["valores"] == Resultado(1, 1, "decifrado")
    assert r["fora"] == {"tipo_implicito": 1}
    vazio = dict(_doc_pa({"Fam.rfa_2": {"a": _pa("x")}}, {}), familia={"nome": "Fam"})
    assert conferir_partatom(vazio)["fora"] == {"tipo_implicito": 1}


def test_partatom_texto_com_quebra_de_linha_do_xml():
    doc = _doc_pa({"T": {"Info": _pa("linha 1\nlinha 2")}}, {"T": {"Info": _lido("linha 1\r\nlinha 2\r\n")}})
    assert conferir_partatom(doc)["valores"] == Resultado(1, 1, "decifrado")
