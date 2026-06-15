from fastapi import APIRouter
from models.project import ProjectName, NSFIPillar
from services import nsfi_service

router = APIRouter(prefix="/nsfi", tags=["nsfi"])


@router.get("/dashboard")
async def nsfi_dashboard(project: ProjectName | None = None):
    """NSFI 2025-30 Panch-Jyoti framework overview and project alignment."""
    return await nsfi_service.get_nsfi_dashboard(project)


@router.get("/pillars")
async def list_pillars():
    """All five Panch-Jyoti pillars with RBI targets and metrics."""
    return nsfi_service.PANCH_JYOTI


@router.get("/report/{project_name}")
async def nsfi_report(project_name: ProjectName):
    """Full NSFI 2025-30 compliance report for a project."""
    return await nsfi_service.generate_nsfi_report(project_name)


@router.get("/alignment")
async def pillar_alignment(pillars: list[NSFIPillar] = []):
    """Return RBI targets and metrics for the specified NSFI pillars."""
    return nsfi_service.get_pillar_alignment(pillars)
