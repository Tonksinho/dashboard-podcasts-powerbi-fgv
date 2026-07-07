"""
Controle de status da coleta diária (usado pelo agendador 11h / 15h).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

STATUS_DIR = Path(__file__).resolve().parent / "data" / "coleta_status"
LOG_FILE = Path(__file__).resolve().parent / "data" / "coleta_agendada.log"


def today_iso() -> str:
    return date.today().isoformat()


def status_path(day: Optional[str] = None) -> Path:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    return STATUS_DIR / f"{day or today_iso()}.json"


def append_log(message: str) -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with LOG_FILE.open("a", encoding="utf-8") as fh:
        fh.write(f"{stamp} {message}\n")


def load_status(day: Optional[str] = None) -> Optional[dict[str, Any]]:
    path = status_path(day)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def captura_ok_hoje() -> bool:
    """True se já houve captura bem-sucedida hoje (qualquer slot)."""
    status = load_status()
    return bool(status and status.get("ok"))


def write_status(
    *,
    ok: bool,
    slot: str,
    exit_code: int,
    podcasts_ok: int = 0,
    podcasts_total: int = 0,
    message: str = "",
) -> None:
    payload = {
        "date": today_iso(),
        "ok": ok,
        "slot": slot,
        "exit_code": exit_code,
        "podcasts_ok": podcasts_ok,
        "podcasts_total": podcasts_total,
        "message": message,
        "finished_at": datetime.now().isoformat(timespec="seconds"),
    }
    path = status_path()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    level = "OK" if ok else "FALHA"
    append_log(
        f"[{level}] slot={slot} exit={exit_code} "
        f"podcasts={podcasts_ok}/{podcasts_total} msg={message or '-'}"
    )


def avaliar_captura(podcasts_ok: int, podcasts_total: int) -> bool:
    """Considera captura válida se processou a grande maioria dos podcasts."""
    if podcasts_ok <= 0 or podcasts_total <= 0:
        return False
    minimo = max(1, int(podcasts_total * 0.9))
    return podcasts_ok >= minimo