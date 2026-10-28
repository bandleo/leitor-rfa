# O formato `.rfa`, do jeito que o leitor o lê

O que se sabe aqui saiu dos bytes de arquivos `.rfa` salvos pelo Revit de 2010 a 2025, conferido contra o que o próprio Revit exporta, pela API dele, das mesmas famílias (de onde também vêm os rótulos que o arquivo não traz por extenso). Os nomes de classe e de campo (`FamilyParams`, `m_oExpression`…) são os que o próprio arquivo traz no seu esquema. A base de descompressão, esquema, registros e grafo é do [rvt-rs](https://github.com/DrunkOnJava/rvt-rs), que cobre 2016+; as diferenças de 2010–2014 estão marcadas.

Unidades: o arquivo guarda comprimentos em **pés** e ângulos em radianos; o leitor converte para mm (× 304,8).

## 1. Contêiner

Um `.rfa` é um arquivo composto OLE/CFB ([MS-CFB]). Os streams que importam:

| Stream | O que tem |
|---|---|
| `BasicFileInfo` | versão do formato, build e caminho em que foi salvo |
| `PartAtom` | XML Atom com título, categoria, OmniClass e os tipos com valores de exibição (não existe em 2010 e 2011) |
| `RevitPreview4.0` | um cabeçalho e, depois, um PNG inteiro (a miniatura) |
| `Formats/Latest` | o esquema: todas as classes do formato e seus campos |
| `Global/ElemTable` | o índice dos ElementIds |
| `Global/Latest` e outros `Global/*` | cabeçalho do documento |
| `Partitions/<n>` | os elementos, comprimidos |

**`BasicFileInfo`:** um u32 de versão da estrutura (3 em 2010–2012, 6 em 2013–2014, 10 em 2018, 14 em 2025), 10 bytes e strings UTF-16 com prefixo u32. Até 2018 a primeira string é "Autodesk Revit … AAAA (Build: …)"; em 2025 é só o ano, e o build vem na seguinte. **A versão do formato vem daqui**, não do PartAtom: há arquivos com PartAtom "2010" salvos pelo Revit 2012.

**Nome da família:** é o nome do arquivo, como o Revit faz. O título do PartAtom costuma estar desatualizado.

## 2. Descompressão

- Os streams paginados guardam cada página completa como **64.896 bytes de dados + 353 de checksum** (65.249 no total); a última página, curta, vai inteira. O checksum sai antes de inflar.
- Depois vem um membro gzip (FEXTRA/FNAME/FCOMMENT/FHCRC opcionais) com **DEFLATE cru** (`zlib.decompressobj(-15)`); CRC32 e tamanho conferem no fim.
- Os `Global/*` de família têm um prefixo de 8 bytes antes do gzip.

## 3. Esquema (`Formats/Latest`)

Cada classe: nome (u16 + texto), base (u16; o bit 15 indica base definida em linha), versão u32, número de campos u32 e os campos como `[u32 nome][u32 tipo]`. A palavra de tipo combina o tipo (`01`–`0e`) com um modificador: `0x10` arranjo, `0x50` contêiner, `0x60` string UTF-16.

- **A etiqueta de uma classe é a ordem em que ela é definida, a partir de 12.** Ela muda de versão para versão, então nunca pode ir fixa no código: o leitor sempre lê o esquema do próprio arquivo.
- Há **duas variantes**: em 2010–2013 a definição de classe não tem o u32 final com o número de entradas opacas de 16 bytes (`sem_opaco`); de 2014 em diante tem (`com_opaco`). O leitor detecta lendo.
- Tamanho: 2.647 classes em 2010, 3.154 em 2012, 3.619 em 2014, 4.024 em 2018, 4.600 em 2025; um único esquema por versão.

## 4. Partições e segmentos

Uma partição inflada tem 8 bytes de cabeçalho e uma sequência de marcadores u16 cujas etiquetas vêm do esquema: `ContentMarker`, `ContentKey`, `SegmentMarker` (`[u32 flags][u32 n][u32 tam][u32 corpo][u64 canal][gzip]`), `SegmentCheckback` e `SignatureMarker` (este só de 2014 em diante). Os elementos ficam em três canais:

| Canal | Conteúdo |
|---|---|
| 101 | cadeia de cabeçalhos `[id][u32 tam][ElementHeader…][u32 tam]` |
| 102 | os objetos: `[id][u32 hash][u32 tam][u16 classe…][u32 tam]` |
| 103 | a geometria regenerada pelo Revit (B-rep), ver §9 |

**2010 e 2011 ainda não fecham:** o esquema dessas versões não tem `ContentMarker` nem `SegmentMarker`. Em 2010 há 8 bytes e um único gzip; em 2011, 8 bytes, um cabeçalho e seis gzip em sequência, sem etiquetas u16.

## 5. ElemTable e o documento principal

`Global/ElemTable`: u16 (etiqueta da classe `ElemTable`, confere com o esquema), u32 com o número de registros e os registros, de **28 bytes com ids de 32 bits (até 2023)** ou **40 bytes com ids de 64 bits (2024+)**. A largura certa é a que fecha com ids crescentes e o menor rabo; famílias recentes trazem rabos de centenas de bytes depois dos registros. Cada registro diz o dono do elemento (0 ou `0xFF…` = sem dono).

Uma família carrega as famílias aninhadas dentro dela, e os elementos delas se misturam aos seus. **O documento principal é a cadeia de donos até a `Family` raiz sem passar por outra `Family`.** Em 2012–2014 as carregadas vêm no mesmo espaço de ids, com uma `Family` aninhada como dona; de 2018 em diante vêm em grupos com chave de conteúdo, fora do ElemTable. A raiz é a `Family` sem dono; havendo duas, a citada no cabeçalho do `Global/Latest`.

## 6. O grafo de objetos

O corpo de um objeto começa com o u16 da classe; os campos vêm da classe mais básica para a mais derivada, cada um decodificado pelo seu tipo no esquema:

- **ponteiro** (base 14, modificadores 1–3): u32 de token e, se não nulo nem externo (modificador 3), o u16 da classe; o objeto apontado é lido depois do atual, em fila, e o mesmo token é o mesmo objeto;
- **string**: u32 n + n unidades UTF-16;
- **arranjo** `0x10`–`0x13`: contagem fixa, dada pelo esquema; `0x50`–`0x53`: u32 de contagem;
- campo com a flag 2 é transitório e não é gravado; o corpo é consumido inteiro.

Esse motor genérico decodifica 99% dos objetos e 100% das classes de parâmetro, tipo e forma.

- **ElementId:** até 2023, `{"m_id": n}`; **no Revit 2024+, 64 bits: `{"m_id": {"m_id64": n}}`**.
- **Revit 2022+:** grupo, tipo de dado e unidade passam a ser **ForgeTypeId em texto** (`autodesk.spec:spec.string-2.0.0`, …) em `m_groupTypeId` e `m_specTypeId`.

## 7. Parâmetros, tipos e fórmulas

- A `Family` raiz guarda `FamilyParams` (a lista de parâmetros, com instância, *reporting*, valor e a árvore da fórmula) e `FamilyTypeTable` (os tipos e o valor de cada parâmetro por tipo).
- Definições: `ParamElemFamily` e `ParamElemExternal` (compartilhado; GUID em `m_externalParamKey`), com `m_pParamDef` → `ParamDef*` (`m_caption`, tipo de dado, grupo).
- **Parâmetros embutidos** (id negativo) não têm nome no arquivo: o nome sai de uma tabela de constantes (`leitor_rfa/tabelas.json`), assim como o rótulo do grupo e o tipo de dado (15 chaves cada, sem ambiguidade). Cerca de um quarto dos parâmetros que o Revit mostra não existe no arquivo: ele acrescenta os de IFC e os da categoria ao abrir. O leitor os acrescenta pela mesma tabela e os marca como inferidos.
- **Fórmulas:** `NamedParam.m_oExpression` é a árvore da expressão — `StringConstant`, `NumberConstant`, `Parameter`, `BinaryOperator` (+ − * / = são os códigos 1–4), `UnaryOperator`, `Function` (`if` = 10) e parênteses. O número traz a unidade em que foi digitado (0 = mm, 4 = número); a fórmula sai como texto igual ao do Revit em 96% dos casos. Código fora da tabela vira erro, sem chute.

## 8. Planos, cotas, aninhadas e formas

- **Planos:** `RefPlane.m_text` (vazio = "Plano de referência") e `m_refName` → tipo de referência.
- **Cotas:** toda classe que herda de `Dimension` no esquema. Rótulo = `m_ArrSegInfo[0].m_paramId`; referências = tamanho de `m_witnessRefs`; valor = `m_lockedValue` só em `LinearDimString` de um segmento.
- **Aninhadas:** `FamilyInstance.m_masterSymbolId` → `FamilySymbol` (tipo = `SymbolInfo.m_name`) → `m_familyId` → `Family` (`m_name`, `m_bShared`, `m_categoryId`).
- **Formas:** a classe dá o tipo (`ExtrusionElem`, `RevolutionElem`, `SweepElem`, `BlendElem`, `SweptBlendElem`); vazio = `m_cutting`. O vínculo com parâmetro (`{m_famParamId, m_elemPropId}`) fica em `m_famParamDrivenData` até 2013 e na célula `FamilyParametrizedElemParamsCell` de 2014 em diante; `-1002107` = material. Início e fim da extrusão são `ParamValueSetDouble` com os ids `-1001800`/`-1001801`; ângulos da revolução, `-1001802`/`-1001803`.
- **Esboço:** os `CurveElem` filhos do `VarSketch` da forma, **em coordenadas do modelo** (`GLine`, `GArc` — parâmetros iguais = círculo —, `GEllipse`). O plano vem da matriz `m_oTrf` do `SketchPlane` (colunas = eixos, `m_or` = origem). O eixo da revolução é `RevolutionCurveData.m_axis`. Os laços se encadeiam pelas pontas com a tolerância de vértice do Revit (0,0005233 pé ≈ 0,16 mm).
- **Tesselação igual à do Revit:** flecha ≤ 1/16" por segmento, no mínimo 2 segmentos por arco, círculo em duas metades.

## 9. Geometria salva (o próximo passo)

O canal 103 guarda, para toda forma, o B-rep que o Revit regenerou (`GElement` → `Geometry` → `Face`/`EdgeLoop`/`Edge`, com superfícies `Plane`, `CylSurf`, `ConeSurf`, `SurfRev`, `RuledSurf`, `HermiteSurf`), **já com cortes e junções aplicados**. Os cortes estão listados em `GeomStepList.m_bRepCutOutGList` e as junções em `FamilyGeomCombination`; aninhadas (`GInstance`/`InstanceInfo`) e CAD importado (`MasterImportSymbol`) também têm B-rep. Transformar isso em malha é o trabalho em andamento; o arquivo guarda **um estado** só (o tipo corrente ao salvar).

## 10. O PartAtom como conferência

Fora de um gabarito exportado pelo Revit, o PartAtom confere tipos e valores: os valores vêm na precisão de exibição (comparar arredondando), o tipo único sem nome aparece com um hash, e parâmetros de sistema vêm no idioma em que o arquivo foi salvo.

[MS-CFB]: https://learn.microsoft.com/openspecs/windows_protocols/ms-cfb/
