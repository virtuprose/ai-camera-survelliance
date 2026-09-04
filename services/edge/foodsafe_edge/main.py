from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from pydantic import BaseModel

from .pipeline import CameraSwitchError, EdgePipeline
from .settings import Settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
settings = Settings()
pipeline = EdgePipeline(settings)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    pipeline.start()
    yield
    pipeline.stop()


app = FastAPI(title="ORVIA AI Surveillance Edge", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


def authorize(authorization: str | None = Header(default=None)) -> None:
    if not settings.edge_device_token:
        return
    if authorization != f"Bearer {settings.edge_device_token}":
        raise HTTPException(status_code=401, detail="Invalid edge device token")


class ReviewRequest(BaseModel):
    status: str


class IncidentUpdateRequest(BaseModel):
    status: str | None = None
    priority: str | None = None
    owner: str | None = None
    rootCause: str | None = None
    correctiveAction: str | None = None
    resolutionNote: str | None = None
    resolutionType: str | None = None
    actor: str = "QA Supervisor (Demo View)"


class IncidentActivityRequest(BaseModel):
    detail: str
    actor: str = "QA Supervisor (Demo View)"


class DemoResetRequest(BaseModel):
    confirmation: str


class CameraSwitchRequest(BaseModel):
    cameraId: str


@app.get("/health")
def health() -> dict[str, object]:
    state = pipeline.state()
    return {"ok": True, "camera": state["health"]["camera"], "lastFrameAt": state["health"]["lastFrameAt"]}


@app.get("/api/state", dependencies=[Depends(authorize)])
def state() -> dict[str, object]:
    return pipeline.state()


@app.get("/api/cameras", dependencies=[Depends(authorize)])
def cameras() -> dict[str, object]:
    return pipeline.cameras()


@app.patch("/api/cameras/active", dependencies=[Depends(authorize)])
def switch_camera(request: CameraSwitchRequest) -> dict[str, object]:
    try:
        return pipeline.switch_camera(request.cameraId)
    except CameraSwitchError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/events", dependencies=[Depends(authorize)])
def events() -> dict[str, object]:
    return {"items": pipeline.store.list_events()}


@app.post("/api/detection/reset", dependencies=[Depends(authorize)])
def reset_detection() -> dict[str, object]:
    return {"ok": True, "detection": pipeline.reset_detection()}


@app.get("/api/temperature", dependencies=[Depends(authorize)])
def temperature_readings() -> dict[str, object]:
    return {"items": pipeline.store.temperature_readings()}


@app.get("/api/inventory/transactions", dependencies=[Depends(authorize)])
def inventory_transactions() -> dict[str, object]:
    return {"items": pipeline.store.inventory_transactions()}


@app.get("/api/enterprise/context", dependencies=[Depends(authorize)])
def enterprise_context() -> dict[str, object]:
    return pipeline.enterprise.context()


@app.get("/api/enterprise/overview", dependencies=[Depends(authorize)])
def enterprise_overview() -> dict[str, object]:
    return pipeline.enterprise.overview()


@app.get("/api/enterprise/incidents", dependencies=[Depends(authorize)])
def enterprise_incidents(status: str | None = None, limit: int = 50) -> dict[str, object]:
    return {"items": pipeline.enterprise.list_incidents(status=status, limit=limit)}


@app.get("/api/enterprise/incidents/{incident_id}", dependencies=[Depends(authorize)])
def enterprise_incident(incident_id: str) -> dict[str, object]:
    try:
        return pipeline.enterprise.get_incident(incident_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Incident not found") from error


@app.patch("/api/enterprise/incidents/{incident_id}", dependencies=[Depends(authorize)])
def update_enterprise_incident(incident_id: str, request: IncidentUpdateRequest) -> dict[str, object]:
    try:
        changes = request.model_dump(exclude={"actor"}, exclude_none=True)
        return pipeline.enterprise.update_incident(incident_id, changes, request.actor)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Incident not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/api/enterprise/incidents/{incident_id}/activity", dependencies=[Depends(authorize)])
def add_enterprise_activity(incident_id: str, request: IncidentActivityRequest) -> dict[str, object]:
    try:
        return pipeline.enterprise.add_activity(incident_id, request.actor, request.detail)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Incident not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/enterprise/sops", dependencies=[Depends(authorize)])
def enterprise_sops() -> dict[str, object]:
    return {"items": pipeline.enterprise.sops()}


@app.get("/api/enterprise/process-runs", dependencies=[Depends(authorize)])
def enterprise_process_runs(limit: int = 50) -> dict[str, object]:
    return {"items": pipeline.enterprise.process_runs(limit=limit)}


@app.get("/api/enterprise/reports/summary", dependencies=[Depends(authorize)])
def enterprise_report_summary() -> dict[str, object]:
    return pipeline.enterprise.report_summary()


@app.get("/api/enterprise/reports/audit-pack", dependencies=[Depends(authorize)])
def enterprise_audit_pack() -> Response:
    return Response(
        content=pipeline.enterprise.audit_pack(),
        media_type="application/pdf",
        headers={"content-disposition": "attachment; filename=orvia-enterprise-audit-pack.pdf"},
    )


@app.get("/api/enterprise/integrations/oracle", dependencies=[Depends(authorize)])
def enterprise_oracle_readiness() -> dict[str, object]:
    return pipeline.enterprise.oracle_readiness()


@app.get("/api/enterprise/audit-log", dependencies=[Depends(authorize)])
def enterprise_audit_log(limit: int = 100) -> dict[str, object]:
    return {"items": pipeline.enterprise.audit_log(limit=limit)}


@app.patch("/api/events/{event_id}", dependencies=[Depends(authorize)])
def review_event(event_id: str, request: ReviewRequest) -> dict[str, object]:
    try:
        return pipeline.store.update_status(event_id, request.status)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Event not found") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/api/events.csv", dependencies=[Depends(authorize)])
def export_events() -> PlainTextResponse:
    return PlainTextResponse(
        pipeline.store.csv_export(),
        media_type="text/csv",
        headers={"content-disposition": "attachment; filename=food-safety-events.csv"},
    )


@app.get("/api/preview.mjpeg", dependencies=[Depends(authorize)])
def preview() -> StreamingResponse:
    return StreamingResponse(pipeline.frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/evidence/{filename}", dependencies=[Depends(authorize)])
def evidence(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    path = settings.evidence_dir / safe_name
    if path.parent != settings.evidence_dir or not path.is_file():
        raise HTTPException(status_code=404, detail="Evidence not found")
    return FileResponse(path)


@app.post("/api/demo/reset", dependencies=[Depends(authorize)])
def reset_demo(request: DemoResetRequest) -> dict[str, object]:
    if request.confirmation != "RESET SIMULATED DATA":
        raise HTTPException(status_code=422, detail="Type RESET SIMULATED DATA to confirm")
    return {"ok": True, "removed": pipeline.reset_demo_state()}


@app.post("/api/demo/{action}", dependencies=[Depends(authorize)])
async def demo_action(action: str, request: Request) -> dict[str, bool]:
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    try:
        pipeline.demo_action(action, payload)
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("foodsafe_edge.main:app", host=settings.edge_host, port=settings.edge_port, reload=False)
