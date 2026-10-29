# leitor-rfa

Converts an Autodesk Revit family (`.rfa`) into a **BIMCraft family**, without Revit. It reads the file directly, works out what it is, and writes the BIMCraft family with the category, parameters, types, formulas and forms BIMCraft can build; whatever cannot be converted goes into a report, with the reason.

Along the way it also returns JSON describing everything about the family (name, category, types, parameters with values and formulas, reference planes, dimensions, nested families, forms with their sketch, and the preview image) and the 3D that Revit itself saved inside the file. For each section, the `cobertura` (coverage) block says whether it was decoded, partially decoded or not decoded.

Pure Python; the only dependency is [`olefile`](https://pypi.org/project/olefile/). Runs on Windows and Linux.

*Versão em português: [README.md](README.md). The code, field names and docs are in Brazilian Portuguese.*

## Install and use

```bash
pip install git+https://github.com/bandleo/leitor-rfa
ler-rfa visualizar
```

`ler-rfa visualizar` opens a local page in your browser: drop a `.rfa`, check the summary, types × parameters, formulas, forms, coverage and the **3D next to Revit's own preview image**, then click **Exportar família BIMCraft** (a `.zip` with the family and the data file). The server only listens on `127.0.0.1`; the file never leaves your machine.

From the command line:

```bash
ler-rfa family.rfa -o family.json --miniatura family.png --glb family.glb
python -m leitor_rfa.bimcraft family.json -o family-bimcraft.json --dados family-data.json
```

## What goes into BIMCraft

| In Revit | In the BIMCraft family |
|---|---|
| Category | Plumbing fixtures → `plumbing`; everything else → `generic` |
| Length, angle, number, yes/no and material parameters | parameters with each type's value (in mm and degrees); names adjusted to BIMCraft's naming rule |
| Formulas | carried over when they only use what BIMCraft supports (mm, `if`, `and`, `or`, `not`, `min`, `max`, `abs`, `sqrt`, `round`, `sin`, `cos`, `tan`…) |
| Text and URL parameters | do not exist in a BIMCraft family: they go to the data file, per type |
| Extrusions and revolutions | forms on the xy, xz or yz plane; a loop inside another becomes a hole; void forms become `void` |
| Sweeps and blends | left out (BIMCraft does not sweep along a path or blend profiles) and listed in the report |
| Reference floor or wall of the template | left out: Revit does not show it in a project |

The data file (`--dados`, or the `-dados.json` in the `.zip`) holds the report: what was left out and why, renamed parameters and the text values per type. Tested with BIMCraft 0.8 (`bimcraft-cli`).

## 3D

The 3D (`--glb`, and on the page) comes from the geometry Revit itself saves inside the `.rfa` (the regenerated B-rep, with cuts and joins already applied): each face becomes triangles within 0.5 mm of the surface, and the edges drawn are the ones Revit draws. A badge says whether the 3D is complete or what is missing (nested families and imported CAD have no 3D yet). The reference floor or wall of host-based templates, which Revit does not show in a project, is flagged and hidden.

## From Python

```python
from leitor_rfa.documento import ler
from leitor_rfa.bimcraft import converter

doc = ler("family.rfa")
doc["familia"]["nome"], list(doc["tipos"])
doc["cobertura"]["secoes"]["parametros"]["estado"]   # "decifrado" | "parcial" | "nao_decifrado"
bimcraft_family, report = converter(doc)
```

For whole folders: `python -m leitor_rfa.lote <folder> -o report.json --jsons <output>` writes one JSON per family and a coverage summary per Revit version.

## What the JSON contains (`versao_esquema: 1`)

| Section | Contents |
|---|---|
| `familia` | name (the file name, as Revit does) and category |
| `tipos` | each type with the value of every parameter |
| `parametros` | name, group, instance or type, shared (with GUID), data type and formula |
| `planos_referencia` | name and reference type (strong, weak, center…) |
| `cotas` | label (parameter), value in mm and number of references |
| `aninhadas` | family, type, category, shared and count |
| `formas` | kind (extrusion, revolution, sweep, blend), solid or void, linked material and visibility parameters, start and end, sketch in mm and sketch plane |
| `partatom` | what the file itself publishes in its PartAtom (title, category, OmniClass, types) |
| `cobertura` | format version, schema, partitions and the state of each section, with a note when something is missing |

Schema v1 is the same one written for each family by an extraction run **inside Revit** (through its API); that extraction is not part of this repository. It is the **reference** for the tests and for the comparison tool (`python -m leitor_rfa.conferencia --gabarito <folder>`): pairs of `familia.rfa` + `familia.json` for the same family. If you have such extractions, `leitor_rfa.fonte.ler_familia(rfa, extracao=<folder>)` fills the sections the reader cannot decode yet from `<folder>/<sha256 of the .rfa>/familia.json`, and `cobertura.origem` says where each section came from.

## Coverage

Measured field by field against a reference set of 106 families exported by Revit itself and, beyond it, against the PartAtom of about 2,700 files (1,824 from manufacturers, Revit 2010 to 2018, and 881 from the Autodesk library, Revit 2025), **without a single crash**:

| Section | Match against Revit |
|---|---|
| Types | 141/141 |
| Parameters | 98.8% of fields |
| Formulas | 96.3% of 1,892 (identical text) |
| Reference planes | 99.2% |
| Dimensions | 97.5% |
| Nested families | 95.7% |
| Form sketches | 92.6% of 782 (0.1 mm tolerance) |

| File version | Status |
|---|---|
| 2012 to 2018 and 2025 | everything above |
| 2022 and later | the parameter group is null (the file stores an identifier without the label) |
| 2010 and 2011 | metadata and preview image only: these files have no PartAtom, and their partition framing is not decoded yet |

**3D** (against the IFC Revit exports for the same families, 95th percentile of the distance between surfaces ≤ 2 mm): 82 of 102 families; 59 of the 63 whose 3D comes out complete. Material parameter values are not read yet. The method and what is known about the format are in [`docs/formato.md`](docs/formato.md) (Portuguese).

## Tests

```bash
pip install -e .[dev]
pytest -q
cd web && npm ci && npm test        # viewer and page (Vitest)
npm run build                       # builds the page into leitor_rfa/web
```

The synthetic tests run anywhere. The ones that compare against real files need third-party `.rfa` files, which are **not in the repository**: point `LEITOR_RFA_FIXTURES` to a folder with `fixtures/<name>/familia.rfa` + `familia.json` (the reference) and `arquivos/*.rfa`. Without it, those tests are skipped.

## Method

The format was decoded from the bytes of `.rfa` files: no part of it was obtained by decompiling, debugging or instrumenting Revit or its libraries. What the file does not spell out (built-in parameter names, group and category labels, formula codes) was learned by comparing with what Revit exports, through its API, for the same families (the reference set above). Part of the code is a port of [rvt-rs](https://github.com/DrunkOnJava/rvt-rs) (Apache-2.0), extended to the 2010–2014 versions.

Independent project, not affiliated with Autodesk. "Autodesk" and "Revit" are registered trademarks of Autodesk, Inc.

## License

MIT ([`LICENSE`](LICENSE)). The files ported from rvt-rs remain under Apache-2.0 ([`NOTICE`](NOTICE), [`LICENSE-APACHE`](LICENSE-APACHE)). The built page in `leitor_rfa/web` bundles three.js (MIT).
