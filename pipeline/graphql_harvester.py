"""
GraphQL Persisted Query Harvester for Spotify Creators

Usa Scrapling StealthySession (modo CDP) com capture_xhr para interceptar
requisições graph-pq enquanto o usuário navega no Spotify Creators.

Fluxo de uso:

1. Feche TODAS as janelas do Chrome (inclusive o ícone na bandeja).
2. Rode o comando abaixo no PowerShell para abrir um Chrome LIMPO com a porta de debug.
3. Peça para a pessoa logar normalmente no Spotify Creators nessa janela.
4. Em outro PowerShell, rode este script:
   cd "C:/dev/dashboard-podcasts-powerbi-fgv/pipeline"
   python graphql_harvester.py

5. O script vai conectar no Chrome que já está aberto.
6. A pessoa navega normalmente (principalmente Audience, mudando datas, abrindo episódios, etc.).
7. O harvester vai mostrar as operações GraphQL que aparecerem.
8. Quando quiser parar, pressione Ctrl+C.

O resultado é salvo em: spotify_creators_operations.json
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from scrapling.fetchers import StealthySession

OUTPUT_FILE = "spotify_creators_operations.json"
CDP_URL = "http://127.0.0.1:9222"
CAPTURE_XHR_PATTERN = r"(graph-pq|creators-graph\.spotify\.com)"

# Armazena operações únicas: (operationName, sha) -> dicionário completo
known_operations: dict[tuple[str, str], dict[str, Any]] = {}


def save_operations(silent: bool = False) -> None:
    """Salva de forma segura usando arquivo temporário + rename atômico."""
    data = list(known_operations.values())
    data.sort(key=lambda x: x.get("operationName", ""))

    temp_file = OUTPUT_FILE + ".tmp"
    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, OUTPUT_FILE)
        if not silent:
            print(f"\n💾 Salvo: {len(data)} operações únicas em {OUTPUT_FILE}")
    except Exception as e:
        print(f"[AVISO] Falha ao salvar JSON: {e}")


def register_operation(url: str, post_data: dict[str, Any]) -> None:
    """Extrai e registra uma operação GraphQL persistida a partir do payload POST."""
    op_name = post_data.get("operationName", "N/A")
    persisted = post_data.get("extensions", {}).get("persistedQuery", {})
    sha = persisted.get("sha256Hash")

    if not sha or not op_name or op_name == "N/A":
        return

    key = (op_name, sha)
    if key in known_operations:
        return

    entry = {
        "operationName": op_name,
        "sha256Hash": sha,
        "variables_example": post_data.get("variables", {}),
        "url": url,
        "timestamp": time.time(),
    }
    known_operations[key] = entry
    print(f"📌 Nova operação: {op_name} | SHA: {sha[:16]}...")
    save_operations()


def intercept_response(response) -> None:
    """
    Intercepta respostas XHR/fetch que batem com capture_xhr e lê o POST
    original (operationName + sha256Hash) via response.request.
    """
    url = response.url
    if not re.search(CAPTURE_XHR_PATTERN, url):
        return

    try:
        post_data = response.request.post_data_json or {}
        if isinstance(post_data, dict):
            register_operation(url, post_data)
    except Exception:
        pass


def attach_listeners(context) -> None:
    """Registra o listener de capture_xhr em páginas existentes e futuras."""
    for page in context.pages:
        page.on("response", intercept_response)

    def on_new_page(page) -> None:
        page.on("response", intercept_response)

    context.on("page", on_new_page)


def get_logged_in_context(session: StealthySession):
    """
    Retorna o contexto original do Chrome (onde o usuário já está logado).

    O StealthySession cria um contexto extra ao conectar via CDP; usamos o
    primeiro contexto, que é o perfil aberto manualmente.
    """
    browser = session.browser
    if browser is None or not browser.contexts:
        raise RuntimeError("Nenhum contexto encontrado no Chrome conectado via CDP.")
    return browser.contexts[0]


def safe_teardown(session: StealthySession) -> None:
    """
    Desconecta o Playwright sem fechar o contexto do usuário no Chrome.

    session.close() fecharia o context ativo — aqui só encerramos a conexão CDP.
    """
    session._is_alive = False
    session.context = None

    if getattr(session, "browser", None):
        try:
            session.browser.close()
        except Exception:
            pass
        session.browser = None

    if getattr(session, "playwright", None):
        try:
            session.playwright.stop()
        except Exception:
            pass
        session.playwright = None


def main() -> None:
    print("🚀 Spotify Creators GraphQL Harvester (Scrapling StealthySession + CDP)\n")

    session = StealthySession(
        cdp_url=CDP_URL,
        capture_xhr=CAPTURE_XHR_PATTERN,
        google_search=False,
        headless=True,
    )

    try:
        print("[INFO] Conectando ao Chrome via Scrapling StealthySession (CDP)...")
        session.__enter__()
        context = get_logged_in_context(session)
        attach_listeners(context)

        print("[OK] Conectado com sucesso ao Chrome!\n")
        print("✅ Harvester rodando!")
        print("   → Peça para a pessoa logar no Spotify Creators.")
        print("   → Depois que logar, navegue bastante (Audience + mudar datas + F5, abrir episódios, etc.).")
        print("   → O script vai mostrar as novas operações que aparecerem.")
        print("   → Pressione Ctrl+C quando quiser parar.\n")

        while True:
            time.sleep(15)
            if known_operations:
                print(
                    f"📊 Progresso: {len(known_operations)} operações únicas capturadas até agora..."
                )

    except KeyboardInterrupt:
        print("\n🛑 Parando harvester...")
    except Exception as e:
        print(f"\n[ERRO] Não foi possível conectar ao Chrome.")
        print(f"Detalhe: {e}")
        print("\nCertifique-se de ter aberto o Chrome LIMPO com este comando no PowerShell:")
        print('  Get-Process chrome -ErrorAction SilentlyContinue | Stop-Process -Force')
        print('  $p = "C:\\temp\\chrome-harvest-clean"')
        print('  New-Item -ItemType Directory -Path $p -Force | Out-Null')
        print(
            '  & "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" '
            '--remote-debugging-port=9222 --user-data-dir="$p" '
            '--no-first-run --no-default-browser-check --disable-extensions'
        )
    finally:
        save_operations()
        safe_teardown(session)
        print(f"\nFinalizado. Total de operações únicas salvas: {len(known_operations)}")
        print(f"Arquivo: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()