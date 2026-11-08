import hashlib
import json
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import TypedDict
from sqlalchemy import select, func, delete
from langgraph.graph import StateGraph, START, END
from app.database import Store, Workspace, Source, Run, as_dict
from app.documents import parse_document
from app.providers import Providers
from app.safety import clean_input, inspect_source, words
from app import fetcher


class State(TypedDict, total=False):
    run_id: str
    source_ids: list[str]
    evidence: list[dict]
    gaps: list[str]
    conflicts: list[dict]
    warnings: list[str]
    round: int
    search_calls: int
    downloads: int
    seen_urls: list[str]
    started: float
    summary: str


class ResearchCancelled(RuntimeError):
    pass


class Lab:
    def __init__(self, settings):
        self.settings = settings
        self.store = Store(settings)
        self.providers = Providers(settings, self.store)
        self.worker = threading.Lock()
        self.upload_lock = threading.RLock()
        self.thread = None
        graph = StateGraph(State)
        graph.add_node('collect',self.collect)
        graph.add_node('extract',self.extract)
        graph.add_node('verify',self.verify)
        graph.add_node('synthesize',self.synthesize)
        graph.add_node('publish',self.publish)
        graph.add_edge(START,'collect')
        graph.add_edge('collect','extract')
        graph.add_edge('extract','verify')
        graph.add_conditional_edges('verify',self.route,{'more':'collect','ready':'synthesize'})
        graph.add_edge('synthesize','publish')
        graph.add_edge('publish',END)
        self.graph = graph.compile()

    def workspace(self, workspace_id):
        with self.store.session() as session:
            row = session.get(Workspace,workspace_id)
            if not row:
                raise LookupError('Workspace unavailable')
            return as_dict(row)

    def delete_workspace(self, workspace_id):
        with self.upload_lock:
            # Serialize deletion with approval and source/plan creation. Never remove a
            # corpus while the research worker can still read or write its snapshots.
            if not self.worker.acquire(blocking=False):
                raise RuntimeError('Wait for active research to finish before deleting a workspace')
            try:
                with self.store.session() as session:
                    if session.get(Workspace, workspace_id) is None:
                        raise LookupError('Workspace unavailable')
                    active = session.scalar(select(Run.id).where(
                        Run.workspace_id == workspace_id, Run.status.in_(['queued', 'running'])))
                    if active:
                        raise RuntimeError('Cancel and wait for the workspace run to stop first')
                    session.execute(delete(Run).where(Run.workspace_id == workspace_id))
                    session.execute(delete(Source).where(Source.workspace_id == workspace_id))
                    session.execute(delete(Workspace).where(Workspace.id == workspace_id))
            finally:
                self.worker.release()

    def add_source(self, workspace_id, title, text, kind='upload', url=None, published=None, provenance=None):
        self.workspace(workspace_id)
        clean_input(text)
        if not text.strip() or len(text)>self.settings.max_source_chars:
            raise ValueError('Invalid source text length')
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self.upload_lock, self.store.session() as session:
            if session.get(Workspace, workspace_id) is None:
                raise LookupError('Workspace unavailable')
            existing = session.scalar(select(Source).where(Source.workspace_id==workspace_id,Source.sha256==digest))
            if existing:
                return as_dict(existing)
            count = session.scalar(select(func.count()).select_from(Source).where(Source.workspace_id==workspace_id))
            used = session.scalar(select(func.coalesce(func.sum(func.length(Source.text)),0)).where(Source.workspace_id==workspace_id))
            if count>=self.settings.max_sources or used+len(text)>self.settings.max_workspace_chars:
                raise ValueError('Workspace source quota exceeded')
            row = Source(id=uuid.uuid4().hex, workspace_id=workspace_id,title=title[:200],text=text,kind=kind,
                         url=url,published=published,created=time.time(),sha256=digest,
                         provenance=provenance or {'origin':'operator_upload'})
            session.add(row)
            session.flush()
            return as_dict(row)

    def create_plan(self, request):
        self.workspace(request.workspace_id)
        clean_input(request.question)
        if request.web_search and not self.settings.brave_api_key:
            raise ValueError('Configure Brave search or use uploaded sources/explicit URLs')
        if len(request.urls)>request.max_web_sources:
            raise ValueError('Explicit URLs exceed approved web-source budget')
        for url in request.urls:
            clean_input(url)
            if not url.startswith('https://') or len(url)>2000:
                raise ValueError('Explicit URLs must be HTTPS and under 2000 characters')
        plan = self.providers.plan(request.question).model_dump()
        plan.update({'urls':request.urls,'web_search':request.web_search,'max_web_sources':request.max_web_sources,
                     'max_search_calls':2,'max_model_calls':2 if self.settings.provider=='gemini' else 0,
                     'provider':self.settings.provider,'model':self.settings.model,
                     'approval_required':True,'workflow_version':'research-v1'})
        with self.upload_lock, self.store.session() as session:
            if session.get(Workspace, request.workspace_id) is None:
                raise LookupError('Workspace unavailable')
            count = session.scalar(select(func.count()).select_from(Run))
            if count>=200:
                raise ValueError('Retained-run quota exceeded; delete old runs')
            row = Run(id=uuid.uuid4().hex,workspace_id=request.workspace_id,question=request.question,
                      status='awaiting_approval',created=time.time(),updated=time.time(),plan=plan,report={},trace=[],cancel=0)
            session.add(row)
            session.flush()
            return as_dict(row)

    def read_run(self, run_id):
        with self.store.session() as session:
            row = session.get(Run,run_id)
            if not row:
                raise LookupError('Run unavailable')
            return as_dict(row)

    def check(self, state):
        run = self.read_run(state['run_id'])
        if run['cancel']:
            raise ResearchCancelled('Cancelled by operator')
        if time.monotonic()-state['started']>180:
            raise TimeoutError('Research wall-clock budget exceeded')
        return run

    def trace(self, run_id, stage, details):
        with self.store.session() as session:
            row = session.get(Run,run_id)
            row.trace = row.trace+[{'stage':stage,'at':datetime.now(timezone.utc).isoformat(),**details}]
            row.updated = time.time()

    def approve(self, run_id, subquestions=None):
        with self.upload_lock:
            if not self.worker.acquire(blocking=False):
                raise ValueError('Another research job is already running')
            try:
                with self.store.session() as session:
                    row = session.get(Run,run_id)
                    if not row or row.status!='awaiting_approval':
                        raise ValueError('Run is not awaiting approval')
                    if subquestions is not None:
                        if any(not q.strip() or len(q)>500 for q in subquestions):
                            raise ValueError('Invalid subquestions')
                        row.plan = {**row.plan,'subquestions':subquestions}
                    row.status='queued'
                    row.updated=time.time()
                self.thread=threading.Thread(target=self.execute,args=(run_id,),daemon=True,name='cognitrail-research')
                self.thread.start()
            except Exception:
                self.worker.release()
                raise
            return {'id':run_id,'status':'queued'}

    def execute(self, run_id):
        try:
            with self.store.session() as session:
                run=session.get(Run,run_id)
                run.status='running'
                sources=session.scalars(select(Source).where(Source.workspace_id==run.workspace_id)).all()
                ids=[source.id for source in sources]
            self.graph.invoke({'run_id':run_id,'source_ids':ids,'evidence':[],'warnings':[],
                               'gaps':[],'round':0,'downloads':0,'search_calls':0,'seen_urls':[],
                               'started':time.monotonic()}, {'recursion_limit':20})
        except Exception as exc:
            status = 'cancelled' if isinstance(exc,ResearchCancelled) else 'failed'
            with self.store.session() as session:
                run=session.get(Run,run_id)
                run.status=status
                run.report={'error':status,'reason_code':type(exc).__name__,
                            'message':'Research did not complete; no validated final report was published.'}
                run.updated=time.time()
            self.trace(run_id,status,{'reason_code':type(exc).__name__})
        finally:
            self.worker.release()

    def collect(self, state):
        run=self.check(state)
        urls=list(run['plan']['urls']) if state['round']==0 else []
        searches=state['search_calls']
        warnings=list(state['warnings'])
        if run['plan']['web_search'] and searches<2:
            query = run['plan']['search_queries'][0] if state['round']==0 else (state['gaps'][0] if state['gaps'] else run['question'])
            try:
                urls += [item['url'] for item in self.providers.search(query)]
            except Exception:
                warnings.append('Search provider failed; available evidence may be incomplete.')
            searches+=1
        ids=list(state['source_ids'])
        seen=list(state['seen_urls'])
        downloads=state['downloads']
        for url in urls:
            self.check(state)
            if url in seen or downloads>=run['plan']['max_web_sources']:
                continue
            seen.append(url)
            downloads+=1
            try:
                fetched=fetcher.fetch(url,self.settings.timeout)
                if fetched['content_type']=='application/pdf':
                    title=fetched['url'].split('/')[-1][:180] or 'source.pdf'
                    text=parse_document(fetched['body'],'source.pdf',self.settings)
                    published=None
                elif fetched['content_type']=='text/plain':
                    title=fetched['url'][:200]
                    text=parse_document(fetched['body'],'source.txt',self.settings)
                    published=None
                else:
                    title,text,published=fetcher.parse_html(fetched['body'],fetched['url'],self.settings.max_source_chars)
                source=self.add_source(run['workspace_id'],title,text,'web',fetched['url'],published,
                    {'origin':'public_https','retrieved_at':datetime.now(timezone.utc).isoformat(),
                     'response_sha256':hashlib.sha256(fetched['body']).hexdigest(),
                     'published_date_status':'publisher_metadata_unverified' if published else 'unknown'})
                if source['id'] not in ids:
                    ids.append(source['id'])
                self.trace(state['run_id'],'source_read',{'source_id':source['id'],'characters':len(text)})
            except Exception as exc:
                warnings.append(f'A web source was unavailable or rejected ({type(exc).__name__}).')
        self.trace(state['run_id'],'collect',{'source_count':len(ids),'search_calls':searches,'download_attempts':downloads})
        return {'source_ids':ids,'warnings':warnings,'round':state['round']+1,'search_calls':searches,
                'downloads':downloads,'seen_urls':seen}

    def extract(self, state):
        run=self.check(state)
        query=words(run['question'])
        candidates=[]
        flagged=0
        with self.store.session() as session:
            sources=[session.get(Source,sid) for sid in state['source_ids']]
            for source in sources:
                if not source:
                    continue
                for match in re.finditer(r'[^.!?\n]+(?:[.!?](?=\s|$)|$)',source.text):
                    quote=match.group().strip()
                    if not 30<=len(quote)<=900:
                        continue
                    if inspect_source(quote):
                        flagged+=1
                        continue
                    overlap=len(query & words(quote))
                    if overlap:
                        start=source.text.find(quote,match.start(),match.end()+1)
                        candidates.append({'source_id':source.id,'quote':quote,'start':start,'end':start+len(quote),
                                           'score':overlap/max(1,len(query)), 'source_sha256':source.sha256})
        selected=sorted(candidates,key=lambda e:(-e['score'],e['source_id'],e['start']))[:12]
        evidence=[{'id':f'E{i:03d}',**item} for i,item in enumerate(selected,1)]
        self.trace(state['run_id'],'extract',{'evidence_count':len(evidence),'flagged_passages':flagged})
        return {'evidence':evidence}

    def verify(self, state):
        run=self.check(state)
        verified=[]
        with self.store.session() as session:
            for item in state['evidence']:
                source=session.get(Source,item['source_id'])
                if source and source.text[item['start']:item['end']]==item['quote'] and source.sha256==item['source_sha256']:
                    verified.append({**item,'verification':'exact_source_span'})
        gaps=[q for q in run['plan']['subquestions'] if not any(len(words(q)&words(e['quote']))>=2 for e in verified)]
        conflicts=[]
        # Candidate disagreements are heuristic signals, never asserted logical contradictions.
        for i,left in enumerate(verified):
            for right in verified[i+1:]:
                if left['source_id']==right['source_id']:
                    continue
                a,b=words(left['quote']),words(right['quote'])
                numbers_a=set(re.findall(r'\b\d+(?:\.\d+)?\b',left['quote']))
                numbers_b=set(re.findall(r'\b\d+(?:\.\d+)?\b',right['quote']))
                if len(a&b)>=4 and ((numbers_a and numbers_b and numbers_a!=numbers_b) or (('not' in a)!=('not' in b))):
                    conflicts.append({'evidence_ids':[left['id'],right['id']],
                                      'status':'candidate_requires_review','reason':'similar passages differ in numbers or negation'})
        self.trace(state['run_id'],'verify',{'verified_spans':len(verified),'gaps':len(gaps),'candidate_conflicts':len(conflicts)})
        return {'evidence':verified,'gaps':gaps,'conflicts':conflicts[:10]}

    def route(self, state):
        run=self.check(state)
        if state['gaps'] and run['plan']['web_search'] and state['search_calls']<2 and state['downloads']<run['plan']['max_web_sources']:
            return 'more'
        return 'ready'

    def synthesize(self, state):
        run=self.check(state)
        summary=self.providers.summarize(run['question'],state['evidence'])
        clean_input(summary)
        self.trace(state['run_id'],'synthesize',{'provider':self.settings.provider,'model':self.settings.model})
        return {'summary':summary}

    def publish(self, state):
        run=self.check(state)
        with self.store.session() as session:
            sources=[as_dict(session.get(Source,sid)) for sid in state['source_ids'] if session.get(Source,sid)]
        report={'question':run['question'],'summary':state['summary'],'evidence':state['evidence'],
                'sources':[{k:v for k,v in s.items() if k!='text'} for s in sources],
                'gaps':state['gaps'],'conflicts':state['conflicts'],'warnings':state['warnings'],
                'provider':self.settings.provider,'model':self.settings.model,'workflow_version':'research-v1',
                'source_snapshot_sha256':hashlib.sha256(json.dumps([(s['id'],s['sha256']) for s in sources],sort_keys=True).encode()).hexdigest(),
                'limitations':['Exact span verification proves provenance, not truth or semantic entailment.',
                               'Coverage and contradiction candidates use heuristics and require human review.',
                               'Source publication dates are metadata, not independently verified.',
                               'Offline mode quotes evidence; it does not perform LLM reasoning.'],
                'usage':{'search_calls':state['search_calls'],'download_attempts':state['downloads'],
                         'elapsed_ms':round((time.monotonic()-state['started'])*1000)}}
        with self.store.session() as session:
            row=session.get(Run,state['run_id'])
            row.report=report
            row.status='completed_with_gaps' if state['gaps'] or state['warnings'] else 'completed'
            row.updated=time.time()
        self.trace(state['run_id'],'publish',{'evidence_count':len(state['evidence'])})
        return {}
