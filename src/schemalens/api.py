"""Local FastAPI app (design.md section 5, requirement 4).

- GET  /api/bundle                     -> the full bundle
- POST /api/routines/{id}/explain      -> cached or freshly generated explanation
- GET  /, static assets                -> the built UI from the package's web_dist/

Binds to 127.0.0.1 by default (see cli.serve).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from schemalens.bundle import Bundle, build_bundle
from schemalens.explain import AIDisabled, ProviderError, get_or_create, get_provider
from schemalens.store import open_cache

WEB_DIST = Path(__file__).parent / "web_dist"


def create_app(store_path: Path, cache_path: Path | None = None, enable_ai: bool = True) -> FastAPI:
    app = FastAPI(title="SchemaLens", version="0.1.0")
    state: dict = {"bundle": None}

    def bundle() -> Bundle:
        if state["bundle"] is None:
            state["bundle"] = build_bundle(store_path, cache_path)
        return state["bundle"]

    @app.get("/api/bundle")
    def get_bundle() -> JSONResponse:
        return JSONResponse(content=bundle().model_dump(by_alias=True))

    @app.post("/api/routines/{routine_id}/explain")
    def explain(routine_id: str) -> JSONResponse:
        if not enable_ai:
            raise HTTPException(status_code=409, detail="AI is disabled (--no-ai)")
        b = bundle()
        routine = next((r for r in b.routines if r.id == routine_id), None)
        if routine is None:
            raise HTTPException(status_code=404, detail="routine not found")

        relation_meta = _relation_meta(b, set(routine.reads) | set(routine.writes))
        provider = get_provider()
        routine_dict = {"definition": routine.definition}
        try:
            with open_cache(cache_path) as cache:
                body = get_or_create(
                    cache,
                    provider,
                    routine_dict,
                    relation_meta,
                    set(routine.reads),
                    set(routine.writes),
                )
        except AIDisabled as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        # refresh the in-memory bundle so the new explanation shows up
        routine.explanation = body
        return JSONResponse(content=body)

    _mount_ui(app)
    return app


def _relation_meta(bundle: Bundle, relation_ids: set[str]) -> dict[str, list[dict]]:
    by_id = {r.id: r for r in bundle.relations}
    meta: dict[str, list[dict]] = {}
    for rel_id in relation_ids:
        rel = by_id.get(rel_id)
        if rel is not None:
            meta[rel_id] = [{"name": c.name, "data_type": c.data_type} for c in rel.columns]
    return meta


def _mount_ui(app: FastAPI) -> None:
    if not WEB_DIST.exists():

        @app.get("/")
        def no_ui() -> JSONResponse:
            return JSONResponse(
                content={
                    "message": "UI not built. Run `npm run build` in web/, or use the API at /api/bundle.",
                }
            )

        return

    assets = WEB_DIST / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str) -> FileResponse:
        # serve real files when they exist, otherwise fall back to index.html (SPA routing)
        candidate = WEB_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(WEB_DIST / "index.html")
