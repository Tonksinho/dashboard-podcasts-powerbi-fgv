"""
Atualiza report_layout/ com o estado atual do relatório no Power BI Desktop.

Use depois de editar visuais no Desktop e salvar o .pbip:
    python salvar_layout.py
"""
from __future__ import annotations

import os
import shutil

import spoti_paths as paths

PROJ = paths.PROJ
REPORT_DEF = os.path.join(paths.PBIP_DIR, f"{PROJ}.Report", "definition")
LAYOUT_DIR = paths.LAYOUT_DIR
RES_SRC = os.path.join(
    paths.PBIP_DIR, f"{PROJ}.Report", "StaticResources", "RegisteredResources"
)


def main() -> None:
    if not os.path.isdir(REPORT_DEF):
        raise SystemExit(f"Relatório não encontrado: {REPORT_DEF}")

    if os.path.isdir(LAYOUT_DIR):
        shutil.rmtree(LAYOUT_DIR)
    os.makedirs(LAYOUT_DIR, exist_ok=True)

    for fname in ("report.json", "version.json"):
        shutil.copy2(os.path.join(REPORT_DEF, fname), os.path.join(LAYOUT_DIR, fname))

    shutil.copytree(os.path.join(REPORT_DEF, "pages"), os.path.join(LAYOUT_DIR, "pages"))

    if os.path.isdir(RES_SRC):
        dst = os.path.join(LAYOUT_DIR, "StaticResources", "RegisteredResources")
        os.makedirs(dst, exist_ok=True)
        for fname in os.listdir(RES_SRC):
            shutil.copy2(os.path.join(RES_SRC, fname), os.path.join(dst, fname))

    n = sum(1 for _ in os.walk(LAYOUT_DIR) for __ in _[2])
    print(f"[OK] Layout salvo em: {LAYOUT_DIR} ({n} arquivos)")
    print(f"     PBIP fonte: {paths.PBIP_FILE}")
    print("     Próximo gerar_pbip.py vai preservar este formato.")


if __name__ == "__main__":
    main()