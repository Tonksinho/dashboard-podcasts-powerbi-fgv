"""
Domain models for Spotify Podcast Analytics (SpotiScript FGV).

Todos os dataclasses são imutáveis (frozen=True) para maior segurança
e previsibilidade no fluxo de dados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass(frozen=True)
class Podcast:
    """Representa um podcast/show no Spotify for Creators."""
    nome: str
    uri: str

    def __post_init__(self):
        if not self.uri.startswith("spotify:show:"):
            # Permite URIs já normalizadas ou apenas o ID
            object.__setattr__(self, "uri", f"spotify:show:{self.uri}")


@dataclass(frozen=True)
class AudienceMetrics:
    """Métricas principais de audiência (plays + seguidores + demografia)."""
    plays: int = 0
    followers: int = 0
    pct_male: float = 0.0
    pct_female: float = 0.0
    top_age_group: str = "N/A"

    # Dados brutos úteis para debugging ou relatórios futuros
    gender_raw_counts: dict[str, int] = field(default_factory=dict)
    age_raw: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class PodcastReport:
    """
    Relatório de um podcast em uma data específica.
    Mantemos só os campos principais (os avançados foram removidos a pedido).
    """
    date: str
    podcast: Podcast
    audience: AudienceMetrics

    # Metadados internos (não usados na escrita)
    raw_responses: dict[str, dict] = field(default_factory=dict, repr=False)

    # ============================================================
    # Métodos utilitários para compatibilidade com sistemas legados
    # ============================================================

    # Colunas principais para Google Sheets + Looker
    # Removidas as colunas avançadas (show_type, monetization, etc) pois quase sempre vêm N/A
    SHEETS_HEADERS = [
        "data",
        "programa",
        "plays",
        "seguidores",
        "pct_homens",
        "pct_mulheres",
        "pct_outros",
        "top_faixa_etaria",
    ]

    def to_sheets_row(self) -> list:
        """
        Retorna linha limpa e organizada para Looker / análise.
        Valores numéricos reais (não strings com %).
        """
        pct_outros = round(100 - self.audience.pct_male - self.audience.pct_female, 1)
        if pct_outros < 0:
            pct_outros = 0.0

        return [
            self.date,
            self.podcast.nome,
            self.audience.plays,
            self.audience.followers,
            round(self.audience.pct_male, 1),
            round(self.audience.pct_female, 1),
            pct_outros,
            self.audience.top_age_group,
        ]

    def get_sheets_headers(self) -> list:
        """Retorna os cabeçalhos das colunas."""
        return self.SHEETS_HEADERS.copy()

    def to_jsonl_dict(self) -> dict:
        """Formato usado no backup fgv-spotify-backup.jsonl (também limpo para análise)."""
        pct_outros = round(100 - self.audience.pct_male - self.audience.pct_female, 1)
        if pct_outros < 0:
            pct_outros = 0.0

        return {
            "date": self.date,
            "programa": self.podcast.nome,
            "plays": self.audience.plays,
            "seguidores": self.audience.followers,
            "pct_homens": round(self.audience.pct_male, 1),
            "pct_mulheres": round(self.audience.pct_female, 1),
            "pct_outros": pct_outros,
            "top_faixa_etaria": self.audience.top_age_group,
        }

    @property
    def display_name(self) -> str:
        return self.podcast.nome


def today_str() -> str:
    """Retorna a data de hoje no formato usado pelo sistema (DD/MM/YYYY)."""
    return date.today().strftime("%d/%m/%Y")
