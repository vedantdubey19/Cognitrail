import {test,before,after} from 'node:test';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {fixture,pause} from './browser_support.mjs';
let app;
before(async()=>{app=await fixture('cog',fileURLToPath(new URL('..',import.meta.url)));});
after(async()=>{if(app)await app.close();});
test('workspace changes discard delayed plans, evidence, and their approval controls',async()=>{
 const page=await app.context.newPage();const errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(app.origin);await page.locator('#workspace').selectOption(app.metadata.alpha);await page.locator('#history .history-item').filter({hasText:app.metadata.first.question}).waitFor();
 let ready,release;const backendReady=new Promise(resolve=>ready=resolve),gate=new Promise(resolve=>release=resolve);
 await page.route('**/api/runs/'+app.metadata.first.id,async route=>{const response=await route.fetch();ready();await gate;try{await route.fulfill({response});}catch{/* Selection invalidation cancels this request. */}});
 await page.locator('#history .history-item').filter({hasText:app.metadata.first.question}).click();await backendReady;
 await page.locator('#workspace').selectOption(app.metadata.beta);await page.locator('[data-tab="library"]').click();await page.locator('#source-list').filter({hasText:'beta-evidence.txt'}).waitFor();release();await pause(250);
 assert.equal(await page.locator('#workspace').inputValue(),app.metadata.beta);assert.equal(await page.locator('#run-panel').isVisible(),false);
 assert.equal(await page.locator('#approve').isVisible(),false);assert.equal(await page.locator('#run-title').innerText(),'');
 assert.equal(await page.locator('#source-list').innerText().then(text=>text.includes('alpha-evidence.txt')),false);
 assert.deepEqual(errors,[]);await page.close();
});
test('latest run selection wins, and deleting runs/workspaces exposes a usable replacement',async()=>{
 const page=await app.context.newPage();await page.goto(app.origin);await page.locator('#workspace').selectOption(app.metadata.alpha);
 await page.locator('#history .history-item').filter({hasText:app.metadata.first.question}).waitFor();
 let ready,release;const backendReady=new Promise(resolve=>ready=resolve),gate=new Promise(resolve=>release=resolve);
 await page.route('**/api/runs/'+app.metadata.first.id,async route=>{const response=await route.fetch();ready();await gate;await route.fulfill({response});});
 await page.locator('#history .history-item').filter({hasText:app.metadata.first.question}).click();await backendReady;
 await page.locator('#history .history-item').filter({hasText:app.metadata.other.question}).click();await page.locator('#run-title').filter({hasText:app.metadata.other.question}).waitFor();
 release();await pause(200);assert.equal(await page.locator('#run-title').innerText(),app.metadata.other.question);assert.equal(await page.locator('#approve').isEnabled(),true);
 page.once('dialog',dialog=>dialog.accept());await page.getByRole('button',{name:'Delete research run: '+app.metadata.other.question,exact:true}).click();
 await page.locator('#message').filter({hasText:'Research run deleted.'}).waitFor();assert.equal(await page.locator('#run-panel').isVisible(),false);
 assert.equal((await app.api('/api/runs/'+app.metadata.other.id)).status(),404);
 await page.locator('#workspace').selectOption(app.metadata.beta);page.once('dialog',dialog=>dialog.accept());await page.locator('#delete-workspace').click();
 await page.locator('#message').filter({hasText:'Workspace deleted.'}).waitFor();assert.equal(await page.locator('#workspace option').count(),1);
 await page.locator('#workspace-name').fill('Replacement workspace');await page.getByRole('button',{name:'Create',exact:true}).click();
 await page.locator('#message').filter({hasText:'Workspace created.'}).waitFor();assert.equal(await page.locator('#workspace option:checked').innerText(),'Replacement workspace');
 assert.equal(await page.getByRole('button',{name:'Create',exact:true}).isEnabled(),true);await page.close();
});
test('workspace and history deletion controls do not create mobile overflow',async()=>{
 const page=await app.context.newPage();await page.goto(app.origin);await page.locator('#workspace option').nth(1).waitFor({state:'attached'});
 for(const width of [320,375,768,1440]){await page.setViewportSize({width,height:900});if(width<=900&&await page.locator('#workspace-navigation').isHidden())await page.locator('#menu-toggle').click();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
 await page.close();
});
