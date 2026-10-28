# leitor-rfa

Lê uma família do Revit (`.rfa`) **sem o Revit** e devolve um JSON com o que ela é: nome, categoria, tipos, parâmetros com valores e fórmulas, planos de referência, cotas, famílias aninhadas, formas (com o esboço) e a miniatura. Cada seção diz, no bloco `cobertura`, se foi decifrada, decifrada em parte ou não.

Python puro; a única dependência é o [`olefile`](https://pypi.org/project/olefile/). Roda no Windows e no Linux.

*English summary at the end.*

## Instalar e usar

```bash
pip install git+https://github.com/bandleo/leitor-rfa
ler-rfa familia.rfa -o familia.json --miniatura familia.png
```

Em Python:

```python
from leitor_rfa.documento import ler

doc = ler("familia.rfa")
doc["familia"]["nome"], list(doc["tipos"])
doc["cobertura"]["secoes"]["parametros"]["estado"]   # "decifrado" | "parcial" | "nao_decifrado"
```

Para pastas inteiras: `python -m leitor_rfa.lote <pasta> -o relatorio.json --jsons <saida>` grava um JSON por família e um resumo de cobertura por versão.

## O que sai no JSON (`versao_esquema: 1`)

| Seção | Conteúdo |
|---|---|
| `familia` | nome (o do arquivo, como o Revit faz) e categoria |
| `tipos` | cada tipo com o valor de cada parâmetro |
| `parametros` | nome, grupo, instância ou tipo, compartilhado (com GUID), tipo de dado e fórmula |
| `planos_referencia` | nome e tipo de referência (forte, fraca, centro…) |
| `cotas` | rótulo (parâmetro), valor em mm e número de referências |
| `aninhadas` | família, tipo, categoria, compartilhada e quantidade |
| `formas` | tipo (extrusão, revolução, varredura, mescla), sólido ou vazio, parâmetros de material e visibilidade ligados, início e fim, esboço em mm e plano do esboço |
| `partatom` | o que o próprio arquivo publica no PartAtom (título, categoria, OmniClass, tipos) |
| `cobertura` | versão do formato, esquema, partições e o estado de cada seção, com nota quando falta algo |

O esquema v1 é o mesmo que uma extração feita **de dentro do Revit** (pela API dele) grava para cada família; essa extração não faz parte deste repositório. É ela o **gabarito** dos testes e da conferência (`python -m leitor_rfa.conferencia --gabarito <pasta>`): pares `familia.rfa` + `familia.json` da mesma família. Quem tiver extrações assim pode usar `leitor_rfa.fonte.ler_familia(rfa, extracao=<pasta>)`, que completa com `<pasta>/<sha256 do .rfa>/familia.json` as seções que o leitor ainda não decifra e diz em `cobertura.origem` de onde veio cada uma.

## Cobertura

Medida campo a campo contra um gabarito de 106 famílias exportadas pelo próprio Revit e, fora dele, contra o PartAtom de cerca de 2.700 arquivos (1.824 de fabricantes, de 2010 a 2018, e 881 da biblioteca da Autodesk, de 2025), **sem nenhuma queda**:

| Seção | Acerto contra o Revit |
|---|---|
| Tipos | 141/141 |
| Parâmetros | 98,8% dos campos |
| Fórmulas | 96,3% das 1.892 (texto igual) |
| Planos de referência | 99,2% |
| Cotas | 97,5% |
| Aninhadas | 95,7% |
| Esboço das formas | 92,6% das 782 (tolerância de 0,1 mm) |

| Versão do arquivo | Situação |
|---|---|
| 2012 a 2018 e 2025 | tudo acima |
| 2022 em diante | o grupo do parâmetro fica nulo (o arquivo guarda um identificador sem o rótulo) |
| 2010 e 2011 | só metadados e miniatura: esses arquivos não têm PartAtom, e o enquadramento das partições ainda não foi decifrado |

Ainda não sai a geometria 3D pronta (malha) nem o valor dos parâmetros de material. O método e o que se sabe do formato estão em [`docs/formato.md`](docs/formato.md).

## Testes

```bash
pip install -e .[dev]
pytest -q
```

Os testes sintéticos rodam em qualquer lugar. Os que comparam com arquivos reais precisam de `.rfa` de terceiros, que **não vêm no repositório**: aponte `LEITOR_RFA_FIXTURES` para uma pasta com `fixtures/<nome>/familia.rfa` + `familia.json` (o gabarito) e `arquivos/*.rfa`. Sem ela, esses testes são pulados.

## Método

O formato foi decifrado a partir dos bytes dos arquivos `.rfa`: nenhuma parte foi obtida decompilando, depurando ou instrumentando o Revit ou suas bibliotecas. O que o arquivo não traz por extenso (nomes dos parâmetros embutidos, rótulos de grupo e de categoria, códigos das fórmulas) foi aprendido comparando com o que o Revit exporta, pela API dele, das mesmas famílias (o gabarito acima). Parte do código é porte do [rvt-rs](https://github.com/DrunkOnJava/rvt-rs) (Apache-2.0), estendido às versões 2010–2014.

Projeto independente, sem afiliação com a Autodesk. "Autodesk" e "Revit" são marcas registradas da Autodesk, Inc.

## Licença

MIT ([`LICENSE`](LICENSE)). Os arquivos portados do rvt-rs seguem sob Apache-2.0 ([`NOTICE`](NOTICE), [`LICENSE-APACHE`](LICENSE-APACHE)).

---

## English summary

**leitor-rfa** reads Autodesk Revit family files (`.rfa`) **without Revit** and outputs JSON: family name and category, types, parameters with per-type values and formulas, reference planes, dimensions, nested families, forms (extrusion, revolution, sweep, blend, with their sketch in mm) and the preview image. A `cobertura` (coverage) block states, per section, whether it was fully decoded, partially decoded or not decoded.

Pure Python; the only dependency is `olefile`. Validated field by field against 106 families exported by Revit itself, and run without a single crash on about 2,700 files from Revit 2010–2025. Install with `pip install git+https://github.com/bandleo/leitor-rfa` and run `ler-rfa family.rfa -o family.json`. Code, field names and docs are in Brazilian Portuguese.

The format was decoded from the bytes of `.rfa` files; Revit was never decompiled, debugged or instrumented. Labels the file does not spell out (built-in parameter names, group and category labels, formula codes) were learned by comparing with what Revit exports for the same families through its API. Parts are Python ports of [rvt-rs](https://github.com/DrunkOnJava/rvt-rs) (Apache-2.0). Not affiliated with Autodesk. MIT licensed; the rvt-rs-derived files stay under Apache-2.0.
