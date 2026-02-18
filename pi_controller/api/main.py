"""
AC Dashboard API

FastAPI backend for the AC control system dashboard.
Provides endpoints for status, settings, and analytics.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import ac, analytics, weather

app = FastAPI(
    title="AC Dashboard API",
    description="API for AC control system analytics and status",
    version="1.0.0",
)

# CORS for Vue frontend (dev server on port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://drywallpi:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ac.router)
app.include_router(analytics.router)
app.include_router(weather.router)


@app.get("/")
def root():
    """API root - returns basic info."""
    return {
        "name": "AC Dashboard API",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
