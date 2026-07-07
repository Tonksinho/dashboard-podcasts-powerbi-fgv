"""
SpotiScript FGV - Extrator de métricas de podcasts do Spotify for Creators.

Uso:
    python spotiscrap.py

    # Com token via variável de ambiente (útil para agendamento)
    $env:SPOTIFY_BEARER = "Bearer eyJ..."
    python spotiscrap.py

O script é apenas o ponto de entrada. Toda a lógica está em:
    models.py, spotify_client.py, parsers.py, writers.py, orchestrator.py
"""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

from orchestrator import AnalyticsOrchestrator
from spotify_client import PersistedQueryRegistry, SpotifyCreatorsClient
from writers import ConsoleReporter, GoogleSheetsWriter, JsonlBackupWriter

LAST_RUN_STATS: dict[str, int] = {"success": 0, "total": 0}


def setup_logging() -> logging.Logger:
    """Configura logging profissional em console + arquivo."""
    log = logging.getLogger()
    if log.handlers:
        return log

    log.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    log.addHandler(ch)

    # Arquivo
    fh = logging.FileHandler("spotiscrap.log", encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(formatter)
    log.addHandler(fh)

    return log


def load_config_from_env() -> dict:
    """Carrega configurações não-sensíveis do .env com valores padrão."""
    load_dotenv()

    return {
        "spreadsheet_key": os.getenv("SPREADSHEET_KEY", ""),
        "sheet_name": os.getenv("SHEET_NAME", "0"),
        "service_account_file": os.getenv("SERVICE_ACCOUNT_FILE", ""),
    }


def resolve_path(path: str) -> str:
    """Resolve caminho relativo ao diretório do script (importante no Windows)."""
    if os.path.isabs(path):
        return path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, path)


def main() -> int:
    # Tenta forçar UTF-8 no Windows para reduzir problemas com emojis
    import sys
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger = setup_logging()
    logger.info("Spotify Podcast Data Extractor (v2 - arquitetura limpa)")

    if os.getenv("CLEAR_SHEET_ON_RUN", "false").lower() in ("true", "1", "yes"):
        logger.info("⚠️  Modo CLEAR_SHEET_ON_RUN ativado → planilha será limpa a cada execução (histórico será perdido)")
    else:
        logger.info("Modo histórico ativado → cada execução acrescenta um snapshot datado (upsert por data+programa)")

    # 1. Token (nunca armazenado em arquivo)
    raw_token = os.getenv("SPOTIFY_BEARER", "").strip()
    if not raw_token:
        try:
            raw_token = input("Enter Spotify Bearer Token (não será salvo): ").strip()
        except (EOFError, KeyboardInterrupt):
            logger.error("Entrada cancelada. Saindo.")
            return 1

    if not raw_token:
        logger.error("Nenhum token fornecido. Saindo.")
        return 1

    # 2. Configuração
    cfg = load_config_from_env()
    service_account = resolve_path(cfg["service_account_file"])

    # 3. Registry + Client
    registry = PersistedQueryRegistry()
    loaded = registry.load_from_file()
    if loaded == 0:
        logger.info("Usando apenas as 2 operações core (sem campos avançados).")

    client = SpotifyCreatorsClient(raw_token, registry=registry)

    # 4. Writers
    use_emojis = sys.platform != "win32"

    # PADRÃO agora é PRESERVAR O HISTÓRICO (clear_sheet=False): cada execução acrescenta
    # um snapshot datado, permitindo gráficos de tendência no Looker.
    # Para voltar ao comportamento antigo (apagar tudo a cada run), defina CLEAR_SHEET_ON_RUN=true.
    clear_sheet = os.getenv("CLEAR_SHEET_ON_RUN", "false").lower() in ("true", "1", "yes")

    writers: list = [ConsoleReporter(show_bars=True, use_emojis=use_emojis)]
    if cfg["spreadsheet_key"] and service_account and os.path.isfile(service_account):
        writers.append(
            GoogleSheetsWriter(
                spreadsheet_key=cfg["spreadsheet_key"],
                sheet_name=cfg["sheet_name"],
                service_account_file=service_account,
                clear_on_run=clear_sheet,
            )
        )
    else:
        logger.info("Google Sheets desativado (configure SPREADSHEET_KEY e SERVICE_ACCOUNT_FILE no .env).")
    writers.append(JsonlBackupWriter("spotify-backup.local.jsonl"))

    # 5. Orquestrador
    orchestrator = AnalyticsOrchestrator(
        client=client,
        writers=writers,
        registry=registry,
        use_dynamic_shows=True,
    )

    # 6. Execução
    global LAST_RUN_STATS
    try:
        success_count, total = orchestrator.run()
        LAST_RUN_STATS = {"success": success_count, "total": total}
        if success_count <= 0:
            logger.error("Nenhum podcast foi capturado com sucesso.")
            return 1
        if success_count < total:
            logger.warning(
                f"Captura parcial: {success_count}/{total} podcasts. "
                "O agendador da tarde pode tentar novamente."
            )
            return 2
        return 0
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário.")
        LAST_RUN_STATS = {"success": 0, "total": 0}
        return 130
    except Exception as e:
        logger.exception(f"Erro fatal durante execução: {e}")
        LAST_RUN_STATS = {"success": 0, "total": 0}
        return 1


if __name__ == "__main__":
    sys.exit(main())
