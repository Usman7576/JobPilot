from fastapi import APIRouter

from app.api.v1 import (
    applications,
    auth,
    dashboard,
    health,
    integrations,
    jobs,
    notifications,
    preferences,
    resumes,
    searches,
    usage,
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
api_router.include_router(notifications.router)
api_router.include_router(dashboard.router)
api_router.include_router(usage.router)
