# AI Project Guide

This file is a fast-start context guide for AI assistants and new contributors.
Read this before exploring the repository in depth.

## 1. What This Project Is

This project is an A-share stock analysis system with:

- a Python multi-agent analysis workflow
- a FastAPI backend
- a React frontend
- local-data-first / snapshot-first data access for unstable market APIs

Its current product goal is not high-frequency trading. It is closer to:

- stock analysis process visualization
- human-readable investment explanation
- thesis / defense-friendly report presentation
- backtesting and workflow demonstration

## 2. Current Top-Level Layout

Important directories:

- `backend/`
  FastAPI app, routers, API state, backend services
- `frontend/`
  React app, main UI, report view, DCF tool page
- `src/agents/`
  Core analysis agents
- `src/tools/`
  Legacy-compatible shared data access, especially `src/tools/api.py`
- `src/core/`
  Newer runtime structure, especially workflow engine entrypoints
- `src/data/`
  Newer data-layer structure
- `src/models/`
  Newer persistence/domain model structure
- `src/database/`, `src/backtesting/`, `src/rag/`, `src/experiments/`, `src/crawler/`
  Compatibility packages kept so old imports continue to work
- `tests/unit/`
  Current working unit tests for compatibility and data-layer behavior
- `docs/`
  Design notes, plans, and migration notes

## 3. Actual Runtime Entry Points

Use these as the main code entrypoints.

Backend:

- [E:\codework\graduation design\backend\main.py](</E:/codework/graduation design/backend/main.py>)

Backend analysis service:

- [E:\codework\graduation design\backend\services\analysis.py](</E:/codework/graduation design/backend/services/analysis.py>)

Frontend app shell:

- [E:\codework\graduation design\frontend\src\App.tsx](</E:/codework/graduation design/frontend/src/App.tsx>)

Core workflow entry:

- [E:\codework\graduation design\src\core\engine\main.py](</E:/codework/graduation design/src/core/engine/main.py>)

Legacy workflow compatibility entry:

- [E:\codework\graduation design\src\main.py](</E:/codework/graduation design/src/main.py>)

Main compatibility data facade:

- [E:\codework\graduation design\src\tools\api.py](</E:/codework/graduation design/src/tools/api.py>)

## 4. Main Analysis Workflow

The core workflow is defined in:

- [E:\codework\graduation design\src\core\engine\main.py](</E:/codework/graduation design/src/core/engine/main.py>)

High-level flow:

1. `market_data`
2. parallel analysis agents:
   - `technicals`
   - `fundamentals`
   - `sentiment`
   - `valuation`
   - `macro_news`
3. `researcher_bull`
4. `researcher_bear`
5. `debate_room`
6. `risk_manager`
7. `macro_analyst`
8. `portfolio_manager`

The market data collection agent is here:

- [E:\codework\graduation design\src\agents\market_data.py](</E:/codework/graduation design/src/agents/market_data.py>)

This agent is important because it prepares:

- price history
- financial metrics
- financial statements
- market data
- critical-data completeness flags for downstream agents

## 5. Frontend Pages That Matter Most

The current frontend is not just a form page anymore. Important components:

- [E:\codework\graduation design\frontend\src\components\AnalysisStatus.tsx](</E:/codework/graduation design/frontend/src/components/AnalysisStatus.tsx>)
  Process visualization, stages, agent status, human-readable summaries
- [E:\codework\graduation design\frontend\src\components\ReportView.tsx](</E:/codework/graduation design/frontend/src/components/ReportView.tsx>)
  Main report cockpit / answer-friendly presentation
- [E:\codework\graduation design\frontend\src\components\DcfWorkbenchPage.tsx](</E:/codework/graduation design/frontend/src/components/DcfWorkbenchPage.tsx>)
  Independent DCF assumption adjustment page
- [E:\codework\graduation design\frontend\src\services\api.ts](</E:/codework/graduation design/frontend/src/services/api.ts>)
  Frontend API contract
- [E:\codework\graduation design\frontend\src\utils\reportView.ts](</E:/codework/graduation design/frontend/src/utils/reportView.ts>)
  Report data shaping
- [E:\codework\graduation design\frontend\src\utils\dcfView.ts](</E:/codework/graduation design/frontend/src/utils/dcfView.ts>)
  DCF UI-side calculation shaping

## 6. Data Strategy: What Is True Right Now

The current project does not rely on truly stable real-time data.

Practical current strategy:

- history price data: prefer local CSV
- latest price reference: prefer latest available close
- financial metrics: snapshot/cache-first, then remote fetch, then offline fallback
- financial statements: snapshot/cache-first, then Sina/AkShare path, then offline fallback
- market data: snapshot/cache-first, then remote fetch, then offline fallback

Main implementation:

- [E:\codework\graduation design\src\tools\api.py](</E:/codework/graduation design/src/tools/api.py>)

Important reality:

- EastMoney / some AkShare endpoints are network-sensitive and can fail
- real-time data is not treated as a hard requirement anymore
- analysis should still run with latest close / snapshot / offline fallback when possible

## 7. Compatibility Layers You Should Know

This repository is mid-migration from an older flat structure to a more layered structure.

That means some packages are compatibility shells, not the final target structure.

Examples:

- `src.database.*` now re-exports from newer model/data locations
- `src.backtesting.*` now re-exports from `src.data.pricing.*`
- `src.rag.*`, `src.experiments.*`, `src.crawler.*` are compatibility layers
- `src.main` points to `src.core.engine.main`
- `src.tools.api` is still a compatibility facade and currently the safest shared data entrypoint

Read this map for migration intent:

- [E:\codework\graduation design\docs\project-structure-map.md](</E:/codework/graduation design/docs/project-structure-map.md>)

## 8. Files That Are Safe To Treat As Canonical

If an AI needs a short list of files to read first, use this order:

1. [E:\codework\graduation design\AI_PROJECT_GUIDE.md](</E:/codework/graduation design/AI_PROJECT_GUIDE.md>)
2. [E:\codework\graduation design\docs\project-structure-map.md](</E:/codework/graduation design/docs/project-structure-map.md>)
3. [E:\codework\graduation design\backend\main.py](</E:/codework/graduation design/backend/main.py>)
4. [E:\codework\graduation design\backend\services\analysis.py](</E:/codework/graduation design/backend/services/analysis.py>)
5. [E:\codework\graduation design\src\core\engine\main.py](</E:/codework/graduation design/src/core/engine/main.py>)
6. [E:\codework\graduation design\src\agents\market_data.py](</E:/codework/graduation design/src/agents/market_data.py>)
7. [E:\codework\graduation design\src\tools\api.py](</E:/codework/graduation design/src/tools/api.py>)
8. [E:\codework\graduation design\frontend\src\App.tsx](</E:/codework/graduation design/frontend/src/App.tsx>)
9. [E:\codework\graduation design\frontend\src\components\AnalysisStatus.tsx](</E:/codework/graduation design/frontend/src/components/AnalysisStatus.tsx>)
10. [E:\codework\graduation design\frontend\src\components\ReportView.tsx](</E:/codework/graduation design/frontend/src/components/ReportView.tsx>)

## 9. Current Known Technical Risks

These are not hypothetical. They matter during AI-assisted modification.

- `src.tools.api.py` is still large and acts as a compatibility facade, so edits here can have wide blast radius.
- Online market APIs are not fully stable.
- The project recently went through structural cleanup, so some paths are new and some are compatibility shims.
- The repo can be in a dirty state; do not casually revert unrelated changes.
- README is not yet a perfect reflection of the current real runtime structure.

## 10. Things An AI Should Avoid Doing Blindly

- Do not remove compatibility packages unless all callers are updated.
- Do not assume real-time A-share data is required.
- Do not rewrite `src/tools/api.py` from scratch without checking tests and import dependencies.
- Do not delete old paths only because a "cleaner" new path exists; confirm references first.
- Do not revert unrelated frontend or backend changes.

## 11. Recommended Verification Commands

Useful commands after changes:

Backend unit checks:

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_api_local_csv_mode.py tests\unit\test_api_market_fallback.py tests\unit\test_api_snapshot_cache.py tests\unit\test_market_data_local_csv.py tests\unit\test_ablation_config.py tests\unit\test_day8_ablation_runtime.py -q
```

Frontend build:

```powershell
cd frontend
npm run build
```

Import smoke:

```powershell
.venv\Scripts\python.exe -c "import backend.main, backend.routers.analysis, src.agents.market_data, src.tools.api; print('import_ok')"
```

## 12. Short Status Summary

If you are an AI assistant picking up this repo mid-session, the most accurate short summary is:

- the project is functional
- the frontend reporting experience has been significantly upgraded
- the backend data layer now favors local/snapshot/offline fallback over hard real-time dependence
- the repository is still in a structure-migration phase
- compatibility shims are currently part of the intended working state, not accidental clutter
