# Pipeline de podcasts institucionais com Python e Power BI PBIP — projeto desenvolvido na FGV (versão pública demo)

**Automação de coleta de métricas Spotify Creators + dashboard executivo em Power BI**, com versionamento Git do PBIP. Esta é a **versão pública de portfólio**: dados sintéticos, sem credenciais e sem métricas operacionais reais.

**GitHub:** https://github.com/Tonksinho/dashboard-podcasts-powerbi-fgv

> Projeto implementado no contexto de **podcasts institucionais da FGV EAESP**. O repositório de produção permanece privado; este repo demonstra arquitetura, stack e resultado visual.

---

## Problema e resultado

| Antes | Depois |
|-------|--------|
| Métricas em planilhas manuais | Pipeline Python → CSV → Power BI |
| Dashboard binário sem histórico Git | **PBIP** versionado (diff de visuais e modelo) |
| Dificuldade de sync entre máquinas | Scripts de auto-pull + `enviar_dashboard.bat` |

**Resultado (ambiente interno):** monitoramento de **12 podcasts**, coleta automatizada **2x/dia**, dashboard com KPIs de plays, engajamento e demografia para gestores. *Nesta versão demo:* CSV com **3 programas fictícios** e números arredondados.

---

## Stack

| Camada | Ferramenta |
|--------|------------|
| Coleta | Python 3.10+, Scrapling/Playwright, GraphQL Spotify Creators |
| Orquestração | `orchestrator.py` + writers (CSV; Sheets opcional) |
| BI | Power BI Desktop PBIP, DAX, Power Query |
| Versionamento | Git, PowerShell (auto-pull) |
| Dependências | `streamlit` N/A — ver `pipeline/requirements.txt` |

Principais libs: `scrapling[fetchers]>=0.2.99`, `python-dotenv>=1.0.0`, `playwright>=1.44.0`

---

## Rodar em 3 comandos

```powershell
git clone https://github.com/Tonksinho/dashboard-podcasts-powerbi-fgv.git
cd dashboard-podcasts-powerbi-fgv\pipeline && pip install -r requirements.txt
# Abra powerbi\dashboards\spotify-fgv\SpotifyDashboardFGV.pbip no Power BI
```

**Importante:** no Power BI, defina o parâmetro **`PastaDados`** como o caminho **absoluto** da pasta `data\sample` do seu clone (ex.: `C:\dev\dashboard-podcasts-powerbi-fgv\data\sample`).

---

## Estrutura

```
dashboard-podcasts-powerbi-fgv/
├── README.md
├── pipeline/                 # Coleta Python (SpotiScript)
│   ├── coletar.py
│   ├── orchestrator.py
│   ├── podcasts.example.json   # Configure seus shows (copie para podcasts.json)
│   └── requirements.txt
├── powerbi/dashboards/spotify-fgv/   # PBIP
├── data/sample/                # CSV demo (sem dados reais)
├── scripts/                    # Auto-pull Git
└── docs/
```

---

## O que NÃO está neste repo (propositalmente)

- `.env` / senhas Spotify
- Service account Google (`*.json`)
- `fgv-spotify-backup.jsonl` e logs de produção
- IDs e métricas reais dos 12 podcasts

Para rodar coleta real: copie `podcasts.example.json` → `podcasts.json`, preencha URIs dos shows, crie `.env` a partir de `.env.example`.

---

## Decisões técnicas

**PBIP + Git** — modelo e relatório em texto (TMDL/JSON), revisável em PR e sincronizável entre analistas.

**Writers desacoplados** — `orchestrator` não conhece destino; CSV e Google Sheets são plugáveis (Sheets desligado por padrão sem credencial).

**CSV demo isolado** — portfólio público sem vazar KPIs internos; produção usa pasta e repo privados.

**Lista de podcasts via JSON** — URIs sensíveis ao negócio ficam em `podcasts.json` local (gitignored), não no código.

---

## Repositório privado (produção FGV)

O ambiente interno usa repo privado `powerbi-dashboards` com dados operacionais — não incluído aqui.