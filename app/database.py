import time
from contextlib import contextmanager
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Text, Float, Integer, JSON, ForeignKey, select
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


class Workspace(Base):
    __tablename__ = 'workspaces'
    id = Column(String(40), primary_key=True)
    name = Column(String(100), nullable=False)
    created = Column(Float, nullable=False)


class Source(Base):
    __tablename__ = 'sources'
    id = Column(String(40), primary_key=True)
    workspace_id = Column(String(40), ForeignKey('workspaces.id'), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    url = Column(Text)
    kind = Column(String(20), nullable=False)
    text = Column(Text, nullable=False)
    sha256 = Column(String(64), nullable=False)
    created = Column(Float, nullable=False)
    published = Column(String(40))
    provenance = Column(JSON, nullable=False)


class Run(Base):
    __tablename__ = 'runs'
    id = Column(String(40), primary_key=True)
    workspace_id = Column(String(40), ForeignKey('workspaces.id'), nullable=False, index=True)
    question = Column(Text, nullable=False)
    status = Column(String(30), nullable=False)
    created = Column(Float, nullable=False)
    updated = Column(Float, nullable=False)
    plan = Column(JSON, nullable=False)
    report = Column(JSON, nullable=False)
    trace = Column(JSON, nullable=False)
    cancel = Column(Integer, default=0, nullable=False)


class Usage(Base):
    __tablename__ = 'usage'
    key = Column(String(100), primary_key=True)
    count = Column(Integer, nullable=False)


class Store:
    def __init__(self, settings):
        self.settings = settings
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.data_dir.chmod(0o700)
        options = {'check_same_thread': False, 'timeout': 15} if settings.database_url.startswith('sqlite:') else {}
        self.engine = create_engine(settings.database_url, connect_args=options, pool_pre_ping=True)
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.recover()

    @contextmanager
    def session(self):
        with self.factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def recover(self):
        with self.session() as session:
            for run in session.scalars(select(Run).where(Run.status.in_(['queued','running']))):
                run.status = 'interrupted'
                run.updated = time.time()
            expired = session.scalars(select(Run).where(Run.created < time.time() - self.settings.retention_days * 86400)).all()
            for run in expired:
                session.delete(run)

    def reserve(self, kind, limit):
        from sqlalchemy import update
        key = datetime.now(timezone.utc).strftime('%Y-%m-%d') + ':' + kind
        # Called under the application's single worker/tool locks; supports both database dialects.
        with self.session() as session:
            row = session.get(Usage, key)
            if row is None:
                session.add(Usage(key=key, count=1))
            else:
                changed = session.execute(update(Usage).where(Usage.key == key, Usage.count < limit)
                                          .values(count=Usage.count + 1)).rowcount
                if not changed:
                    raise ValueError(f'Daily {kind} budget exhausted')


def as_dict(row):
    return {column.name: getattr(row, column.name) for column in row.__table__.columns}
