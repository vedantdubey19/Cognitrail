from pathlib import Path
import time
import uuid
from sqlalchemy import select
from app.config import Settings
from app.database import Workspace
from app.research import Lab

lab=Lab(Settings())
with lab.store.session() as session:
    row=session.scalar(select(Workspace).where(Workspace.name=='Demo · Synthetic Retrieval Research'))
    if row is None:
        row=Workspace(id=uuid.uuid4().hex,name='Demo · Synthetic Retrieval Research',created=time.time())
        session.add(row)
        session.flush()
    workspace_id=row.id
for file in sorted((Path(__file__).resolve().parents[1]/'data').glob('demo-*.txt')):
    lab.add_source(workspace_id,file.name,file.read_text(),provenance={'origin':'synthetic_demo','not_real_research':True})
print('Synthetic demo workspace ready:',workspace_id)
