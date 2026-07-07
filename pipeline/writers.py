"""
Abstrações de escrita de dados (Writers).

O Orchestrator não sabe se está escrevendo em Google Sheets, JSONL ou console.
Isso é o coração da melhoria de arquitetura.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Protocol

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from models import PodcastReport

logger = logging.getLogger(__name__)


# ============================================================
# Protocol / Interface
# ============================================================

class DataWriter(Protocol):
    """Qualquer destino de dados deve implementar este protocolo."""

    def write(self, report: PodcastReport) -> bool:
        """Escreve um relatório. Retorna True em caso de sucesso."""
        ...


# ============================================================
# Implementações concretas
# ============================================================

class GoogleSheetsWriter:
    """
    Escreve na planilha Google PRESERVANDO O HISTÓRICO (séries temporais),
    o que é o ideal para gráficos de tendência no Looker.

    Modos:
        clear_on_run=False (PADRÃO, recomendado):
            NÃO apaga nada. Faz "upsert" por (data, programa):
              - se já existe uma linha para aquela data + podcast, atualiza no lugar;
              - caso contrário, adiciona uma nova linha.
            Assim cada execução vira um snapshot datado, e rodar duas vezes no
            mesmo dia NÃO duplica linhas.
        clear_on_run=True (legado):
            Apaga tudo e regrava do zero (comportamento antigo — perde histórico).
    """

    def __init__(
        self,
        spreadsheet_key: str,
        sheet_name: str = "0",
        service_account_file: str = "",
        clear_on_run: bool = False,
    ):
        self.spreadsheet_key = spreadsheet_key
        self.sheet_name = sheet_name
        self.service_account_file = service_account_file
        self.clear_on_run = clear_on_run
        self._worksheet = None
        self._headers_written = False
        self._cleared_this_run = False
        # Estado do modo histórico (upsert)
        self._existing_loaded = False
        self._row_index: dict[tuple[str, str], int] = {}
        self._next_row = 2
        self._connect()

    def _connect(self) -> None:
        if not self.service_account_file:
            logger.warning("Service account file não configurado. Google Sheets desativado.")
            return

        try:
            scope = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.service_account_file, scope)
            client = gspread.authorize(creds)
            spreadsheet = client.open_by_key(self.spreadsheet_key)

            if self.sheet_name.isdigit():
                self._worksheet = spreadsheet.get_worksheet(int(self.sheet_name))
            else:
                self._worksheet = spreadsheet.worksheet(self.sheet_name)

            logger.info("[OK] Conectado ao Google Sheets com sucesso")
        except Exception as e:
            logger.error(f"Erro ao conectar no Google Sheets: {e}")
            self._worksheet = None

    def _clear_sheet_if_needed(self, report: PodcastReport) -> None:
        """Apaga todos os dados antigos da planilha (usado apenas quando clear_on_run=True)."""
        if not self._worksheet or self._cleared_this_run:
            return

        try:
            # Limpa a planilha inteira
            self._worksheet.clear()
            logger.info("[OK] Dados antigos da planilha foram apagados (clear_on_run=True)")

            # Escreve os cabeçalhos logo em seguida
            headers = report.get_sheets_headers()
            self._worksheet.append_row(headers)
            self._headers_written = True
            self._cleared_this_run = True

            logger.info(f"[OK] Cabeçalhos reescritos ({len(headers)} colunas)")

        except Exception as e:
            logger.error(f"Erro ao limpar a planilha: {e}")

    def _prepare_existing(self, report: PodcastReport) -> None:
        """
        Modo histórico: lê a planilha UMA vez, garante os cabeçalhos e monta um
        índice (data, programa) -> número da linha, para permitir o upsert.
        """
        if self._existing_loaded:
            return
        self._existing_loaded = True

        headers = report.get_sheets_headers()
        try:
            all_values = self._worksheet.get_all_values()
        except Exception as e:
            logger.warning(f"Não foi possível ler a planilha existente: {e}")
            all_values = []

        has_header = bool(all_values) and bool(all_values[0]) and all_values[0][0] == "data"
        if not has_header:
            try:
                self._worksheet.insert_row(headers, index=1)
                all_values = [headers] + all_values
                logger.info(f"[OK] Cabeçalhos inseridos na planilha ({len(headers)} colunas)")
            except Exception as e:
                logger.warning(f"Não foi possível inserir cabeçalhos: {e}")
        self._headers_written = True

        # Indexa as linhas de dados já existentes (linha 1 = cabeçalho)
        self._row_index = {}
        for sheet_row, rowvals in enumerate(all_values[1:], start=2):
            if len(rowvals) >= 2 and rowvals[0]:
                self._row_index[(rowvals[0], rowvals[1])] = sheet_row
        self._next_row = len(all_values) + 1

        if self._row_index:
            logger.info(f"[OK] Histórico preservado: {len(self._row_index)} linhas já na planilha.")

    def _update_row(self, rownum: int, row: list) -> None:
        """Atualiza uma linha existente no lugar (compatível entre versões do gspread)."""
        cells = self._worksheet.range(rownum, 1, rownum, len(row))
        for cell, value in zip(cells, row):
            cell.value = value
        self._worksheet.update_cells(cells)

    def write(self, report: PodcastReport) -> bool:
        if not self._worksheet:
            logger.warning("Google Sheets não conectado. Pulando escrita.")
            return False

        # --- Modo legado: apaga tudo e só anexa (perde histórico) ---
        if self.clear_on_run:
            if not self._cleared_this_run:
                self._clear_sheet_if_needed(report)
            try:
                self._worksheet.append_row(report.to_sheets_row())
                return True
            except Exception as e:
                logger.error(f"Erro ao gravar linha na planilha: {e}")
                return False

        # --- Modo histórico (padrão): upsert por (data, programa) ---
        self._prepare_existing(report)
        try:
            row = report.to_sheets_row()
            key = (str(report.date), report.podcast.nome)
            if key in self._row_index:
                # Já existe snapshot dessa data+podcast → atualiza no lugar
                self._update_row(self._row_index[key], row)
            else:
                # Novo snapshot → adiciona ao final e registra no índice
                self._worksheet.append_row(row)
                self._row_index[key] = self._next_row
                self._next_row += 1
            return True
        except Exception as e:
            logger.error(f"Erro ao gravar linha na planilha: {e}")
            return False


class JsonlBackupWriter:
    """Append em arquivo JSON Lines (backup local resiliente)."""

    def __init__(self, path: str = "fgv-spotify-backup.jsonl"):
        self.path = path

    def write(self, report: PodcastReport) -> bool:
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(report.to_jsonl_dict(), ensure_ascii=False) + "\n")
            return True
        except Exception as e:
            logger.error(f"Erro ao escrever backup JSONL: {e}")
            return False


def desenhar_barra(valor: int, total: int, char: str = "█") -> str:
    """Desenha barra de progresso visual (igual à versão original)."""
    if total <= 0:
        return ""
    largura_max = 20
    preenchido = int((valor / total) * largura_max)
    return char * preenchido + "░" * (largura_max - preenchido)


class ConsoleReporter:
    """
    Reporter rico no terminal.
    Reproduz a experiência visual da versão original (com barras, gênero detalhado, faixas etárias etc).
    """

    def __init__(self, show_bars: bool = True, use_emojis: bool = True):
        self.show_bars = show_bars
        self.use_emojis = use_emojis

    def _e(self, emoji: str, fallback: str = "") -> str:
        """Retorna emoji ou fallback seguro para Windows."""
        return emoji if self.use_emojis else fallback

    def write(self, report: PodcastReport) -> bool:
        p = self._e
        print(f"\n{p('🎙️ ', '>> ')}PROGRAMA: {report.display_name}")

        aud = report.audience
        print(f"   {p('📈 ', '')}Audiência: {aud.plays:,} plays | {aud.followers:,} seguidores")

        # === GÊNERO ===
        print(f"   {p('👫 ', '')}Gênero:")
        gender_counts = aud.gender_raw_counts or {}
        total_gender = sum(gender_counts.values()) or 1

        homens = gender_counts.get("MALE", 0)
        mulheres = gender_counts.get("FEMALE", 0)
        outros = gender_counts.get("OTHER_AGGREGATED", 0)

        if homens == 0 and mulheres == 0:
            homens = int(aud.pct_male / 100 * total_gender) if total_gender > 0 else 0
            mulheres = int(aud.pct_female / 100 * total_gender) if total_gender > 0 else 0

        if homens > 0 or mulheres > 0:
            if homens > 0:
                pct = (homens / total_gender * 100) if total_gender > 0 else 0
                barra = desenhar_barra(homens, total_gender) if self.show_bars else ""
                print(f"      {'Homens'.ljust(9)}: {homens:>6} | {pct:>5.1f}% {barra}")
            if mulheres > 0:
                pct = (mulheres / total_gender * 100) if total_gender > 0 else 0
                barra = desenhar_barra(mulheres, total_gender) if self.show_bars else ""
                print(f"      {'Mulheres'.ljust(9)}: {mulheres:>6} | {pct:>5.1f}% {barra}")
            if outros > 0:
                pct = (outros / total_gender * 100) if total_gender > 0 else 0
                barra = desenhar_barra(outros, total_gender) if self.show_bars else ""
                print(f"      {'Outros'.ljust(9)}: {outros:>6} | {pct:>5.1f}% {barra}")

        # === FAIXAS ETÁRIAS ===
        age_list = aud.age_raw or []
        if age_list:
            print(f"   {p('🎂 ', '')}Faixas Etárias (Ranking):")
            total_age = sum(a.get("genderBreakdown", {}).get("total", 0) for a in age_list) or 1
            sorted_ages = sorted(
                age_list,
                key=lambda x: x.get("genderBreakdown", {}).get("total", 0),
                reverse=True,
            )
            for age in sorted_ages[:4]:
                val = age.get("genderBreakdown", {}).get("total", 0)
                pct = (val / total_age * 100) if total_age > 0 else 0
                name = age.get("displayName", "N/A")
                barra = desenhar_barra(val, total_age, "▓") if self.show_bars else ""
                print(f"      {name.ljust(9)}: {val:>6} | {pct:>5.1f}% {barra}")

        # (Campos avançados removidos: não existem mais no PodcastReport e causavam
        #  AttributeError. O modelo atual expõe apenas date/podcast/audience.)

        print("-" * 55)
        return True
