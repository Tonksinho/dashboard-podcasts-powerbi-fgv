"""
Gerador do projeto Power BI (PBIP) para o dashboard de podcasts da FGV.

Cria a estrutura PBIP completa (modelo TMSL/.bim + relatório PBIR + tema)
apontando para data/spotify_dashboard.csv.

Estratégia: montar tudo como dicionários Python e serializar com json.dump
(escaping automático = zero erro de aspas/barra).

Uso:
    python gerar_pbip.py
Depois: abrir SpotifyDashboardFGV.pbip no Power BI Desktop (pasta do repo Git).
"""

from __future__ import annotations

import json
import os

import spoti_paths as paths

PROJ = paths.PROJ
PBIP_DIR = paths.PBIP_DIR
MODEL_DIR = os.path.join(PBIP_DIR, f"{PROJ}.SemanticModel")
REPORT_DIR = os.path.join(PBIP_DIR, f"{PROJ}.Report")
DATA_DIR = paths.DATA_DIR
LAYOUT_DIR = paths.LAYOUT_DIR


def w_json(path: str, obj: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ============================================================
# 1) Arquivo raiz .pbip
# ============================================================
def gerar_pbip_root():
    obj = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0",
        "artifacts": [
            {"report": {"path": f"{PROJ}.Report"}}
        ],
        "settings": {"enableAutoRecovery": True},
    }
    w_json(os.path.join(PBIP_DIR, f"{PROJ}.pbip"), obj)


# ============================================================
# 2) Semantic Model (TMSL / model.bim)
# ============================================================
def gerar_modelo():
    # .platform
    w_json(os.path.join(MODEL_DIR, ".platform"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": PROJ},
        "config": {"version": "2.0", "logicalId": "a1a1a1a1-1111-4111-8111-111111111111"},
    })

    # definition.pbism
    w_json(os.path.join(MODEL_DIR, "definition.pbism"), {"version": "4.0", "settings": {}})

    # Parâmetro de caminho (M). Em M a barra é literal; json.dump escapa sozinho.
    param_expr = (
        '"' + DATA_DIR + '" meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]'
    )

    # Consulta M que lê o CSV limpo
    m_expr = (
        'let\n'
        '    Fonte = Csv.Document(File.Contents(PastaDados & "\\spotify_dashboard.csv"), '
        '[Delimiter=",", Columns=8, Encoding=65001, QuoteStyle=QuoteStyle.Csv]),\n'
        '    Promovido = Table.PromoteHeaders(Fonte, [PromoteAllScalars=true]),\n'
        '    Tipado = Table.TransformColumnTypes(Promovido, {'
        '{"data", type date}, {"programa", type text}, {"plays", Int64.Type}, '
        '{"seguidores", Int64.Type}, {"pct_homens", type number}, {"pct_mulheres", type number}, '
        '{"pct_outros", type number}, {"top_faixa_etaria", type text}})\n'
        'in\n'
        '    Tipado'
    )

    # ----- Medidas DAX -----
    # Semântica de SNAPSHOT: `plays` e `seguidores` são ACUMULADOS (só crescem),
    # então somar linhas dobra a contagem. KPI correto = valor no ÚLTIMO dia do filtro;
    # variação = fim do período selecionado vs. início do período (não dia a dia).
    # Demografia: média PONDERADA por plays (um podcast de 30k não pode pesar
    # igual a um de 1 play), restrita ao último snapshot.
    # Slicer no Calendário (todos os dias); KPIs usam snapshots reais do Spotify.
    _ULT = "CALCULATE(MAX('Spotify'[data]), ALLSELECTED('Calendario'[data]))"
    _DATAS_COLETA = "CALCULATETABLE(VALUES('Spotify'[data]), ALLSELECTED('Calendario'[data]))"
    _SEL_INI = "MINX(ALLSELECTED('Calendario'[data]), 'Calendario'[data])"
    _SEL_FIM = "MAXX(ALLSELECTED('Calendario'[data]), 'Calendario'[data])"
    def _atual(col: str) -> str:
        return (f"VAR _d = {_ULT}\n"
                f"RETURN CALCULATE(SUM('Spotify'[{col}]), 'Spotify'[data] = _d)")

    def _inicio_periodo(col: str) -> str:
        return (f"VAR _datas = {_DATAS_COLETA}\n"
                "VAR _ini = MINX(_datas, 'Spotify'[data])\n"
                f"RETURN CALCULATE(SUM('Spotify'[{col}]), 'Spotify'[data] = _ini)")

    def _genero(col: str) -> str:
        return (f"VAR _d = {_ULT}\n"
                "RETURN DIVIDE(CALCULATE(DIVIDE("
                f"SUMX('Spotify', 'Spotify'[plays] * 'Spotify'[{col}]), "
                "SUM('Spotify'[plays])), 'Spotify'[data] = _d), 100)")

    measures = [
        # Estado atual (último snapshot)
        {"name": "Plays Atual", "expression": _atual("plays"), "formatString": "#,0"},
        {"name": "Seguidores Atual", "expression": _atual("seguidores"), "formatString": "#,0"},
        # Helpers ocultos (snapshot anterior)
        {"name": "Plays Início Período", "expression": _inicio_periodo("plays"),
         "formatString": "#,0", "isHidden": True},
        {"name": "Seguidores Início Período", "expression": _inicio_periodo("seguidores"),
         "formatString": "#,0", "isHidden": True},
        # Variação absoluta e percentual vs. snapshot anterior
        {"name": "Var Plays", "expression": "[Plays Atual] - [Plays Início Período]",
         "formatString": "+#,0;-#,0"},
        {"name": "Var Seguidores", "expression": "[Seguidores Atual] - [Seguidores Início Período]",
         "formatString": "+#,0;-#,0"},
        {"name": "Crescimento Plays", "expression": "DIVIDE([Var Plays], [Plays Início Período])",
         "formatString": "+0.0%;-0.0%"},
        {"name": "Crescimento Seguidores",
         "expression": "DIVIDE([Var Seguidores], [Seguidores Início Período])",
         "formatString": "+0.0%;-0.0%"},
        # Período selecionado no slicer (início → fim)
        {"name": "Período Início",
         "expression": f"RETURN {_SEL_INI}",
         "formatString": "dd/mm/yyyy", "isHidden": True},
        {"name": "Período Fim",
         "expression": f"RETURN {_SEL_FIM}",
         "formatString": "dd/mm/yyyy", "isHidden": True},
        {"name": "Comparação Snapshot",
         "expression": (
             f"VAR _ini = {_SEL_INI}\n"
             f"VAR _fim = {_SEL_FIM}\n"
             "RETURN\n"
             "IF(_ini = _fim, FORMAT(_fim, \"DD/MM/YYYY\"), "
             "FORMAT(_ini, \"DD/MM/YYYY\") & \" até \" & FORMAT(_fim, \"DD/MM/YYYY\"))"
         )},
        {"name": "Período Análise",
         "expression": (
             "VAR _comp = [Comparação Snapshot]\n"
             "RETURN \"Período: \" & _comp"
         )},
        {"name": "Nota Snapshot",
         "expression": (
             f"VAR _selIni = {_SEL_INI}\n"
             f"VAR _selFim = {_SEL_FIM}\n"
             f"VAR _datas = {_DATAS_COLETA}\n"
             "VAR _colIni = MINX(_datas, 'Spotify'[data])\n"
             "VAR _colFim = MAXX(_datas, 'Spotify'[data])\n"
             "RETURN\n"
             "IF(_selIni = _selFim, "
             "\"Selecione um intervalo (de/até) no slicer de período.\", "
             "IF(_colIni = _colFim, "
             "\"Período \" & FORMAT(_selIni, \"DD/MM/YYYY\") & \" a \" & FORMAT(_selFim, \"DD/MM/YYYY\") "
             "& \" · uma coleta em \" & FORMAT(_colFim, \"DD/MM/YYYY\") & \".\", "
             "\"Período \" & FORMAT(_selIni, \"DD/MM/YYYY\") & \" a \" & FORMAT(_selFim, \"DD/MM/YYYY\") "
             "& \" · variações nas coletas de \" & FORMAT(_colIni, \"DD/MM/YYYY\") & \" a \" "
             "& FORMAT(_colFim, \"DD/MM/YYYY\") & \".\"))"
         )},
        {"name": "Programas Ativos",
         "expression": f"VAR _d = {_ULT}\n"
                       "RETURN CALCULATE(DISTINCTCOUNT('Spotify'[programa]), 'Spotify'[data] = _d)",
         "formatString": "0"},
        # Demografia PONDERADA por plays (não média simples)
        {"name": "Homens", "expression": _genero("pct_homens"), "formatString": "0.0%"},
        {"name": "Mulheres", "expression": _genero("pct_mulheres"), "formatString": "0.0%"},
        {"name": "Outros", "expression": _genero("pct_outros"), "formatString": "0.0%"},
        {"name": "Plays por Faixa",
         "expression": (
             f"VAR _d = {_ULT}\n"
             "RETURN CALCULATE(SUM('Spotify'[plays]), 'Spotify'[data] = _d)"
         ),
         "formatString": "#,0"},
        {"name": "Faixa Etária Principal",
         "expression": (
             f"VAR _d = {_ULT}\n"
             "VAR _t = ADDCOLUMNS(\n"
             "    VALUES('Spotify'[top_faixa_etaria]),\n"
             "    \"@p\", CALCULATE(SUM('Spotify'[plays]), 'Spotify'[data] = _d)\n"
             ")\n"
             "VAR _top = TOPN(1, _t, [@p], DESC)\n"
             "RETURN MAXX(_top, 'Spotify'[top_faixa_etaria])"
         )},
        # Ranking por programa (último vs. snapshot anterior)
        {"name": "Líder Volume",
         "expression": "VAR _t = ADDCOLUMNS(VALUES('Spotify'[programa]), \"@p\", [Plays Atual])\n"
                       "RETURN MAXX(TOPN(1, _t, [@p], DESC), 'Spotify'[programa])"},
        {"name": "Top Crescimento",
         "expression": "VAR _t = ADDCOLUMNS(VALUES('Spotify'[programa]), \"@v\", [Var Plays])\n"
                       "RETURN MAXX(TOPN(1, _t, [@v], DESC), 'Spotify'[programa])"},
        {"name": "Delta Top Crescimento",
         "expression": "VAR _t = ADDCOLUMNS(VALUES('Spotify'[programa]), \"@v\", [Var Plays])\n"
                       "RETURN MAXX(TOPN(1, _t, [@v], DESC), [@v])",
         "formatString": "+#,0;-#,0"},
        # Eficiência de engajamento: quantos plays cada seguidor "rende"
        {"name": "Plays por Seguidor", "expression": "DIVIDE([Plays Atual], [Seguidores Atual])",
         "formatString": "0.0"},
        # Conversão de funil: dos novos plays, quantos viraram seguidor
        {"name": "Conversão Seguidores", "expression": "DIVIDE([Var Seguidores], [Var Plays])",
         "formatString": "0.0%;-0.0%"},
        # Risco de concentração: % dos plays nos 3 maiores programas
        {"name": "% Plays nos Top 3",
         "expression": "VAR _tab = ADDCOLUMNS(ALLSELECTED('Spotify'[programa]), \"@p\", [Plays Atual])\n"
                       "VAR _top3 = TOPN(3, _tab, [@p], DESC)\n"
                       "RETURN DIVIDE(SUMX(_top3, [@p]), SUMX(_tab, [@p]))",
         "formatString": "0.0%"},
        {"name": "Nomes Top 3",
         "expression": "VAR _tab = ADDCOLUMNS(ALLSELECTED('Spotify'[programa]), \"@p\", [Plays Atual])\n"
                       "VAR _top3 = TOPN(3, _tab, [@p], DESC)\n"
                       "RETURN CONCATENATEX(_top3, 'Spotify'[programa], \" · \", [@p], DESC)"},
        {"name": "Top 3 Detalhe",
         "expression": (
             "VAR _pct = [% Plays nos Top 3]\n"
             "VAR _nomes = [Nomes Top 3]\n"
             "RETURN\n"
             "IF(ISBLANK(_nomes), \"Sem dados de Top 3\", "
             "FORMAT(_pct, \"0%\") & \" dos plays: \" & _nomes)"
         )},
        # Narrativa executiva (página Conselho) — textos curtos para cards compactos
        {"name": "Resumo Executivo",
         "expression": (
             "VAR _delta = [Var Plays]\n"
             "VAR _lider = [Líder Volume]\n"
             "VAR _cresce = [Top Crescimento]\n"
             "VAR _dc = [Delta Top Crescimento]\n"
             "VAR _conc = [% Plays nos Top 3]\n"
             "VAR _nomes = [Nomes Top 3]\n"
             "VAR _prog = [Programas Ativos]\n"
             "VAR _sinal = IF(_delta >= 0, \"+\", \"\")\n"
             "VAR _sinalc = IF(ISBLANK(_dc) || _dc >= 0, \"+\", \"\")\n"
             "VAR _dcn = IF(ISBLANK(_dc), 0, _dc)\n"
             "VAR _crescetxt = IF(ISBLANK(_cresce), \"sem destaque\", _cresce)\n"
             "VAR _comp = [Comparação Snapshot]\n"
             "RETURN\n"
             + "_sinal & FORMAT(_delta, \"#,0\") & \" plays (\" & _comp & \") · \" & _lider "
             + "& \" lidera volume · maior crescimento: \" & _crescetxt "
             + "& \" (\" & _sinalc & FORMAT(_dcn, \"#,0\") & \") · Top 3 (\" "
             + "& FORMAT(_conc, \"0%\") & \"): \" & _nomes "
             + "& \" · \" & FORMAT(_prog, \"0\") & \" programas\""
         )},
        {"name": "Última Coleta",
         "expression": f'VAR _d = {_ULT}\nRETURN "Última coleta: " & FORMAT(_d, "DD/MM/YYYY")'},
        {"name": "Top Conversão Seguidores",
         "expression": (
             "VAR _t = ADDCOLUMNS(\n"
             "    FILTER(VALUES('Spotify'[programa]), [Var Plays] > 0 "
             "&& NOT(ISBLANK([Conversão Seguidores]))),\n"
             "    \"@c\", [Conversão Seguidores])\n"
             "RETURN MAXX(TOPN(1, _t, [@c], DESC), 'Spotify'[programa])"
         )},
        {"name": "Valor Top Conversão",
         "expression": (
             "VAR _p = [Top Conversão Seguidores]\n"
             "RETURN CALCULATE([Conversão Seguidores], 'Spotify'[programa] = _p)"
         ),
         "formatString": "0.0%"},
        {"name": "PPS Top Conversão",
         "expression": (
             "VAR _p = [Top Conversão Seguidores]\n"
             "RETURN CALCULATE([Plays por Seguidor], 'Spotify'[programa] = _p)"
         ),
         "formatString": "0.0"},
        {"name": "Destaque Engajamento",
         "expression": (
             "VAR _p = [Top Conversão Seguidores]\n"
             "VAR _conv = [Valor Top Conversão]\n"
             "VAR _pps = [PPS Top Conversão]\n"
             "RETURN\n"
             "IF(ISBLANK(_p), \"Sem conversão mensurável no período\", "
             "\"Melhor conversão em seguidores: \" & _p & \" (\" & FORMAT(_conv, \"0.0%\") "
             "& \" dos novos plays viraram seguidor · \" & FORMAT(_pps, \"0.0\") "
             "& \" plays/seguidor)\")"
         )},
        {"name": "Destaque Oportunidade",
         "expression": (
             "VAR _p = [Top Crescimento]\n"
             "VAR _d = [Delta Top Crescimento]\n"
             "VAR _dn = IF(ISBLANK(_d), 0, _d)\n"
             "VAR _s = IF(_dn >= 0, \"+\", \"\") & FORMAT(_dn, \"#,0\")\n"
             "RETURN\n"
             "IF(ISBLANK(_p), \"Sem crescimento de plays no período\", "
             "\"Maior crescimento: \" & _p & \" (\" & _s & \" plays)\")"
         )},
    ]

    model_bim = {
        "name": PROJ,
        "compatibilityLevel": 1600,
        "model": {
            "culture": "pt-BR",
            "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "sourceQueryCulture": "pt-BR",
            "tables": [
                {
                    "name": "Spotify",
                    "columns": [
                        {"name": "data", "dataType": "dateTime", "sourceColumn": "data",
                         "formatString": "yyyy-mm-dd", "summarizeBy": "none"},
                        {"name": "programa", "dataType": "string", "sourceColumn": "programa",
                         "summarizeBy": "none"},
                        {"name": "plays", "dataType": "int64", "sourceColumn": "plays",
                         "summarizeBy": "sum"},
                        {"name": "seguidores", "dataType": "int64", "sourceColumn": "seguidores",
                         "summarizeBy": "sum"},
                        {"name": "pct_homens", "dataType": "double", "sourceColumn": "pct_homens",
                         "summarizeBy": "none"},
                        {"name": "pct_mulheres", "dataType": "double", "sourceColumn": "pct_mulheres",
                         "summarizeBy": "none"},
                        {"name": "pct_outros", "dataType": "double", "sourceColumn": "pct_outros",
                         "summarizeBy": "none"},
                        {"name": "top_faixa_etaria", "dataType": "string",
                         "sourceColumn": "top_faixa_etaria", "summarizeBy": "none"},
                    ],
                    "partitions": [
                        {"name": "Spotify", "mode": "import",
                         "source": {"type": "m", "expression": m_expr}}
                    ],
                    "measures": measures,
                },
                {
                    # Calendário contínuo para o slicer de/até (inclui dias sem coleta).
                    "name": "Calendario",
                    "columns": [
                        {"name": "data", "dataType": "dateTime", "sourceColumn": "data",
                         "formatString": "dd/mm/yyyy", "summarizeBy": "none"},
                    ],
                    "partitions": [
                        {"name": "Calendario", "mode": "import",
                         "source": {
                             "type": "m",
                             "expression": (
                                 "let\n"
                                 "    Fonte = Spotify,\n"
                                 "    MinData = List.Min(Fonte[data]),\n"
                                 "    MaxData = List.Max(Fonte[data]),\n"
                                 "    Ini = Date.StartOfMonth(MinData),\n"
                                 "    Fim = Date.EndOfMonth(MaxData),\n"
                                 "    N = Duration.Days(Fim - Ini) + 1,\n"
                                 "    Dias = List.Dates(Ini, N, #duration(1, 0, 0, 0)),\n"
                                 "    Tbl = Table.FromList(Dias, Splitter.SplitByNothing(), {\"data\"}),\n"
                                 "    Tipado = Table.TransformColumnTypes(Tbl, {{\"data\", type date}}),\n"
                                 "    Unico = Table.Distinct(Tipado, {\"data\"})\n"
                                 "in\n"
                                 "    Unico"
                             ),
                         }},
                    ],
                },
                {
                    # Tabela estática (M) — mais estável que calculated no PBIP
                    "name": "DemografiaGenero",
                    "columns": [
                        {"name": "Genero", "dataType": "string", "sourceColumn": "Genero",
                         "summarizeBy": "none"},
                    ],
                    "partitions": [
                        {"name": "DemografiaGenero", "mode": "import",
                         "source": {
                             "type": "m",
                             "expression": (
                                 "let\n"
                                 "    Source = #table({\"Genero\"}, {{\"Homens\"}, {\"Mulheres\"}})\n"
                                 "in\n"
                                 "    Source"
                             ),
                         }},
                    ],
                    "measures": [
                        {"name": "Pct Audiencia",
                         "expression": (
                             "VAR _g = SELECTEDVALUE(DemografiaGenero[Genero])\n"
                             "VAR _h = [Homens]\n"
                             "VAR _m = [Mulheres]\n"
                             "VAR _base = _h + _m\n"
                             "RETURN\n"
                             "SWITCH(_g,\n"
                             "    \"Homens\", DIVIDE(_h, _base),\n"
                             "    \"Mulheres\", DIVIDE(_m, _base),\n"
                             "    BLANK())"
                         ),
                         "formatString": "0.0%"},
                    ],
                },
            ],
            "expressions": [
                {"name": "PastaDados", "kind": "m", "expression": param_expr}
            ],
            "relationships": [
                # many (Spotify) → one (Calendario) — data única só no calendário
                {"name": "Spotify-Calendario-data",
                 "fromTable": "Spotify", "fromColumn": "data",
                 "toTable": "Calendario", "toColumn": "data",
                 "crossFilteringBehavior": "oneDirection"},
            ],
            "annotations": [
                {"name": "PBI_QueryOrder",
                 "value": "[\"PastaDados\",\"Spotify\",\"Calendario\",\"DemografiaGenero\"]"}
            ],
        },
    }
    w_json(os.path.join(MODEL_DIR, "model.bim"), model_bim)


# ============================================================
# 3) Relatório (PBIR) + tema
# ============================================================
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"


def measure_proj_entity(entity: str, prop: str, label: str | None = None) -> dict:
    proj = {
        "field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
        "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop,
    }
    if label:
        proj["displayName"] = label
    return proj


def measure_proj(prop: str, label: str | None = None) -> dict:
    return measure_proj_entity("Spotify", prop, label)


def column_proj(prop: str, entity: str = "Spotify", label: str | None = None) -> dict:
    proj = {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
        "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop,
    }
    if label:
        proj["displayName"] = label
    return proj


def _field_ref(entity: str, prop: str, ftype: str) -> dict:
    return {"field": {ftype: {"Expression": {"SourceRef": {"Entity": entity}},
                              "Property": prop}}}


def visual(name, x, y, w, h, tab, vtype, query_state) -> dict:
    return {
        "$schema": f"{SCHEMA}/visualContainer/1.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": tab, "width": w, "height": h, "tabOrder": tab},
        "visual": {"visualType": vtype, "query": {"queryState": query_state},
                   "drillFilterOtherVisuals": True},
    }


def _lit(value: str | bool | int) -> dict:
    if isinstance(value, bool):
        lit = "true" if value else "false"
    elif isinstance(value, int):
        lit = f"{value}D"
    else:
        lit = f"'{value}'"
    return {"expr": {"Literal": {"Value": lit}}}


def insight_card(name, x, y, w, h, tab, measure: str, font_pt: int = 10,
                 title: str | None = None) -> dict:
    """Card de narrativa: fonte pequena, sem rótulo da medida, quebra de linha."""
    v = visual(name, x, y, w, h, tab, "card",
               {"Values": {"projections": [measure_proj(measure)]}})
    objects: dict = {
        "labels": [{"properties": {
            "fontSize": _lit(font_pt),
            "color": {"solid": {"color": "#1A2A44"}},
        }}],
        "categoryLabels": [{"properties": {"show": _lit(False)}}],
        "wordWrap": [{"properties": {"show": _lit(True)}}],
    }
    if title:
        objects["title"] = [{"properties": {
            "show": _lit(True),
            "text": {"expr": {"Literal": {"Value": f"'{title}'"}}},
            "fontSize": _lit(9),
            "fontColor": {"solid": {"color": "#0A2240"}},
        }}]
    v["visual"]["objects"] = objects
    return v


def table_visual(name, x, y, w, h, tab, fields: list[tuple[str, str, str | None]],
                 sort_entity: str, sort_prop: str,
                 sort_dir: str = "Descending") -> dict:
    """Tabela com colunas e ordenação padrão por medida."""
    projections = []
    for ftype, prop, label in fields:
        if ftype == "column":
            projections.append(column_proj(prop))
        else:
            projections.append(measure_proj(prop, label))
    v = visual(name, x, y, w, h, tab, "tableEx", {"Values": {"projections": projections}})
    sort_field = _field_ref(sort_entity, sort_prop, "Measure")["field"]
    v["visual"]["query"]["sortDefinition"] = {
        "sort": [{"field": sort_field, "direction": sort_dir}],
        "isDefaultSort": True,
    }
    return v


def pie_visual(name, x, y, w, h, tab, cat_entity: str, cat_prop: str,
               measure_entity: str, measure_prop: str,
               measure_label: str | None = None,
               cat_label: str | None = None,
               title: str | None = None,
               percent_labels: bool = False) -> dict:
    """Gráfico de pizza: categoria + medida (donutChart = compatível PBIR)."""
    v = visual(name, x, y, w, h, tab, "donutChart", {
        "Category": {"projections": [column_proj(cat_prop, cat_entity, cat_label)]},
        "Y": {"projections": [measure_proj_entity(measure_entity, measure_prop, measure_label)]},
    })
    objects: dict = {}
    if title:
        objects["title"] = [{"properties": {
            "show": _lit(True),
            "text": _lit(title),
            "fontSize": _lit(10),
            "fontColor": {"solid": {"color": "#0A2240"}},
        }}]
    if percent_labels:
        objects["labels"] = [{"properties": {
            "show": _lit(True),
            "labelStyle": _lit("Percent of total"),
            "fontSize": _lit(9),
        }}]
    if objects:
        v["visual"]["objects"] = objects
    return v


def kpi_card(name, x, y, w, h, tab, measure: str, label: str,
             precision: int = 0) -> dict:
    """KPI numérico: valor completo + nome da métrica embaixo."""
    v = visual(name, x, y, w, h, tab, "card",
               {"Values": {"projections": [measure_proj(measure, label)]}})
    v["visual"]["objects"] = {
        "labels": [{"properties": {
            "fontSize": _lit(24),
            "labelDisplayUnits": _lit(1),
            "labelPrecision": _lit(precision),
            "color": {"solid": {"color": "#0A2240"}},
        }}],
        "categoryLabels": [{"properties": {
            "show": _lit(True),
            "fontSize": _lit(9),
            "color": {"solid": {"color": "#4A5E78"}},
        }}],
    }
    return v


# Estilos de texto para as caixas de insight (alinhados ao DESIGN_FGV)
LEAD_STYLE = {"fontFamily": "Segoe UI Semibold", "fontSize": "12pt",
              "color": "#0A2240", "fontWeight": "bold"}
BODY_STYLE = {"fontFamily": "Segoe UI", "fontSize": "10pt", "color": "#1A2A44"}
LEGEND_TITLE = {"fontFamily": "Segoe UI Semibold", "fontSize": "9pt",
                "color": "#0A2240", "fontWeight": "bold"}
LEGEND_BODY = {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": "#4A5E78"}


def textbox(name, x, y, w, h, tab, lead: str, body: str) -> dict:
    """Caixa de texto com um rótulo em negrito (lead) seguido do corpo do insight."""
    text_runs = [{"value": lead, "textStyle": LEAD_STYLE}]
    if body:
        text_runs.append({"value": body, "textStyle": BODY_STYLE})
    return {
        "$schema": f"{SCHEMA}/visualContainer/1.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": tab, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [
                    {"properties": {"paragraphs": [
                        {"textRuns": text_runs, "horizontalTextAlignment": "left"}
                    ]}}
                ]
            },
            "drillFilterOtherVisuals": True,
        },
    }


def slicer_programa(name, x, y, w, h, tab) -> dict:
    """Sidebar: lista clicável de programas (modo Basic, filtra todos os visuais)."""
    v = visual(name, x, y, w, h, tab, "slicer",
               {"Values": {"projections": [column_proj("programa")]}})
    v["visual"]["objects"] = {
        "data": [{"properties": {
            "mode": _lit("Basic"),
        }}],
        "header": [{"properties": {
            "show": _lit(True),
            "text": _lit("Programas"),
        }}],
        "selection": [{"properties": {
            "singleSelect": _lit(True),
        }}],
        "searchBox": [{"properties": {
            "show": _lit(False),
        }}],
    }
    v["visual"]["syncGroup"] = {
        "groupName": "ProgramaSync",
        "fieldChanges": True,
        "filterChanges": True,
    }
    return v


def slicer_data(name, x, y, w, h, tab) -> dict:
    """Slicer de data (intervalo de/até) com título."""
    v = visual(name, x, y, w, h, tab, "slicer",
               {"Values": {"projections": [column_proj("data", "Calendario", "Data")]}})
    v["visual"]["objects"] = {
        "data": [{"properties": {
            "mode": _lit("Between"),
        }}],
        "header": [{"properties": {
            "show": _lit(True),
            "text": _lit("Período (de/até)"),
        }}],
    }
    v["visual"]["syncGroup"] = {
        "groupName": "DataSync",
        "fieldChanges": True,
        "filterChanges": True,
    }
    return v


def legend_textbox(name, x, y, w, h, tab, lines: list[tuple[str, str]]) -> dict:
    """Legenda compacta: lista de (rótulo, explicação)."""
    paragraphs = []
    if lines:
        paragraphs.append({
            "textRuns": [{"value": "Legenda", "textStyle": LEGEND_TITLE}],
            "horizontalTextAlignment": "left",
        })
    for label, explanation in lines:
        paragraphs.append({
            "textRuns": [
                {"value": f"{label}: ", "textStyle": LEGEND_TITLE},
                {"value": explanation, "textStyle": LEGEND_BODY},
            ],
            "horizontalTextAlignment": "left",
        })
    return {
        "$schema": f"{SCHEMA}/visualContainer/1.0.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": tab, "width": w, "height": h, "tabOrder": tab},
        "visual": {
            "visualType": "textbox",
            "objects": {
                "general": [{"properties": {"paragraphs": paragraphs}}]
            },
            "drillFilterOtherVisuals": False,
        },
    }


def deploy_report_from_layout() -> None:
    """Copia o snapshot report_layout/ para o .Report (preserva edições manuais)."""
    import shutil

    src_pages = os.path.join(LAYOUT_DIR, "pages")
    dst_def = os.path.join(REPORT_DIR, "definition")
    dst_pages = os.path.join(dst_def, "pages")

    for fname in ("report.json", "version.json"):
        shutil.copy2(os.path.join(LAYOUT_DIR, fname), os.path.join(dst_def, fname))

    if os.path.isdir(dst_pages):
        shutil.rmtree(dst_pages)
    shutil.copytree(src_pages, dst_pages)

    src_res = os.path.join(LAYOUT_DIR, "StaticResources", "RegisteredResources")
    dst_res = os.path.join(REPORT_DIR, "StaticResources", "RegisteredResources")
    if os.path.isdir(src_res):
        os.makedirs(dst_res, exist_ok=True)
        for fname in os.listdir(src_res):
            shutil.copy2(os.path.join(src_res, fname), os.path.join(dst_res, fname))


def gerar_relatorio():
    # .platform
    w_json(os.path.join(REPORT_DIR, ".platform"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "Report", "displayName": PROJ},
        "config": {"version": "2.0", "logicalId": "b2b2b2b2-2222-4222-8222-222222222222"},
    })

    # definition.pbir → aponta para o modelo por caminho relativo.
    # version 4.0 = PBIR moderno (lê a pasta definition/). version 1.0 = legado (ignora a pasta).
    w_json(os.path.join(REPORT_DIR, "definition.pbir"), {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
        "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{PROJ}.SemanticModel"}},
    })

    if os.path.isdir(LAYOUT_DIR):
        deploy_report_from_layout()
        return

    # Tema CLARO FGV (ref: educacao-executiva.fgv.br) — fundo claro, cards brancos,
    # azul-marinho nos títulos/KPIs, dourado no realce. Ver DESIGN_FGV.md.
    w_json(os.path.join(REPORT_DIR, "StaticResources", "RegisteredResources", "tema.json"), {
        "name": "TemaFGVClaro",
        "dataColors": ["#1C5BA8", "#E0A800", "#0A2240", "#5B8FD4", "#C8A24B", "#3FA7B5", "#8FB3E0"],
        "background": "#FFFFFF",      # fundo dos visuais (cards brancos)
        "foreground": "#1A2A44",      # texto/rótulos (azul-escuro)
        "tableAccent": "#1C5BA8",
        "good": "#1C8A5B",
        "neutral": "#1C5BA8",
        "bad": "#C0392B",
        "maximum": "#0A2240",
        "minimum": "#8FB3E0",
        "textClasses": {
            "label":   {"color": "#1A2A44", "fontFace": "Segoe UI"},
            "callout": {"color": "#0A2240", "fontFace": "Segoe UI Semibold"},
            "title":   {"color": "#0A2240", "fontFace": "Segoe UI Semibold"},
            "header":  {"color": "#0A2240", "fontFace": "Segoe UI Semibold"},
        },
        "visualStyles": {
            "*": {
                "*": {
                    "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
                    "border": [{"show": True, "color": {"solid": {"color": "#E3E8F0"}}, "radius": 10}],
                    "title": [{"show": True, "fontColor": {"solid": {"color": "#0A2240"}},
                               "fontSize": 12, "fontFamily": "Segoe UI Semibold"}],
                }
            },
            "page": {
                "*": {
                    "background": [{"color": {"solid": {"color": "#F4F6FA"}}, "transparency": 0}],
                    "outspace": [{"color": {"solid": {"color": "#F4F6FA"}}, "transparency": 0}],
                }
            },
            "card": {
                "*": {
                    "labels": [{"labelDisplayUnits": 1, "fontSize": 24}],
                    "categoryLabels": [{"show": True, "fontSize": 9}],
                }
            },
        },
    })

    # version.json (obrigatório no PBIR moderno) — declara a versão do formato de definição
    w_json(os.path.join(REPORT_DIR, "definition", "version.json"), {
        "$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json",
        "version": "2.0.0",
    })

    # report.json (nível do relatório) com referência ao tema
    w_json(os.path.join(REPORT_DIR, "definition", "report.json"), {
        "$schema": f"{SCHEMA}/report/1.0.0/schema.json",
        "layoutOptimization": "None",
        "themeCollection": {
            "customTheme": {
                "name": "tema.json",
                "type": "RegisteredResources",
                "reportVersionAtImport": "5.55",
            }
        },
        "resourcePackages": [
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "tema.json", "path": "tema.json", "type": "CustomTheme"}]}
        ],
        "settings": {},
    })

    # pages.json — Conselho (shareholder) + Operacional (dia a dia)
    w_json(os.path.join(REPORT_DIR, "definition", "pages", "pages.json"), {
        "$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
        "pageOrder": ["pgConselho", "pgUnico"],
        "activePageName": "pgUnico",
    })

    import shutil

    def write_page(page_name: str, display_name: str, visuais: list) -> None:
        """Escreve page.json + recria a pasta de visuais (limpa órfãos)."""
        pdir = os.path.join(REPORT_DIR, "definition", "pages", page_name)
        w_json(os.path.join(pdir, "page.json"), {
            "$schema": f"{SCHEMA}/page/1.0.0/schema.json",
            "name": page_name,
            "displayName": display_name,
            "displayOption": "FitToPage",
            "height": 720,
            "width": 1280,
        })
        vroot = os.path.join(pdir, "visuals")
        if os.path.isdir(vroot):
            shutil.rmtree(vroot)
        for vid, vobj in visuais:
            w_json(os.path.join(vroot, vid, "visual.json"), vobj)

    # Remove páginas antigas (pgExec / pgEficiencia) se existirem
    pages_root = os.path.join(REPORT_DIR, "definition", "pages")
    for old_page in ("pgExec", "pgEficiencia"):
        old_dir = os.path.join(pages_root, old_page)
        if os.path.isdir(old_dir):
            shutil.rmtree(old_dir)

    # Layout 1280×720 — sidebar esquerda (programas + período), conteúdo à direita.
    SIDE_X, SIDE_W = 16, 260
    CX = SIDE_X + SIDE_W + 16   # início da área de conteúdo (292)
    CW = 1280 - CX - 16         # largura útil do conteúdo (972)

    # ============================================================
    # PÁGINA ÚNICA — Podcasts FGV (volume + eficiência)
    visuais_unico = [
        # --- Sidebar esquerda ---
        ("slicerData", slicer_data("slicerData", SIDE_X, 36, SIDE_W, 112, 100)),
        ("slicerPrograma", slicer_programa(
            "slicerPrograma", SIDE_X, 160, SIDE_W, 548, 101)),
        # --- Faixa 1: volume (4 cards) ---
        ("cardPlays", kpi_card(
            "cardPlays", CX, 36, 222, 108, 0, "Plays Atual",
            "Plays totais (consolidado)")),
        ("cardCrescPlays", kpi_card(
            "cardCrescPlays", CX + 232, 36, 222, 108, 1, "Var Plays",
            "Var. plays (no período)")),
        ("cardSeguidores", kpi_card(
            "cardSeguidores", CX + 464, 36, 222, 108, 2, "Seguidores Atual",
            "Seguidores totais (consolidado)")),
        ("cardCrescSeguidores", kpi_card(
            "cardCrescSeguidores", CX + 696, 36, 222, 108, 3, "Var Seguidores",
            "Var. seguidores (no período)")),
        # --- Faixa 2: eficiência + legenda ---
        ("cardPlaysSeg", kpi_card(
            "cardPlaysSeg", CX, 156, 300, 108, 4, "Plays por Seguidor",
            "Plays por seguidor (consolidado)", precision=1)),
        ("cardConcentracao", insight_card(
            "cardConcentracao", CX + 312, 156, 300, 108, 5, "Top 3 Detalhe", 10,
            title="Top 3 por plays")),
        ("txtLegenda", legend_textbox(
            "txtLegenda", CX + 624, 156, CW - 624, 108, 6, [
                (
                    "Δ plays / Δ seguidores",
                    "variação no intervalo do slicer (consolidado no último dia vs. primeiro dia).",
                ),
                (
                    "Top 3 por plays",
                    "% total + nomes dos 3 programas com mais plays "
                    "(card ao lado).",
                ),
            ])),
        ("cardPeriodo", insight_card(
            "cardPeriodo", CX, 268, 320, 44, 9, "Período Análise", 9)),
        ("cardNotaSnapshot", insight_card(
            "cardNotaSnapshot", CX + 332, 268, CW - 332, 44, 10, "Nota Snapshot", 9)),
        # --- Gráficos operacionais ---
        ("barCrescimento", visual(
            "barCrescimento", CX, 316, CW, 120, 11, "barChart",
            {"Category": {"projections": [column_proj("programa")]},
             "Y": {"projections": [measure_proj("Var Plays")]}})),
        ("barProgramas", visual(
            "barProgramas", CX, 444, (CW - 16) // 2, 134, 11, "barChart",
            {"Category": {"projections": [column_proj("programa")]},
             "Y": {"projections": [measure_proj("Plays Atual")]}})),
        ("barEficiencia", visual(
            "barEficiencia", CX + (CW - 16) // 2 + 16, 444, (CW - 16) // 2, 134, 12,
            "barChart",
            {"Category": {"projections": [column_proj("programa")]},
             "Y": {"projections": [measure_proj("Plays por Seguidor")]}})),
        ("colGenero", visual(
            "colGenero", CX, 586, (CW - 16) // 2, 122, 13, "clusteredColumnChart",
            {"Category": {"projections": [column_proj("programa")]},
             "Y": {"projections": [measure_proj("Homens"),
                                   measure_proj("Mulheres"),
                                   measure_proj("Outros")]}})),
        ("barConversao", visual(
            "barConversao", CX + (CW - 16) // 2 + 16, 586, (CW - 16) // 2, 122, 14,
            "barChart",
            {"Category": {"projections": [column_proj("programa")]},
             "Y": {"projections": [measure_proj("Conversão Seguidores")]}})),
    ]
    write_page("pgUnico", "Podcasts FGV — Visão Geral", visuais_unico)

    # ============================================================
    # PÁGINA CONSELHO — visão shareholder
    # KPIs · narrativa · tabelas ranking · pizzas demografia · rodapé
    half_w = (CW - 16) // 2
    visuais_conselho = [
        # --- Sidebar esquerda ---
        ("slicerData", slicer_data("slicerData", SIDE_X, 32, SIDE_W, 112, 100)),
        ("slicerPrograma", slicer_programa(
            "slicerPrograma", SIDE_X, 156, SIDE_W, 544, 101)),
        # --- KPIs ---
        ("cardPlays", kpi_card(
            "cardPlays", CX, 32, 222, 118, 0, "Plays Atual",
            "Plays totais (consolidado)")),
        ("cardCrescPlays", kpi_card(
            "cardCrescPlays", CX + 232, 32, 222, 118, 1, "Var Plays",
            "Var. plays (no período)")),
        ("cardPlaysSeg", kpi_card(
            "cardPlaysSeg", CX + 464, 32, 222, 118, 2, "Plays por Seguidor",
            "Plays por seguidor (consolidado)", precision=1)),
        ("cardConcentracao", insight_card(
            "cardConcentracao", CX + 696, 32, 222, 118, 3, "Top 3 Detalhe", 9,
            title="Top 3 por plays")),
        ("cardPeriodo", insight_card(
            "cardPeriodo", CX, 154, 360, 44, 4, "Período Análise", 9)),
        ("cardNotaSnapshot", insight_card(
            "cardNotaSnapshot", CX + 372, 154, CW - 372, 44, 5, "Nota Snapshot", 9)),
        ("cardResumo", insight_card(
            "cardResumo", CX, 204, CW, 48, 6, "Resumo Executivo", 10)),
        ("cardEngajamento", insight_card(
            "cardEngajamento", CX, 258, half_w, 40, 7, "Destaque Engajamento", 10)),
        ("cardOportunidade", insight_card(
            "cardOportunidade", CX + half_w + 16, 258, half_w, 40, 8,
            "Destaque Oportunidade", 10)),
        # --- Tabelas ranking (shareholder) ---
        ("tblEficiencia", table_visual(
            "tblEficiencia", CX, 306, half_w, 158, 9,
            [("column", "programa", None),
             ("measure", "Plays por Seguidor", "Plays / seguidor")],
            "Spotify", "Plays por Seguidor")),
        ("tblVarPlays", table_visual(
            "tblVarPlays", CX + half_w + 16, 306, half_w, 158, 10,
            [("column", "programa", None), ("measure", "Var Plays", "Var. plays")],
            "Spotify", "Var Plays")),
        # --- Pizzas: gênero (sem Outros) + faixa etária ---
        ("pieGenero", pie_visual(
            "pieGenero", CX, 474, half_w, 168, 11,
            "DemografiaGenero", "Genero", "DemografiaGenero", "Pct Audiencia",
            "Audiência %", cat_label="Gênero",
            title="Audiência por gênero", percent_labels=True)),
        ("cardFaixaEtaria", insight_card(
            "cardFaixaEtaria", CX + half_w + 16, 474, half_w, 40, 12,
            "Faixa Etária Principal", 11, title="Faixa etária principal")),
        ("pieIdade", pie_visual(
            "pieIdade", CX + half_w + 16, 520, half_w, 122, 13,
            "Spotify", "top_faixa_etaria", "Spotify", "Plays por Faixa",
            "Plays", cat_label="Faixa etária",
            title="Plays por faixa etária")),
        ("cardPeriodo", insight_card(
            "cardPeriodo", CX, 652, 360, 44, 14, "Período Análise", 9)),
        ("cardUltimaColeta", insight_card(
            "cardUltimaColeta", CX + 376, 652, 200, 44, 15, "Última Coleta", 9)),
        ("txtRodape", textbox(
            "txtRodape", CX + 584, 652, CW - 584, 52, 16,
            "",
            "Fonte: Spotify for Creators · Coleta automática SpotiScript · FGV DICOM")),
    ]
    write_page("pgConselho", "Visão Conselho — Podcasts FGV", visuais_conselho)


def main():
    paths.ensure_data_dir()
    os.makedirs(PBIP_DIR, exist_ok=True)
    gerar_pbip_root()
    gerar_modelo()
    gerar_relatorio()
    print(f"[OK] Projeto PBIP gerado em: {PBIP_DIR}")
    print(f"     Abra: {paths.PBIP_FILE}")
    print(f"     Parâmetro PastaDados = {DATA_DIR}")
    if os.path.isdir(LAYOUT_DIR):
        print(f"     Relatório: layout salvo em report_layout/ (edições preservadas)")


if __name__ == "__main__":
    main()
