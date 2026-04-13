# AI Handoff

This is the shortest possible handoff note for an AI taking over this repository.

## Read These First

1. [E:\codework\graduation design\AI_PROJECT_GUIDE.md](</E:/codework/graduation design/AI_PROJECT_GUIDE.md>)
2. [E:\codework\graduation design\docs\project-structure-map.md](</E:/codework/graduation design/docs/project-structure-map.md>)
3. [E:\codework\graduation design\src\tools\api.py](</E:/codework/graduation design/src/tools/api.py>)
4. [E:\codework\graduation design\src\core\engine\main.py](</E:/codework/graduation design/src/core/engine/main.py>)
5. [E:\codework\graduation design\src\agents\market_data.py](</E:/codework/graduation design/src/agents/market_data.py>)
6. [E:\codework\graduation design\frontend\src\components\AnalysisStatus.tsx](</E:/codework/graduation design/frontend/src/components/AnalysisStatus.tsx>)
7. [E:\codework\graduation design\frontend\src\components\ReportView.tsx](</E:/codework/graduation design/frontend/src/components/ReportView.tsx>)

## Current Reality

- The repo works, but it is still in a structure-migration phase.
- `src.tools.api` is the safest shared data entrypoint right now.
- Real-time market data is not a hard requirement anymore.
- Snapshot/offline/local fallback is part of the intended behavior.
- Compatibility shims are still expected in several packages.

## Do Not Do This Blindly

- Do not remove compatibility packages just because a new structure exists.
- Do not rewrite `src/tools/api.py` from scratch.
- Do not assume unstable online APIs are the primary source of truth.
- Do not revert unrelated dirty-worktree changes.

## Quick Verification

```powershell
.venv\Scripts\python.exe -m pytest tests\unit\test_api_local_csv_mode.py tests\unit\test_api_market_fallback.py tests\unit\test_api_snapshot_cache.py tests\unit\test_market_data_local_csv.py tests\unit\test_ablation_config.py tests\unit\test_day8_ablation_runtime.py -q
```

```powershell
cd frontend
npm run build
```
