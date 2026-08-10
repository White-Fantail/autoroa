import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import get_settings
from .db import Base, SessionLocal, engine
from .routes import cleanup_expired_limits, router

settings=get_settings(); logging.basicConfig(level=logging.INFO,format='{"level":"%(levelname)s","message":"%(message)s"}')

def create_app(app_settings=settings):
    @asynccontextmanager
    async def lifespan(app):
        if app_settings.app_env in {"development","test"} and app_settings.database_url.startswith("sqlite"):Base.metadata.create_all(engine)
        with SessionLocal() as db:cleanup_expired_limits(db)
        yield
    application=FastAPI(title="Carfolio API",version="0.1.0",docs_url=None if app_settings.app_env=="production" else "/docs",lifespan=lifespan)
    application.add_middleware(CORSMiddleware,allow_origins=app_settings.cors_origins,allow_origin_regex=app_settings.cors_origin_regex,allow_credentials=True,allow_methods=["*"],allow_headers=["Authorization","Content-Type"])
    application.include_router(router)
    @application.get("/health")
    def health():return {"status":"ok"}
    @application.get("/ready")
    def ready():
        with engine.connect() as connection:connection.exec_driver_sql("SELECT 1")
        return {"status":"ready"}
    @application.exception_handler(Exception)
    async def error_handler(request:Request,exc:Exception):
        logging.exception("unhandled_error");return JSONResponse(status_code=500,content={"error":{"code":"INTERNAL_ERROR","message":"An unexpected error occurred.","details":None}})
    @application.exception_handler(HTTPException)
    async def http_error(request:Request,exc:HTTPException):return JSONResponse(status_code=exc.status_code,content={"error":{"code":"HTTP_ERROR","message":str(exc.detail),"details":None}},headers=exc.headers)
    @application.exception_handler(RequestValidationError)
    async def validation_error(request:Request,exc:RequestValidationError):return JSONResponse(status_code=422,content={"error":{"code":"VALIDATION_ERROR","message":"Request validation failed.","details":exc.errors()}})
    return application

app=create_app()
