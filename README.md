# leitor-rfa

Converte uma família do Revit (`.rfa`) em **família do BIMCraft**, sem o Revit. Lê o arquivo direto, entende o que ele é e grava a família do BIMCraft com a categoria, os parâmetros, os tipos, as fórmulas e as formas que o BIMCraft sabe montar; o que não dá para converter vai num relatório, com o motivo.

No caminho, devolve também um JSON com tudo o que a família é (nome, categoria, tipos, parâmetros com valores e fórmulas, planos de referência, cotas, famílias aninhadas, formas com o esboço e a miniatura) e o 3D que o próprio Revit gravou no arquivo. Cada seção diz, no bloco `cobertura`, se foi decifrada, decifrada em parte ou não.

Python puro; a única dependência é o [`olefile`](https://pypi.org/project/olefile/). Roda no Windows e no Linux.

*English version: [README.en.md](README.en.md).*

## Instalar e usar

```bash
pip install git+https://github.com/bandleo/leitor-rfa
ler-rfa visualizar
```

`ler-rfa visualizar` abre no navegador uma página local: solte um `.rfa`, confira o resumo, os tipos × parâmetros, as fórmulas, as formas, a cobertura e o **3D ao lado da miniatura do Revit**, e clique em **Exportar família BIMCraft** (um `.zip` com a família e o arquivo de dados). O servidor só escuta em `127.0.0.1`; o arquivo não sai da máquina.

Pela linha de comando:

```bash
ler-rfa familia.rfa -o familia.json --miniatura familia.png --glb familia.glb
python -m leitor_rfa.bimcraft familia.json -o familia-bimcraft.json --dados familia-dados.json
```

## O que vai para o BIMCraft

| No Revit | Na família do BIMCraft |
|---|---|
| Categoria | Peças hidrossanitárias → `plumbing`; as demais → `generic` |
| Parâmetros de comprimento, ângulo, número, sim/não e material | parâmetros com o valor de cada tipo (em mm e graus); nomes ajustados à regra do BIMCraft |
| Fórmulas | passam quando só usam o que o BIMCraft tem (mm, `if`, `and`, `or`, `not`, `min`, `max`, `abs`, `sqrt`, `round`, `sin`, `cos`, `tan`…) |
| Parâmetros de texto e URL | não existem na família do BIMCraft: vão para o arquivo de dados, por tipo |
| Extrusões e revoluções | formas no plano xy, xz ou yz; laço dentro de laço vira furo; forma vazia vira `void` |
| Varreduras e mesclas | ficam de fora (o BIMCraft não varre por caminho nem mescla perfis) e entram no relatório |
| Laje ou parede de referência do gabarito | fica de fora: o Revit não a mostra no projeto |

O arquivo de dados (`--dados`, ou o `-dados.json` do `.zip`) traz o relatório: o que ficou de fora e por quê, os nomes ajustados e os textos por tipo. Testado com o BIMCraft 0.8 (`bimcraft-cli`).

## 3D

O 3D (`--glb`, e na página) sai da geometria que o próprio Revit grava dentro do `.rfa` (o B-rep regenerado, já com cortes e junções): cada face vira triângulos dentro de 0,5 mm da superfície, e as arestas são as que o Revit desenha. Um selo diz se o 3D está completo ou o que falta (famílias aninhadas e CAD importado ainda não têm 3D). A laje ou parede de referência dos gabaritos baseados em hospedeiro, que o Revit não mostra no projeto, vem marcada e fica oculta.

## Em Python

```python
from leitor_rfa.documento import ler
from leitor_rfa.bimcraft import converter

doc = ler("familia.rfa")
doc["familia"]["nome"], list(doc["tipos"])
doc["cobertura"]["secoes"]["parametros"]["estado"]   # "decifrado" | "parcial" | "nao_decifrado"
familia_bimcraft, relatorio = converter(doc)
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

**3D** (contra o IFC que o Revit exporta das mesmas famílias, P95 da distância entre as superfícies ≤ 2 mm): 82 de 102 famílias; 59 de 63 das que saem com 3D completo. Ainda não sai o valor dos parâmetros de material. O método e o que se sabe do formato estão em [`docs/formato.md`](docs/formato.md).

## Testes

```bash
pip install -e .[dev]
pytest -q
cd web && npm ci && npm test        # visualizador e página (Vitest)
npm run build                       # gera a página em leitor_rfa/web
```

Os testes sintéticos rodam em qualquer lugar. Os que comparam com arquivos reais precisam de `.rfa` de terceiros, que **não vêm no repositório**: aponte `LEITOR_RFA_FIXTURES` para uma pasta com `fixtures/<nome>/familia.rfa` + `familia.json` (o gabarito) e `arquivos/*.rfa`. Sem ela, esses testes são pulados.

## Método

O formato foi decifrado a partir dos bytes dos arquivos `.rfa`: nenhuma parte foi obtida decompilando, depurando ou instrumentando o Revit ou suas bibliotecas. O que o arquivo não traz por extenso (nomes dos parâmetros embutidos, rótulos de grupo e de categoria, códigos das fórmulas) foi aprendido comparando com o que o Revit exporta, pela API dele, das mesmas famílias (o gabarito acima). Parte do código é porte do [rvt-rs](https://github.com/DrunkOnJava/rvt-rs) (Apache-2.0), estendido às versões 2010–2014.

Projeto independente, sem afiliação com a Autodesk. "Autodesk" e "Revit" são marcas registradas da Autodesk, Inc.

## Licença

MIT ([`LICENSE`](LICENSE)). Os arquivos portados do rvt-rs seguem sob Apache-2.0 ([`NOTICE`](NOTICE), [`LICENSE-APACHE`](LICENSE-APACHE)).

---

**English:** full version in [README.en.md](README.en.md).
