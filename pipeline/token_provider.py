"""
token_provider.py — Opção 1 (via CDP): obtém o Bearer do Spotify for Creators
reusando uma sessão do SEU Chrome de verdade, persistida em disco.

Por que CDP e não launch_persistent_context?
- O Chromium "for Testing" do Playwright, em modo visível, é instável nesta máquina
  (abre e fecha na hora — provável bloqueio de antivírus/política do Windows).
- O harvester deste projeto sempre funcionou abrindo o Chrome REAL com porta de
  debug e conectando via CDP. Reusamos esse caminho comprovado.

Como funciona:
- Abrimos o Chrome instalado (assinado, confiável) com --remote-debugging-port e um
  diretório de PERFIL dedicado (os cookies de sessão ficam salvos nele).
- Se a sessão expirar, o script tenta login automático com SPOTIFY_EMAIL e
  SPOTIFY_PASSWORD do arquivo .env (fora do git).
- Depois navega no Creators e captura o header `authorization`.

Uso:
    python token_provider.py
    python token_provider.py --login   # força janela visível (login manual, fallback)

Credenciais em .env (copie de .env.example):
    SPOTIFY_EMAIL=podcast@fgv.br
    SPOTIFY_PASSWORD=...

SEGURANÇA: o perfil salvo e o .env são credenciais. Ficam FORA do git.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time

from dotenv import load_dotenv
from playwright.sync_api import Error as PlaywrightError, Page, sync_playwright

# Perfil dedicado, fora do repositório (é uma credencial — não pode ir pro git)
PROFILE_DIR = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
    "SpotiScript", "chrome-profile",
)

CREATORS_URL = "https://creators.spotify.com/"
LOGIN_URL = "https://accounts.spotify.com/login?continue=https%3A%2F%2Fcreators.spotify.com%2F"
CDP_PORT = 9222
WAIT_S = 90        # tempo máx. esperando a requisição GraphQL após sessão ativa
LOGIN_WAIT_S = 300  # tempo máx. para login manual (--login)
AUTO_LOGIN_WAIT_S = 120  # tempo máx. no fluxo de login automático

CHROME_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

EMAIL_SELECTORS = (
    'input#username',
    'input[data-testid="login-username"]',
    'input[name="username"]',
    'input[type="email"]',
    'input[autocomplete="username"]',
)

PASSWORD_SELECTORS = (
    'input#password',
    'input[data-testid="login-password"]',
    'input[name="password"]',
    'input[type="password"]',
    'input[autocomplete="current-password"]',
)

CONTINUE_LABELS = ("Continue", "Continuar", "Avançar", "Next")
LOGIN_LABELS = ("Log in", "Entrar", "Login", "Iniciar sesión")
ENTRAR_COM_SENHA_SELECTORS = (
    'a[data-encore-id="buttonTertiary"][href*="method=password"]',
    'a[href*="method=password"]',
    'a:has-text("Entrar com senha")',
)
CONTINUAR_SPOTIFY_SELECTORS = (
    'span.e-10492-button-primary__inner:has-text("Continuar com o Spotify")',
    'button:has(span:has-text("Continuar com o Spotify"))',
    'span:has-text("Continuar com o Spotify")',
)
CONTINUAR_SPOTIFY_LABELS = ("Continuar com o Spotify", "Continue with Spotify")
ENTRAR_CREATORS_SELECTORS = (
    'a[data-encore-id="buttonSecondary"][href="/pod/login"]',
    'a[href="/pod/login"][data-encore-id="buttonSecondary"]',
    'a[href="/pod/login"]',
    'a.e-10501-legacy-button-secondary[href="/pod/login"]',
)


def _is_bearer(value: str | None) -> bool:
    return bool(value) and value.lower().startswith("bearer ")


def _is_graph(url: str) -> bool:
    """Reconhece o endpoint GraphQL do Creators, tolerando renomeações de host."""
    return "spotify" in url and "graph" in url


def _find_chrome() -> str | None:
    for path in CHROME_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def _port_aberta(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _carregar_credenciais() -> tuple[str, str] | None:
    """Lê email/senha do .env na pasta do projeto."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    load_dotenv(os.path.join(base_dir, ".env"))

    email = os.getenv("SPOTIFY_EMAIL", "").strip()
    password = os.getenv("SPOTIFY_PASSWORD", "").strip()
    if email and password:
        return email, password
    return None


def _primeiro_visivel(page: Page, selectors: tuple[str, ...], timeout_ms: int = 8000):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            locator.wait_for(state="visible", timeout=timeout_ms)
            return locator
        except Exception:
            continue
    return None


def _clicar_botao(page: Page, labels: tuple[str, ...], timeout_ms: int = 8000) -> bool:
    for label in labels:
        try:
            btn = page.get_by_role("button", name=label, exact=False).first
            btn.wait_for(state="visible", timeout=timeout_ms)
            btn.click(timeout=5000)
            return True
        except Exception:
            pass
        try:
            btn = page.locator(f'button:has-text("{label}")').first
            btn.wait_for(state="visible", timeout=2000)
            btn.click(timeout=5000)
            return True
        except Exception:
            continue
    return False


def _tem_botao_entrar(page: Page) -> bool:
    for selector in ENTRAR_CREATORS_SELECTORS:
        try:
            if page.locator(selector).first.is_visible(timeout=1000):
                return True
        except Exception:
            continue
    return False


def _tem_continuar_spotify(page: Page) -> bool:
    for label in CONTINUAR_SPOTIFY_LABELS:
        try:
            if page.get_by_text(label, exact=True).first.is_visible(timeout=1000):
                return True
        except Exception:
            continue
    return False


def _precisa_login(page: Page) -> bool:
    url = page.url.lower()
    if "accounts.spotify.com" in url:
        return True
    if "/pod/login" in url:
        return True
    if _tem_botao_entrar(page):
        return True
    if _tem_continuar_spotify(page):
        return True
    if _primeiro_visivel(page, EMAIL_SELECTORS, timeout_ms=1500):
        return True
    return False


def _clicar_entrar_creators(page: Page) -> bool:
    """Etapa 1: link 'Entrar' na home do Creators (href=/pod/login)."""
    for selector in ENTRAR_CREATORS_SELECTORS:
        try:
            link = page.locator(selector).first
            link.wait_for(state="visible", timeout=8000)
            link.click(timeout=5000)
            return True
        except Exception:
            continue
    try:
        page.get_by_role("link", name="Entrar", exact=True).click(timeout=5000)
        return True
    except Exception:
        return False


def _clicar_continuar_spotify(page: Page) -> bool:
    """Etapa 2: botão 'Continuar com o Spotify' em /pod/login."""
    for selector in CONTINUAR_SPOTIFY_SELECTORS:
        try:
            alvo = page.locator(selector).first
            alvo.wait_for(state="visible", timeout=8000)
            alvo.click(timeout=5000)
            return True
        except Exception:
            continue
    for label in CONTINUAR_SPOTIFY_LABELS:
        try:
            alvo = page.get_by_text(label, exact=True).first
            alvo.wait_for(state="visible", timeout=8000)
            alvo.click(timeout=5000)
            return True
        except Exception:
            pass
        try:
            page.locator(f'button:has-text("{label}")').first.click(timeout=5000)
            return True
        except Exception:
            pass
        try:
            page.locator(f'span:has-text("{label}")').first.click(timeout=5000)
            return True
        except Exception:
            continue
    return False


def _aguardar_accounts(page: Page, timeout_s: int = 25) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if "accounts.spotify.com" in page.url.lower():
            return True
        page.wait_for_timeout(500)
    return False


def _clicar_entrar_com_senha(page: Page) -> bool:
    """Etapa 4: link 'Entrar com senha' após preencher o e-mail."""
    for selector in ENTRAR_COM_SENHA_SELECTORS:
        try:
            link = page.locator(selector).first
            link.wait_for(state="visible", timeout=8000)
            link.click(timeout=5000)
            return True
        except Exception:
            continue
    try:
        page.get_by_role("link", name="Entrar com senha", exact=True).click(timeout=5000)
        return True
    except Exception:
        return False


def _login_accounts_spotify(page: Page, email: str, password: str) -> bool:
    """
    Etapas 3–5 em accounts.spotify.com:
      3) preencher #username
      4) clicar 'Entrar com senha'
      5) preencher #password e confirmar
    """
    email_input = _primeiro_visivel(page, EMAIL_SELECTORS)
    if not email_input:
        print("[ERRO] Campo de usuário (#username) não encontrado.", file=sys.stderr)
        return False

    try:
        email_input.fill(email, timeout=5000)
    except Exception as exc:
        print(f"[ERRO] Não consegui preencher o e-mail: {exc}", file=sys.stderr)
        return False

    page.wait_for_timeout(1500)

    print("[INFO] Etapa 4/5: clicando em 'Entrar com senha'...", file=sys.stderr)
    if not _clicar_entrar_com_senha(page):
        # Fallback: alguns fluxos usam Continue antes da senha
        if not _clicar_botao(page, CONTINUE_LABELS):
            print("[ERRO] Link 'Entrar com senha' não encontrado.", file=sys.stderr)
            return False

    page.wait_for_timeout(2000)

    password_input = _primeiro_visivel(page, PASSWORD_SELECTORS, timeout_ms=15000)
    if not password_input:
        print("[ERRO] Campo de senha (#password) não apareceu.", file=sys.stderr)
        return False

    print("[INFO] Etapa 5/5: preenchendo senha e confirmando...", file=sys.stderr)
    try:
        password_input.fill(password, timeout=5000)
    except Exception as exc:
        print(f"[ERRO] Não consegui preencher a senha: {exc}", file=sys.stderr)
        return False

    if not _clicar_botao(page, LOGIN_LABELS):
        try:
            page.locator('button[data-testid="login-button"]').first.click(timeout=5000)
        except Exception:
            print("[ERRO] Botão final de login não encontrado.", file=sys.stderr)
            return False

    return True


def _aguardar_pos_login(page: Page, timeout_s: int = 45) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        page.wait_for_timeout(1000)
        url = page.url.lower()
        if "creators.spotify.com" in url and "/pod/login" not in url and "/login" not in url:
            return True
        if "accounts.spotify.com" not in url:
            return True
    return False


def _fazer_login_automatico(page: Page, email: str, password: str) -> bool:
    """
    Fluxo Creators:
      1) Home -> clicar 'Entrar' (/pod/login)
      2) /pod/login -> clicar 'Continuar com o Spotify'
      3) accounts.spotify.com -> email, senha
    """
    if not _precisa_login(page):
        print("[INFO] Sessão já ativa — login automático não necessário.", file=sys.stderr)
        return True

    print("[INFO] Sessão expirada — iniciando login automático...", file=sys.stderr)

    url = page.url.lower()

    # Etapa 1 — Entrar (home do Creators)
    if "creators.spotify.com" in url and "/pod/login" not in url and "accounts.spotify.com" not in url:
        if _tem_botao_entrar(page):
            print("[INFO] Etapa 1/5: clicando em 'Entrar'...", file=sys.stderr)
            if not _clicar_entrar_creators(page):
                print("[ERRO] Botão 'Entrar' não encontrado no Creators.", file=sys.stderr)
                return False
            page.wait_for_timeout(2500)

    # Etapa 2 — Continuar com o Spotify
    if "/pod/login" in page.url.lower() or _tem_continuar_spotify(page):
        print("[INFO] Etapa 2/5: clicando em 'Continuar com o Spotify'...", file=sys.stderr)
        if not _clicar_continuar_spotify(page):
            print("[ERRO] Botão 'Continuar com o Spotify' não encontrado.", file=sys.stderr)
            return False

    # Aguarda a tela de login Spotify com o campo #username
    print("[INFO] Aguardando formulário de login Spotify (#username)...", file=sys.stderr)
    campo_pronto = False
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if _primeiro_visivel(page, EMAIL_SELECTORS, timeout_ms=800):
            campo_pronto = True
            break
        if "accounts.spotify.com" in page.url.lower() or "login" in page.url.lower():
            page.wait_for_timeout(500)
            continue
        page.wait_for_timeout(500)

    if not campo_pronto:
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)
        except Exception as exc:
            print(f"[AVISO] Fallback login URL falhou: {exc}", file=sys.stderr)
            return False

    print("[INFO] Etapa 3/5: preenchendo e-mail (#username)...", file=sys.stderr)
    if not _login_accounts_spotify(page, email, password):
        return False

    if _aguardar_pos_login(page):
        print("[OK] Login automático concluído.", file=sys.stderr)
        return True

    print("[ERRO] Login não redirecionou a tempo (captcha/2FA?).", file=sys.stderr)
    return False


def _abrir_chrome(chrome: str, offscreen: bool) -> subprocess.Popen:
    """Abre o Chrome real com porta de debug e perfil dedicado."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    args = [
        chrome,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-extensions",
    ]
    if offscreen:
        args += [
            "--window-position=-32000,-32000",
            "--window-size=1280,900",
            "--disable-background-timer-throttling",
            "--disable-backgrounding-occluded-windows",
            "--disable-renderer-backgrounding",
        ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if _port_aberta(CDP_PORT):
            return proc
        time.sleep(0.5)
    return proc


def capturar_token(login: bool = False, auto_login: bool = True) -> str | None:
    """
    Captura o Bearer.

    - login=True: aguarda login manual na janela visível.
    - auto_login=True: se a sessão expirou, usa SPOTIFY_EMAIL/PASSWORD do .env.
    """
    chrome = _find_chrome()
    if not chrome:
        print(
            "[ERRO] Chrome não encontrado nos caminhos padrão. Edite CHROME_CANDIDATES.",
            file=sys.stderr,
        )
        return None

    credenciais = _carregar_credenciais() if auto_login and not login else None
    if auto_login and not login and not credenciais:
        print(
            "[AVISO] SPOTIFY_EMAIL/SPOTIFY_PASSWORD não encontrados no .env — "
            "login automático desativado.",
            file=sys.stderr,
        )

    proc: subprocess.Popen | None = None
    iniciou_chrome = False

    if _port_aberta(CDP_PORT):
        print("[INFO] Reutilizando Chrome já aberto na porta 9222.", file=sys.stderr)
    else:
        proc = _abrir_chrome(chrome, offscreen=False)
        iniciou_chrome = True
        if not login:
            print(
                "  (uma janela do Chrome vai abrir por alguns segundos e fechar sozinha)",
                file=sys.stderr,
            )

    captured: dict[str, str | None] = {"token": None}

    def on_request(req) -> None:
        url = req.url
        if _is_graph(url):
            if captured["token"] is None:
                auth = req.headers.get("authorization")
                if _is_bearer(auth):
                    captured["token"] = auth
                    print("  [✓ token capturado]", file=sys.stderr)

    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            context.on("page", lambda pg: pg.on("request", on_request))
            page = context.pages[0] if context.pages else context.new_page()
            page.on("request", on_request)

            try:
                page.goto(CREATORS_URL, wait_until="domcontentloaded", timeout=WAIT_S * 1000)
            except Exception:
                pass

            limite = LOGIN_WAIT_S if login else WAIT_S
            if login:
                print("\n>> Faça login no Spotify Creators na janela do Chrome que abriu.", file=sys.stderr)
                print(">> Depois abra a aba de Audience/estatísticas de qualquer podcast.", file=sys.stderr)
                print(">> Pode deixar — quando eu capturar o token, encerro sozinho.", file=sys.stderr)
                print(f">> (aguardando até {limite}s)\n", file=sys.stderr)

            inicio = time.monotonic()
            recarregou = False
            tentou_login_auto = False

            while captured["token"] is None and (time.monotonic() - inicio) < limite:
                try:
                    page.wait_for_timeout(1000)
                except PlaywrightError:
                    if captured["token"] is not None:
                        break
                    try:
                        page = context.pages[-1] if context.pages else context.new_page()
                        page.on("request", on_request)
                        page.goto(CREATORS_URL, wait_until="domcontentloaded", timeout=30000)
                        continue
                    except PlaywrightError:
                        print("[AVISO] Chrome fechou antes de capturar o token.", file=sys.stderr)
                        return None

                if captured["token"] is not None:
                    break

                tempo_decorrido = time.monotonic() - inicio
                sessao_expirada = _precisa_login(page)
                sem_token_demais = tempo_decorrido >= 20

                if (
                    not login
                    and credenciais
                    and not tentou_login_auto
                    and (sessao_expirada or sem_token_demais)
                ):
                    tentou_login_auto = True
                    if _fazer_login_automatico(page, credenciais[0], credenciais[1]):
                        if captured["token"] is None:
                            try:
                                page.goto(
                                    CREATORS_URL,
                                    wait_until="domcontentloaded",
                                    timeout=WAIT_S * 1000,
                                )
                            except Exception:
                                pass
                            inicio = time.monotonic()
                            limite = max(limite, AUTO_LOGIN_WAIT_S)
                            recarregou = False
                    elif captured["token"] is None:
                        print(
                            "[AVISO] Login automático falhou. Verifique .env ou use --login.",
                            file=sys.stderr,
                        )

                if captured["token"] is not None:
                    break

                if not login and not recarregou and (time.monotonic() - inicio) > 15:
                    recarregou = True
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=WAIT_S * 1000)
                    except Exception:
                        pass
    finally:
        # No modo automático mantemos o Chrome aberto (perfil persistente + reuso na porta 9222).
        if login and iniciou_chrome and proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    return captured["token"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Obtém o Bearer do Spotify for Creators (via CDP).")
    ap.add_argument(
        "--login",
        action="store_true",
        help="aguarda login manual na janela visível (ignora login automático)",
    )
    ap.add_argument(
        "--no-auto-login",
        action="store_true",
        help="não tenta login automático com credenciais do .env",
    )
    args = ap.parse_args()

    token = capturar_token(login=args.login, auto_login=not args.no_auto_login)

    if not token:
        print(
            "[ERRO] Não capturei o token. Verifique .env (SPOTIFY_EMAIL/PASSWORD) "
            "ou rode:  python token_provider.py --login",
            file=sys.stderr,
        )
        return 1

    if args.login:
        print(
            "\n[OK] Sessão salva! Daqui pra frente o login automático deve funcionar.",
            file=sys.stderr,
        )

    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())