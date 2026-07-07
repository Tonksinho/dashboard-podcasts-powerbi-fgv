"""
coletar.py — pipeline de coleta completo e (quase) sem intervenção.

Encadeia os três passos:
    1. token_provider  -> obtém o Bearer reusando a sessão Chrome salva (headless)
    2. spotiscrap      -> coleta as métricas do Spotify e grava o snapshot
    3. export_para_powerbi -> regenera o CSV em data/sample (ou pasta configurada)

Uso normal (login automático via .env — SPOTIFY_EMAIL / SPOTIFY_PASSWORD):
    python coletar.py
    python coletar.py --slot manha
    python coletar.py --slot tarde

Depois é só abrir o Power BI Desktop e clicar em Atualizar.

Se o login automático falhar (captcha/2FA), rode manualmente:
    python token_provider.py --login
"""

from __future__ import annotations

import argparse
import os
import sys

import coleta_status
import token_provider


def _abrir_dashboard() -> None:
    """Abre o .pbip no Power BI Desktop (o usuário ainda precisa clicar em Atualizar/F5)."""
    script = os.path.join(os.path.dirname(__file__), "atualizar_dashboard.ps1")
    if not os.path.isfile(script):
        print("       (atualizar_dashboard.ps1 não encontrado — abra o .pbip manualmente)")
        return
    try:
        import subprocess

        subprocess.Popen(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                script,
            ],
            cwd=os.path.dirname(__file__),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        print(f"       (não foi possível abrir o Power BI: {exc})")


def main(slot: str = "manual") -> int:
    coleta_status.append_log(f"[INICIO] slot={slot}")

    if slot == "tarde" and coleta_status.captura_ok_hoje():
        status = coleta_status.load_status() or {}
        msg = (
            f"Coleta da manhã já concluída com sucesso "
            f"({status.get('podcasts_ok', '?')}/{status.get('podcasts_total', '?')} podcasts). "
            "Pulando execução das 15h."
        )
        print(f"[SKIP] {msg}")
        coleta_status.append_log(f"[SKIP] slot=tarde motivo=manha_ok")
        return 0

    print("=== [1/3] Obtendo token do Spotify Creators (sessão salva) ===")
    token = token_provider.capturar_token(login=False)
    if not token:
        msg = "Não foi possível obter token (login automático falhou)."
        print(
            f"\n[ERRO] {msg}\n"
            "       Verifique SPOTIFY_EMAIL/SPOTIFY_PASSWORD no .env\n"
            "       ou rode:  python token_provider.py --login",
            file=sys.stderr,
        )
        coleta_status.write_status(
            ok=False,
            slot=slot,
            exit_code=1,
            message=msg,
        )
        return 1
    os.environ["SPOTIFY_BEARER"] = token
    print("[OK] Token capturado.\n")

    print("=== [2/3] Coletando métricas (spotiscrap) ===")
    import spotiscrap

    rc = spotiscrap.main()
    stats = spotiscrap.LAST_RUN_STATS
    podcasts_ok = int(stats.get("success", 0))
    podcasts_total = int(stats.get("total", 0))

    if rc == 1:
        coleta_status.write_status(
            ok=False,
            slot=slot,
            exit_code=rc,
            podcasts_ok=podcasts_ok,
            podcasts_total=podcasts_total,
            message="spotiscrap falhou",
        )
        print(f"\n[ERRO] spotiscrap retornou código {rc}. Abortando.", file=sys.stderr)
        return rc

    if rc == 2:
        print(
            f"\n[AVISO] Captura parcial ({podcasts_ok}/{podcasts_total}). "
            "Seguindo para export; a tarde pode tentar de novo.",
            file=sys.stderr,
        )

    print("\n=== [3/3] Gerando CSV para o Power BI (export_para_powerbi) ===")
    import export_para_powerbi

    rc = export_para_powerbi.main()
    if rc != 0:
        coleta_status.write_status(
            ok=False,
            slot=slot,
            exit_code=rc,
            podcasts_ok=podcasts_ok,
            podcasts_total=podcasts_total,
            message="export_para_powerbi falhou",
        )
        print(f"\n[ERRO] export retornou código {rc}.", file=sys.stderr)
        return rc

    captura_ok = coleta_status.avaliar_captura(podcasts_ok, podcasts_total)
    coleta_status.write_status(
        ok=captura_ok,
        slot=slot,
        exit_code=0,
        podcasts_ok=podcasts_ok,
        podcasts_total=podcasts_total,
        message="pipeline completo" if captura_ok else "poucos podcasts capturados",
    )

    if captura_ok:
        print("\n=== Pronto! Atualize o Power BI (F5) para ver os dados novos. ===")
        _abrir_dashboard()
    else:
        print(
            f"\n[AVISO] Pipeline terminou, mas só {podcasts_ok}/{podcasts_total} podcasts "
            "foram capturados. A tarde tentará de novo se estiver agendado.",
            file=sys.stderr,
        )
        return 2

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline de coleta SpotiScript")
    parser.add_argument(
        "--slot",
        choices=["manual", "manha", "tarde"],
        default="manual",
        help="Slot do agendador: manha (11h), tarde (15h) ou manual",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    raise SystemExit(main(slot=args.slot))