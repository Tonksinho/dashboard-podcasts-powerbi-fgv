"""Caminhos do repositório público (demo/portfólio)."""
from __future__ import annotations

import os

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(PIPELINE_DIR)

PBIP_DIR = os.path.join(REPO_ROOT, "powerbi", "dashboards", "spotify-fgv")
PROJ = "SpotifyDashboardFGV"
PBIP_FILE = os.path.join(PBIP_DIR, f"{PROJ}.pbip")

# CSV de demonstração — sem dados operacionais reais
DATA_DIR = os.path.join(REPO_ROOT, "data", "sample")
DATA_CSV = os.path.join(DATA_DIR, "spotify_dashboard.csv")

SPOTI_DATA_DIR = os.path.join(PIPELINE_DIR, "data")
LAYOUT_DIR = os.path.join(PIPELINE_DIR, "report_layout")


def ensure_data_dir() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)