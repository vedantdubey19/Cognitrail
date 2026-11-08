import hmac
import html
import re
import json
import threading
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy import select, func
from fastapi import FastAPI, Request, UploadFile, File, HTTPException
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exception_handlers import http_exception_handler
from app.config import Settings
from app.database import Workspace, Source, Run, as_dict
from app.documents import parse_document
from app.providers import ProviderError
from app.research import Lab
from app.schemas import NewWorkspace, ResearchRequest, Approval


def escape_markdown(value):
    return re.sub(r'([!\[\]`*_])', r'\\\1', html.escape(value))

def markdown(run):
    report=run['report']
    if 'summary' not in report:
        raise ValueError('Run has no final report')
    parts=[f'# {escape_markdown(run["question"])}',escape_markdown(report['summary']),'## Evidence ledger']
    for evidence in report['evidence']:
        parts.append(f'### [{evidence["id"]}]\n\n> {escape_markdown(evidence["quote"])}\n\nSource: {evidence["source_id"]}; offsets {evidence["start"]}–{evidence["end"]}; verified exact span.')
    parts.append('## Sources')
    for source in report['sources']:
        parts.append(f'- {escape_markdown(source["title"])} — {source["url"] or "Uploaded document"}; SHA-256: {source["sha256"]}')
    parts.append('## Open questions\n'+'\n'.join('- '+escape_markdown(gap) for gap in report['gaps']))
    parts.append('## Limitations\n'+'\n'.join('- '+escape_markdown(item) for item in report['limitations']+report['warnings']))
    return '\n\n'.join(parts)


def create_app(settings=None):
    config=settings or Settings()
    @asynccontextmanager
    async def lifespan(api):
        api.state.lab=Lab(config)
        yield
        if api.state.lab.thread and api.state.lab.thread.is_alive():
            with api.state.lab.store.session() as session:
                for run in session.scalars(select(Run).where(Run.status.in_(['queued','running']))):
                    run.cancel=1
            api.state.lab.thread.join(timeout=config.timeout+2)
        api.state.lab.store.engine.dispose()
    private = config.deployment == 'private'
    api=FastAPI(title='Cognitrail',version='0.1.0',lifespan=lifespan,
                docs_url=None if private else '/docs', redoc_url=None if private else '/redoc',
                openapi_url=None if private else '/openapi.json')
    hosts = ['127.0.0.1', 'localhost', '[::1]']
    hosts += [urlparse(config.public_url).hostname] if private else ['testserver']
    api.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)
    calls=deque()
    rate_lock=threading.Lock()
    upload_slots=threading.BoundedSemaphore(1)

    @api.middleware('http')
    async def boundary(request,call_next):
        loopback = bool(request.client and request.client.host in ('127.0.0.1','::1','testclient'))
        if private:
            # Only the authenticated gateway knows this secret. Proxy headers do not establish trust.
            health_probe = request.url.path == '/health' and request.method in ('GET', 'HEAD') and loopback
            if not health_probe and not hmac.compare_digest(request.headers.get('x-cognitrail-gateway', '').encode(), config.gateway_secret.encode()):
                return Response('Authenticated gateway required', status_code=401)
        elif not loopback:
            return Response('Local operator access only',status_code=403)
        if request.method not in ('GET','HEAD'):
            origin=request.headers.get('origin')
            if (private and origin != config.public_url.rstrip('/')) or (not private and origin and origin not in ('http://127.0.0.1:8100','http://localhost:8100')):
                return Response('Origin denied',status_code=403)
        public=request.url.path in ('/','/health') or request.url.path.startswith('/assets/')
        if not public:
            if not private and config.api_token and not hmac.compare_digest(request.headers.get('authorization',''),f'Bearer {config.api_token}'):
                return Response('Unauthorized',status_code=401)
            with rate_lock:
                now=time.monotonic()
                while calls and calls[0]<now-60:
                    calls.popleft()
                if len(calls)>=60:
                    return Response('Request rate exceeded',status_code=429,headers={'Retry-After':'60'})
                calls.append(now)
        if request.method=='POST':
            maximum=config.max_file_bytes+65536 if request.url.path.endswith('/sources') else 32768
            chunks=[]
            size=0
            async for chunk in request.stream():
                size+=len(chunk)
                if size>maximum:
                    return Response('Payload too large',status_code=413)
                chunks.append(chunk)
            request._body=b''.join(chunks)
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'Referrer-Policy':'no-referrer','X-Frame-Options':'DENY',
            'Content-Security-Policy':"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
        if private:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        return response

    @api.middleware('http')
    async def upload_admission(request,call_next):
        if request.method!='POST' or not request.url.path.endswith('/sources'):
            return await call_next(request)
        if not upload_slots.acquire(blocking=False):
            return Response('Another upload is active',status_code=429)
        try:
            return await call_next(request)
        finally:
            upload_slots.release()

    @api.exception_handler(ValueError)
    async def value_error(request,exc):
        return Response(str(exc),status_code=400)

    @api.exception_handler(LookupError)
    async def lookup_error(request,exc):
        return Response('Resource unavailable',status_code=404)

    @api.exception_handler(ProviderError)
    async def provider_error(request,exc):
        return Response('Provider unavailable or invalid response',status_code=502)

    @api.get('/health')
    def health():
        return {'status':'ok','provider':config.provider,'model':config.model,
                'web_search_configured':bool(config.brave_api_key),'scope':'private-single-operator' if private else 'local-single-operator'}

    @api.get('/api/workspaces')
    def workspaces(request:Request):
        with request.app.state.lab.store.session() as session:
            return [as_dict(w) for w in session.scalars(select(Workspace).order_by(Workspace.created.desc()))]

    @api.post('/api/workspaces',status_code=201)
    def add_workspace(body:NewWorkspace,request:Request):
        lab = request.app.state.lab
        with lab.upload_lock, lab.store.session() as session:
            if session.scalar(select(func.count()).select_from(Workspace))>=20:
                raise ValueError('Workspace quota reached')
            row=Workspace(id=uuid.uuid4().hex,name=body.name,created=time.time())
            session.add(row)
            session.flush()
            return as_dict(row)

    @api.delete('/api/workspaces/{workspace_id}', status_code=204)
    def delete_workspace(workspace_id: str, request: Request):
        try:
            request.app.state.lab.delete_workspace(workspace_id)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from None
        return Response(status_code=204)

    @api.get('/api/workspaces/{workspace_id}/sources')
    def sources(workspace_id:str,request:Request):
        lab=request.app.state.lab
        lab.workspace(workspace_id)
        with lab.store.session() as session:
            return [{k:v for k,v in as_dict(s).items() if k!='text'} for s in session.scalars(select(Source).where(Source.workspace_id==workspace_id))]

    @api.post('/api/workspaces/{workspace_id}/sources',status_code=201)
    def upload(workspace_id:str,request:Request,file:UploadFile=File(...)):
        lab=request.app.state.lab
        lab.workspace(workspace_id)
        data=file.file.read(config.max_file_bytes+1)
        text=parse_document(data,file.filename,config)
        import hashlib
        result=lab.add_source(workspace_id,file.filename,text,provenance={'origin':'operator_upload',
                              'file_sha256':hashlib.sha256(data).hexdigest(),'publication_date_status':'unknown'})
        return {k:v for k,v in result.items() if k!='text'}

    @api.get('/api/sources/{source_id}')
    def source(source_id:str,request:Request):
        with request.app.state.lab.store.session() as session:
            row=session.get(Source,source_id)
            if not row:
                raise LookupError()
            return as_dict(row)

    @api.delete('/api/sources/{source_id}',status_code=204)
    def delete_source(source_id:str,request:Request):
        lab = request.app.state.lab
        with lab.upload_lock, lab.store.session() as session:
            row=session.get(Source,source_id)
            if not row:
                raise LookupError()
            for run in session.scalars(select(Run).where(Run.workspace_id==row.workspace_id)):
                if run.status in ('queued','running'):
                    raise HTTPException(409,'Cannot delete sources during an active workspace run')
                # Remove report snapshots too: source deletion must not leave quoted copies behind.
                if any(s.get('id')==source_id for s in run.report.get('sources',[])):
                    session.delete(run)
            session.delete(row)
        return Response(status_code=204)

    @api.post('/api/runs',status_code=201)
    def create_run(body:ResearchRequest,request:Request):
        return request.app.state.lab.create_plan(body)

    @api.get('/api/runs')
    def runs(workspace_id:str,request:Request):
        request.app.state.lab.workspace(workspace_id)
        with request.app.state.lab.store.session() as session:
            return [{k:v for k,v in as_dict(run).items() if k not in ('report','trace')}
                    for run in session.scalars(select(Run).where(Run.workspace_id==workspace_id).order_by(Run.created.desc()))]

    @api.get('/api/runs/{run_id}')
    def run(run_id:str,request:Request):
        return request.app.state.lab.read_run(run_id)

    @api.post('/api/runs/{run_id}/approve',status_code=202)
    def approve(run_id:str,body:Approval,request:Request):
        return request.app.state.lab.approve(run_id,body.subquestions)

    @api.post('/api/runs/{run_id}/cancel')
    def cancel(run_id:str,request:Request):
        with request.app.state.lab.store.session() as session:
            row=session.get(Run,run_id)
            if not row:
                raise LookupError()
            if row.status in ('completed','completed_with_gaps','failed','cancelled','interrupted'):
                raise ValueError('Run is already terminal')
            row.cancel=1
            if row.status=='awaiting_approval':
                row.status='cancelled'
        return {'status':'cancellation_requested'}

    @api.delete('/api/runs/{run_id}',status_code=204)
    def delete_run(run_id:str,request:Request):
        lab = request.app.state.lab
        with lab.upload_lock, lab.store.session() as session:
            row=session.get(Run,run_id)
            if not row:
                raise LookupError()
            if row.status in ('queued','running'):
                raise HTTPException(409,'Cancel and wait for the run to stop first')
            session.delete(row)
        return Response(status_code=204)

    @api.get('/api/runs/{run_id}/export')
    def export(run_id:str,request:Request,format:str='json'):
        row=request.app.state.lab.read_run(run_id)
        if format=='json':
            value,kind=json.dumps(row,indent=2),'application/json'
        elif format=='markdown':
            value,kind=markdown(row),'text/markdown'
        else:
            raise ValueError('Choose json or markdown')
        return Response(value,media_type=kind,headers={'Content-Disposition':f'attachment; filename="cognitrail-{run_id}.{ "json" if format=="json" else "md"}"'})

    web=Path(__file__).resolve().parent/'web'
    @api.exception_handler(StarletteHTTPException)
    async def browser_error(request, exc):
        if exc.status_code == 404 and "text/html" in request.headers.get("accept", "") and not request.url.path.startswith(("/api/", "/assets/")):
            return FileResponse(web / "404.html", status_code=404)
        return await http_exception_handler(request, exc)

    api.mount('/assets',StaticFiles(directory=web),name='assets')

    @api.get('/')
    def home():
        return FileResponse(web/'index.html')
    return api


app=create_app()
