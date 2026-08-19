import asyncio, logging, uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import get_settings
from .db import Base, SessionLocal, engine
from .achievements import achievement_router
from .achievement_catalog import ensure_core_achievement_catalog, bootstrap_existing_contributor_achievements
from .quality_achievements import ensure_quality_achievement_catalog, bootstrap_existing_quality_achievements, install_quality_achievement_processing
from .regional_achievements import ensure_regional_achievement_catalog, regional_router
from .trust_views import trust_router
from . import routes as routes_module
from . import station_catalog as station_catalog_module
from . import community_price_boards as community_price_boards_module
from . import contribution_rewards as contribution_rewards_module
from .community_price_boards import community_router, install_community_price_board_processing
from .contribution_views import router as contribution_views_router
from .image_validation import normalize_image_for_ocr, validate_image_content
from .public_station_snapshot import public_station_router
from .station_admin_tools import install_catalog_dedup, station_admin_router
from .station_catalog import catalog_router
from .station_inference import inference_router, install_station_inference
from .user_price_boards import user_price_board_router
from .user_moderation import moderation_router, install_user_moderation_rewards

# Use the same trusted image validator for upload completion and OCR processing.
routes_module.validate_image_content=validate_image_content

# Preserve the original uploaded object for EXIF/GPS station inference, but pass
# provider-friendly single-frame bytes into OCR. This mainly affects iPhone MPO
# JPEGs; regular JPEG/PNG/WebP bytes are returned unchanged.
_original_validated_media_bytes=routes_module.validated_media_bytes
def _validated_media_bytes_for_ocr(db,media):
    content=_original_validated_media_bytes(db,media)
    try:return normalize_image_for_ocr(content,media.mime_type)
    except ValueError as exc:raise HTTPException(422,"Uploaded content could not be normalized for OCR") from exc
routes_module.validated_media_bytes=_validated_media_bytes_for_ocr

install_station_inference(routes_module)
install_community_price_board_processing(routes_module)
contribution_rewards_module.install_contribution_rewards(community_price_boards_module)
install_user_moderation_rewards(community_price_boards_module)
install_quality_achievement_processing(community_price_boards_module)
install_catalog_dedup(station_catalog_module)
cleanup_expired_limits=routes_module.cleanup_expired_limits
process_ocr_jobs=routes_module.process_ocr_jobs
router=routes_module.router
settings=get_settings(); logging.basicConfig(level=logging.INFO,format='{"level":"%(levelname)s","message":"%(message)s"}')

def create_app(app_settings=settings):
    @asynccontextmanager
    async def lifespan(app):
        if app_settings.app_env in {"development","test"} and app_settings.database_url.startswith("sqlite"):Base.metadata.create_all(engine)
        with SessionLocal() as db:
            cleanup_expired_limits(db)
            ensure_core_achievement_catalog(db)
            ensure_quality_achievement_catalog(db)
            ensure_regional_achievement_catalog(db)
            bootstrap_existing_contributor_achievements(db)
            bootstrap_existing_quality_achievements(db)
            db.commit()
        async def worker():
            while True:
                try:await asyncio.to_thread(process_ocr_jobs)
                except Exception:logging.exception("ocr_worker_iteration_failed")
                await asyncio.sleep(1)
        worker_task=asyncio.create_task(worker())
        try:yield
        finally:
            worker_task.cancel()
            try:await worker_task
            except asyncio.CancelledError:pass
    application=FastAPI(title="Autoroa API",version="0.1.0",docs_url=None if app_settings.app_env=="production" else "/docs",lifespan=lifespan)
    application.add_middleware(CORSMiddleware,allow_origins=app_settings.cors_origins,allow_origin_regex=app_settings.cors_origin_regex,allow_credentials=True,allow_methods=["*"],allow_headers=["Authorization","Content-Type","X-Request-ID"])

    @application.middleware("http")
    async def request_diagnostics(request:Request,call_next):
        request_id=request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        request.state.request_id=request_id
        response=await call_next(request)
        response.headers["x-request-id"]=request_id
        if response.status_code>=400:
            logging.warning(
                "request_rejected request_id=%s method=%s path=%s status=%s origin=%s content_type=%s content_length=%s",
                request_id,request.method,request.url.path,response.status_code,
                request.headers.get("origin","-"),request.headers.get("content-type","-"),request.headers.get("content-length","-"),
            )
        return response

    # Register moderation first so enriched admin-user routes and guarded
    # contribution endpoints take precedence over their legacy equivalents.
    application.include_router(moderation_router)
    application.include_router(achievement_router)
    application.include_router(trust_router)
    application.include_router(regional_router)
    application.include_router(user_price_board_router)
    application.include_router(community_router)
    application.include_router(contribution_views_router)
    application.include_router(public_station_router)
    application.include_router(station_admin_router)
    application.include_router(catalog_router)
    application.include_router(inference_router)
    application.include_router(router)
    @application.get("/health")
    def health():return {"status":"ok"}
    @application.get("/ready")
    def ready():
        with engine.connect() as connection:connection.exec_driver_sql("SELECT 1")
        return {"status":"ready"}
    @application.exception_handler(Exception)
    async def error_handler(request:Request,exc:Exception):
        request_id=getattr(request.state,"request_id","unknown")
        logging.exception("unhandled_error request_id=%s method=%s path=%s",request_id,request.method,request.url.path)
        return JSONResponse(status_code=500,content={"error":{"code":"INTERNAL_ERROR","message":"An unexpected error occurred.","details":None}},headers={"x-request-id":request_id})
    @application.exception_handler(HTTPException)
    async def http_error(request:Request,exc:HTTPException):
        request_id=getattr(request.state,"request_id","unknown")
        logging.warning("http_error request_id=%s method=%s path=%s status=%s detail=%r",request_id,request.method,request.url.path,exc.status_code,exc.detail)
        headers=dict(exc.headers or {});headers["x-request-id"]=request_id
        return JSONResponse(status_code=exc.status_code,content={"error":{"code":"HTTP_ERROR","message":str(exc.detail),"details":None}},headers=headers)
    @application.exception_handler(RequestValidationError)
    async def validation_error(request:Request,exc:RequestValidationError):
        request_id=getattr(request.state,"request_id","unknown")
        logging.warning("validation_error request_id=%s method=%s path=%s errors=%r",request_id,request.method,request.url.path,exc.errors())
        return JSONResponse(status_code=422,content={"error":{"code":"VALIDATION_ERROR","message":"Request validation failed.","details":exc.errors()},},headers={"x-request-id":request_id})
    return application

app=create_app()
