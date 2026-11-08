import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawn,execFileSync} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import net from 'node:net';
import https from 'node:https';
export const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export async function fixture(profile,root){
 const directory=await mkdtemp(join(tmpdir(),`${profile}-browser-`));
 const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const port=server.address().port;await new Promise(resolve=>server.close(resolve));
 const origin=`https://127.0.0.1:${port}`,password=randomBytes(24).toString('hex'),secret=randomBytes(32).toString('hex');
 execFileSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-keyout',join(directory,'key.pem'),'-out',join(directory,'cert.pem'),'-subj','/CN=127.0.0.1','-days','1'],{stdio:'ignore'});
 const code=`import json,os,time,uuid
from pathlib import Path
import uvicorn
from app.config import Settings
from app.main import create_app
q=json.loads(os.environ['QA_FIXTURE_JSON']);directory=Path(q['directory']);data=directory/'data'
if q['profile']=='rag':
 from app.service import Laboratory
 from app.auth import Auth
 config=Settings(_env_file=None,data_dir=data,deployment='hosted',public_url=q['origin'],provider='extractive',retrieval='lexical',actor_id='qa_alpha')
 lab=Laboratory(config);auth=Auth(lab.store,config)
 for user in ['qa_alpha','qa_beta']:auth.create_user(user,q['password'])
 cid=lab.create_collection('Alpha private evidence')['id'];lab.ingest(b'The alpha project codename is Violet Orchard.','alpha-private.txt',cid)
 metadata={'alpha_collection':cid,'database':str(lab.store.path)}
else:
 from app.research import Lab
 from app.database import Workspace
 from app.schemas import ResearchRequest
 config=Settings(_env_file=None,data_dir=data,database_url=f'sqlite:///{data}/research.db',deployment='private',public_url=q['origin'],gateway_secret=q['secret'],provider='extractive',model='extractive-v1')
 lab=Lab(config);ids=[]
 for label in ['Alpha','Beta']:
  wid=uuid.uuid4().hex
  with lab.store.session() as session:session.add(Workspace(id=wid,name='Workspace '+label,created=time.time()))
  lab.add_source(wid,label.lower()+'-evidence.txt',label+' evidence describes hybrid retrieval using lexical and semantic search.')
  ids.append(wid)
 first=lab.create_plan(ResearchRequest(workspace_id=ids[0],question='What belongs to Alpha workspace?',max_web_sources=0))
 other=lab.create_plan(ResearchRequest(workspace_id=ids[0],question='How does Alpha retrieve evidence?',max_web_sources=0))
 metadata={'alpha':ids[0],'beta':ids[1],'first':first,'other':other}
 lab.store.engine.dispose()
(directory/'metadata.json').write_text(json.dumps(metadata))
uvicorn.run(create_app(config),host='127.0.0.1',port=q['port'],ssl_keyfile=str(directory/'key.pem'),ssl_certfile=str(directory/'cert.pem'),proxy_headers=False,access_log=False)
`;
 const processHandle=spawn(resolve(root,'.venv/bin/python'),['-c',code],{cwd:root,env:{...process.env,QA_FIXTURE_JSON:JSON.stringify({profile,directory,port,origin,password,secret})},stdio:['ignore','pipe','pipe']});
 let logs='';processHandle.stdout.on('data',data=>logs=(logs+data).slice(-6000));processHandle.stderr.on('data',data=>logs=(logs+data).slice(-6000));
 let browser;
 async function close(){
  if(browser)await browser.close();
  if(processHandle.exitCode===null){processHandle.kill('SIGTERM');await Promise.race([new Promise(resolve=>processHandle.once('exit',resolve)),pause(5000)]);if(processHandle.exitCode===null)processHandle.kill('SIGKILL');}
  await rm(directory,{recursive:true,force:true});
 }
 try{
  let ready=false;
  for(let i=0;i<150;i++){
   if(processHandle.exitCode!==null)throw Error(logs);
   ready=await new Promise(resolve=>{const request=https.get(origin+'/health',{rejectUnauthorized:false},response=>{response.resume();resolve(response.statusCode===200);});request.on('error',()=>resolve(false));request.setTimeout(500,()=>request.destroy());});
   if(ready)break;await pause(200);
  }
  if(!ready)throw Error('Fixture did not start: '+logs);
  const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
  browser=await chromium.launch({headless:true,channel:process.env.PLAYWRIGHT_CHANNEL||undefined});
  const gatewayHeaders=profile==='cog'?{'X-Cognitrail-Gateway':secret}:{};
  const context=await browser.newContext({ignoreHTTPSErrors:true,viewport:{width:1280,height:900},extraHTTPHeaders:gatewayHeaders});
  const metadata=JSON.parse(await readFile(join(directory,'metadata.json'),'utf8'));
  async function api(path,method='GET',data){
   const cookies=await context.cookies();const csrf=cookies.find(cookie=>cookie.name==='ragvanta_csrf')?.value||'';
   return context.request.fetch(origin+path,{method,data,headers:{...gatewayHeaders,Origin:origin,'X-CSRF-Token':csrf}});
  }
  function expire(user){execFileSync(resolve(root,'.venv/bin/python'),['-c',"import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);c.execute('UPDATE sessions SET expires=0 WHERE user_id=?',(sys.argv[2],));c.commit()",metadata.database,user]);}
  return {origin,password,context,metadata,api,expire,close};
 }catch(error){await close();throw error;}
}
