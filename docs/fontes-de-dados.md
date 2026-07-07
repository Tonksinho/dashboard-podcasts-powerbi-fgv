# Fontes de dados (versão pública / demo)

## Dashboard Spotify — FGV (portfólio)

| Item | Caminho |
|------|---------|
| PBIP | `powerbi/dashboards/spotify-fgv/SpotifyDashboardFGV.pbip` |
| CSV demo | `data/sample/spotify_dashboard.csv` |
| Parâmetro Power Query | `PastaDados` → pasta absoluta de `data/sample` |
| Pipeline Python | `pipeline/coletar.py` |

## Dados sensíveis

Esta versão **não inclui**:

- Credenciais Spotify (`.env`)
- Service account Google Sheets
- Métricas reais de produção
- IDs de shows em produção (use `podcasts.json` local)

## Uso em produção (privado)

O ambiente interno FGV usa repositório privado, CSV operacional e credenciais em variáveis de ambiente — fora deste repo público.