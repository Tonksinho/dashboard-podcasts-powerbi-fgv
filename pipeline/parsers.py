"""
Funções puras de parsing das respostas GraphQL do Spotify Creators.

Todas as funções recebem dicionários crus retornados pela API e devolvem
estruturas limpas (ou None quando não há dados). Não têm efeitos colaterais.
"""

from __future__ import annotations

from typing import Any, Optional

from models import AudienceMetrics


# ============================================================
# Parsing de métricas principais (header + demografia)
# ============================================================

def parse_audience_metrics(header_response: Optional[dict], demo_response: Optional[dict]) -> AudienceMetrics:
    """
    Combina as duas chamadas principais e produz AudienceMetrics limpo.
    Mantém exatamente a mesma lógica do código original (incluindo agregação de "Outros").
    """
    plays = 0
    followers = 0

    if header_response and isinstance(header_response, dict):
        s = header_response.get("data", {}).get("showByShowUri", {})
        stats = s.get("streamsAndDownloadsAllTime", {})
        plays = stats.get("showViews", {}).get("viewCount", 0) or 0

        folls_raw = s.get("followersAllTime", {}).get("analyticsValue", {}).get("analyticsValue", {}).get("value", 0)
        followers = folls_raw or 0

    pct_male = 0.0
    pct_female = 0.0
    top_age = "N/A"
    gender_counts: dict[str, int] = {}
    age_raw: list[dict] = []

    if demo_response and isinstance(demo_response, dict):
        demo = (
            demo_response.get("data", {})
            .get("showByShowUri", {})
            .get("showStreamsFaceted", {})
            .get("analyticsValue", {})
            .get("analyticsValue", {})
        )

        # Gênero
        g_list = demo.get("genderBreakdown", {}).get("counts", []) or demo.get("genderDistribution", {}).get("counts", [])
        if g_list:
            total_gender = sum(c.get("count", 0) for c in g_list)
            outros = 0
            for g in g_list:
                gender = g.get("gender")
                count = g.get("count", 0) or 0
                gender_counts[gender] = count

                if gender == "MALE":
                    pct_male = (count / total_gender * 100) if total_gender > 0 else 0
                elif gender == "FEMALE":
                    pct_female = (count / total_gender * 100) if total_gender > 0 else 0
                else:
                    outros += count

            if outros > 0 and total_gender > 0:
                # Apenas registramos; o log de "Outros" é responsabilidade do reporter
                gender_counts["OTHER_AGGREGATED"] = outros

        # Idade
        age_list = demo.get("ageBreakdown", []) or []
        age_raw = age_list
        if age_list:
            total_age = sum(a.get("genderBreakdown", {}).get("total", 0) for a in age_list)
            if total_age > 0:
                sorted_ages = sorted(
                    age_list,
                    key=lambda x: x.get("genderBreakdown", {}).get("total", 0),
                    reverse=True,
                )
                top_age = sorted_ages[0].get("displayName", "N/A") if sorted_ages else "N/A"

    return AudienceMetrics(
        plays=plays,
        followers=followers,
        pct_male=round(pct_male, 1),
        pct_female=round(pct_female, 1),
        top_age_group=top_age,
        gender_raw_counts=gender_counts,
        age_raw=age_raw,
    )


# (Funções de parsing de campos avançados foram removidas a pedido do usuário,
# pois as colunas quase sempre vinham como N/A)
