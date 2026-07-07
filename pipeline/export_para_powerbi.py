"""
Exportador para o Power BI.

Lê o backup `fgv-spotify-backup.jsonl` (que tem schema misturado de versões
diferentes do SpotiScript) e gera um CSV LIMPO e deduplicado em
``C:/DadosPowerBI/spotify-fgv/spotify_dashboard.csv``, pronto para ser consumido pelo dashboard.

Normalizações feitas:
- Reconcilia `seguidores` vs `followers`.
- Converte percentuais em texto ("74.6%") para número (74.6).
- Calcula `pct_outros` quando ausente (100 - homens - mulheres, nunca negativo).
- Converte a data DD/MM/YYYY -> ISO YYYY-MM-DD (evita ambiguidade de locale no Power BI).
- Deduplica por (data, programa) — fica 1 snapshot por dia por podcast.

Uso:
    python export_para_powerbi.py
"""

from __future__ import annotations

import csv
import json
import os

import spoti_paths as paths

SRC = paths.BACKUP_JSONL
OUT_DIR = paths.DATA_DIR
OUT = paths.DATA_CSV

COLS = ["data", "programa", "plays", "seguidores",
        "pct_homens", "pct_mulheres", "pct_outros", "top_faixa_etaria"]


def to_float_pct(v) -> float | None:
    """Converte 74.6 ou '74.6%' -> 74.6. Retorna None se não der."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("%", "").replace(",", ".").strip()
    try:
        return float(s)
    except ValueError:
        return None


def iso_date(d: str) -> str:
    """DD/MM/YYYY -> YYYY-MM-DD (mantém original se não casar)."""
    try:
        dd, mm, yy = d.split("/")
        return f"{yy}-{mm.zfill(2)}-{dd.zfill(2)}"
    except Exception:
        return d


def main() -> int:
    if not os.path.exists(SRC):
        print(f"[ERRO] Backup não encontrado: {SRC}")
        return 1

    rows: dict[tuple[str, str], dict] = {}
    total_lidas = 0

    with open(SRC, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            total_lidas += 1

            data = o.get("date")
            prog = o.get("programa")
            if not data or not prog:
                continue

            seg = o.get("seguidores", o.get("followers"))
            ph = to_float_pct(o.get("pct_homens"))
            pm = to_float_pct(o.get("pct_mulheres"))
            po = to_float_pct(o.get("pct_outros"))
            if po is None and ph is not None and pm is not None:
                po = round(max(0.0, 100.0 - ph - pm), 1)

            rec = {
                "data": iso_date(data),
                "programa": prog,
                "plays": int(o.get("plays") or 0),
                "seguidores": int(seg or 0),
                "pct_homens": round(ph, 1) if ph is not None else 0.0,
                "pct_mulheres": round(pm, 1) if pm is not None else 0.0,
                "pct_outros": round(po, 1) if po is not None else 0.0,
                "top_faixa_etaria": o.get("top_faixa_etaria") or "N/A",
            }
            # dedup por (data, programa) — última ocorrência vence
            rows[(rec["data"], rec["programa"])] = rec

    os.makedirs(OUT_DIR, exist_ok=True)
    data_sorted = sorted(rows.values(), key=lambda r: (r["data"], -r["plays"]))

    # utf-8-sig (BOM) para o Power BI reconhecer acentuação corretamente
    with open(OUT, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in data_sorted:
            w.writerow(r)

    datas = sorted({r["data"] for r in data_sorted})
    print(f"[OK] {total_lidas} linhas lidas -> {len(data_sorted)} linhas limpas (deduplicadas).")
    print(f"[OK] Datas no arquivo: {', '.join(datas)}")
    print(f"[OK] CSV gerado: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
