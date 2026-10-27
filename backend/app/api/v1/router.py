from fastapi import APIRouter

from app.api.v1 import (
    applications,
    auth,
    health,
    integrations,
    jobs,
    preferences,
    resumes,
    searches,
    users,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(resumes.router)
api_router.include_router(preferences.router)
api_router.include_router(searches.router)
api_router.include_router(jobs.router)
api_router.include_router(applications.router)
api_router.include_router(integrations.router)
