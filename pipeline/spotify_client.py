"""
Cliente Spotify for Creators (GraphQL Persisted Queries).

Responsável por:
- Gerenciar o registro de hashes (PersistedQueryRegistry)
- Executar requisições autenticadas contra creators-graph.spotify.com
- Oferecer métodos de alto nível com nomes claros
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from scrapling.fetchers import FetcherSession

logger = logging.getLogger(__name__)

URL = "https://creators-graph.spotify.com/v2/graph-pq"

# Hashes core que sempre funcionam (fallback quando o harvester ainda não rodou)
CORE_OPERATIONS: dict[str, str] = {
    "getShowHeaderStats": "2656f0ffa6b3f8fffa02c5fb682425e1318cc5be6e23305330e1f07ed5e32f07",
    "getShowAudienceDemographicsStats": "f5d7195822edfd4796a97674cea46bc0015da7a795aba849eb410139d4b40573",
}


@dataclass
class PersistedQueryRegistry:
    """
    Registro de operações GraphQL persistidas do Spotify Creators.

    Substitui completamente o antigo dicionário global OPERATIONS + load_operations().
    É thread-safe para leitura após carregamento inicial.
    """

    operations: dict[str, str] = field(default_factory=lambda: CORE_OPERATIONS.copy())
    _loaded_from_file: bool = field(default=False, init=False, repr=False)

    def load_from_file(self, path: Optional[str] = None) -> int:
        """
        Carrega operações adicionais do arquivo gerado pelo graphql_harvester.py.
        Retorna a quantidade de novas operações carregadas.
        """
        if path is None:
            # Resolve relativo ao local deste módulo
            base_dir = os.path.dirname(os.path.abspath(__file__))
            path = os.path.join(base_dir, "spotify_creators_operations.json")

        if not os.path.exists(path):
            logger.info("ℹ️  Arquivo de operações do harvester não encontrado. Apenas métricas básicas funcionarão.")
            return 0

        loaded = 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            for entry in data if isinstance(data, list) else []:
                name = entry.get("operationName")
                sha = entry.get("sha256Hash")
                if name and sha and name not in self.operations:
                    self.operations[name] = sha
                    loaded += 1

            if loaded:
                logger.info(f"✅ Carregadas {loaded} operações extras do harvester (novos campos disponíveis).")
                self._loaded_from_file = True

        except Exception as e:
            logger.warning(f"⚠️  Não foi possível carregar {path}: {e}")

        return loaded

    def get(self, operation_name: str) -> Optional[str]:
        """Retorna o SHA256 da operação ou None se não existir."""
        return self.operations.get(operation_name)

    def has(self, operation_name: str) -> bool:
        return operation_name in self.operations

    def available_advanced_operations(self) -> list[str]:
        """Lista operações além das duas core."""
        core = set(CORE_OPERATIONS.keys())
        return [name for name in self.operations if name not in core]


class SpotifyCreatorsClient:
    """
    Cliente de alto nível para a API interna do Spotify for Creators.
    """

    def __init__(self, bearer_token: str, registry: Optional[PersistedQueryRegistry] = None):
        token = bearer_token.strip()
        if not token.lower().startswith("bearer "):
            token = "Bearer " + token

        self._token = token
        self.registry = registry or PersistedQueryRegistry()
        self._fetcher_manager = FetcherSession(
            headers={
                "authorization": self._token,
                "content-type": "application/json",
                "x-creator-client": "microfrontend-analytics",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
                ),
            },
            impersonate="chrome123",
            stealthy_headers=False,
            timeout=15,
            retries=1,
        )
        self._session = self._fetcher_manager.__enter__()

    def close(self) -> None:
        """Encerra a sessão HTTP do Scrapling."""
        if self._fetcher_manager is not None:
            self._fetcher_manager.__exit__(None, None, None)
            self._fetcher_manager = None
            self._session = None

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    @staticmethod
    def _response_json(resp) -> dict[str, Any]:
        encoding = getattr(resp, "encoding", "utf-8") or "utf-8"
        return json.loads(resp.body.decode(encoding))

    # ------------------------------------------------------------------
    # Métodos de baixo nível (usados internamente)
    # ------------------------------------------------------------------

    def _request(
        self,
        operation_name: str,
        variables: dict[str, Any],
        *,
        max_retries: int = 3,
    ) -> Optional[dict[str, Any]] | str:
        """
        Executa uma requisição GraphQL persisted query.

        Retorna:
            - dict com os dados quando sucesso
            - "EXPIRED" quando 401 (token inválido)
            - None em caso de erro após retries
        """
        sha = self.registry.get(operation_name)
        if not sha:
            logger.debug(f"Operação '{operation_name}' não encontrada no registry.")
            return None

        payload = {
            "variables": variables,
            "operationName": operation_name,
            "extensions": {
                "persistedQuery": {"version": 1, "sha256Hash": sha}
            },
        }

        for attempt in range(max_retries):
            try:
                resp = self._session.post(
                    URL,
                    json=payload,
                    timeout=15,
                    stealthy_headers=False,
                )

                if resp.status == 200:
                    return self._response_json(resp)

                if resp.status == 401:
                    return "EXPIRED"

                if resp.status in (429, 503):
                    sleep_time = (attempt + 1) * 3
                    logger.warning(
                        f"API lenta ou com rate limit ({resp.status}). Aguardando {sleep_time}s..."
                    )
                    time.sleep(sleep_time)
                    continue

                logger.warning(f"Resposta inesperada {resp.status} para {operation_name}")

            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                logger.error(f"Erro de rede em {operation_name}: {e}")

        return None

    # ------------------------------------------------------------------
    # Métodos de domínio (API pública limpa)
    # ------------------------------------------------------------------

    def get_show_header_stats(self, show_uri: str) -> Optional[dict]:
        """Estatísticas principais (plays totais + seguidores)."""
        return self._request("getShowHeaderStats", {"showUri": show_uri})

    def get_audience_demographics(self, show_uri: str) -> Optional[dict]:
        """Demografia (gênero + faixa etária)."""
        return self._request(
            "getShowAudienceDemographicsStats",
            {"showUri": show_uri, "dateRangeWindow": "WINDOW_ALL_TIME"},
        )

    def get_user_shows(
        self,
        show_filter: str = "HOSTED_ONLY",
        page: int = 1,
        page_size: int = 50,
    ) -> Optional[dict]:
        """Lista de shows do usuário autenticado (usado para carregamento dinâmico)."""
        sha = self.registry.get("WebGetShowsForUser") or self.registry.get("WebGetUserShows")
        if not sha:
            return None
        # Reutilizamos o nome da operação que existir
        op_name = "WebGetShowsForUser" if self.registry.has("WebGetShowsForUser") else "WebGetUserShows"
        return self._request(op_name, {
            "showFilter": show_filter,
            "currentPage": page,
            "pageSize": page_size,
        })

    # Método get_advanced_field foi removido (campos avançados não são mais usados)

    def is_token_valid(self) -> bool:
        """Teste rápido para verificar se o token ainda é válido."""
        result = self._request(
            "getShowHeaderStats",
            {"showUri": "spotify:show:SUBSTITUA_PELO_SEU_SHOW_ID"},
        )
        return result != "EXPIRED" and result is not None