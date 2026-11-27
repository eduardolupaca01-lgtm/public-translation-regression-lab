"use strict";
const assert=require("node:assert/strict");
const {performance}=require("node:perf_hooks");
const {setTimeout:delay}=require("node:timers/promises");
const {chromium}=require(process.argv[3]);

// The polling loop lives in Node, not in the inspected page. In particular,
// no waitForFunction/evaluate string, CSP bypass, or unsafe-eval is needed.
async function waitText(page,selector,expected,stage,timeout=120000){
 const deadline=performance.now()+timeout;
 const element=page.locator(selector);
 let last="";
 while(performance.now()<deadline){
  try{last=(await element.textContent({timeout:Math.max(1,Math.min(1000,deadline-performance.now()))}))||"";}
  catch(e){if(e.name!=="TimeoutError")throw e;}
  if(expected.test(last))return last;
  await delay(100);
 }
 throw Error(stage+"_TIMEOUT (last fixture text: "+JSON.stringify(last.slice(0,160))+")");
}
async function verifyCSP(response){
 assert.ok(response&&response.ok(),"IA_WEB_PAGE_HTTP_FAIL");
 const csp=await response.headerValue("content-security-policy");
 assert.ok(csp,"IA_WEB_CSP_HEADER_MISSING");
 const scripts=csp.split(";").map(s=>s.trim()).find(s=>s.startsWith("script-src "));
 assert.equal(scripts,"script-src 'self'","IA_WEB_CSP_WEAKENED");
 assert.ok(!csp.includes("'unsafe-eval'"),"IA_WEB_UNSAFE_EVAL_ENABLED");
}
async function verifySaved(page,expected){
 // The synthetic application's own module reads back localStorage. Its
 // non-translated data attribute is a real readback, not a mocked save.
 assert.equal(await page.locator("#app").getAttribute("data-saved-index"),expected);
}
(async()=>{
 const browser=await chromium.launch({channel:"msedge",headless:true});
 try{
  const context=await browser.newContext({bypassCSP:false});
  const page=await context.newPage();
  const errors=[];
  page.on("pageerror",e=>errors.push(String(e.message).slice(0,240)));
  page.on("response",r=>{
   if(r.url().endsWith("/__ia/translate")&&!r.ok())
    console.error("IA_WEB_TRANSLATE_HTTP_"+r.status());
  });
  await verifyCSP(await page.goto(process.argv[2]+"/#/"));
  await waitText(page,"#dialog",/ventana/i,"IA_WEB_FIRST_EN");
  assert.equal(await page.locator("#next").textContent(),"Siguiente");
  assert.equal(await page.locator("#save").textContent(),"Guardar");
  assert.equal(await page.locator("#name").inputValue(),"Please keep my name.");
  assert.equal(await page.locator("#identity").textContent(),"Alice");
  await verifySaved(page,"unset");
  console.log("IA_WEB_CSP_NATIVE_LOCATOR_EN_PASS");
  await page.locator("#next").click();
  await waitText(page,"#dialog",/puente/i,"IA_WEB_NEXT_JA");
  await page.locator("#save").click();
  await verifySaved(page,"1");
  await page.keyboard.press("F10");
  assert.equal(await page.locator("#ia-web-panel").isVisible(),true);
  await page.keyboard.press("F10");
  assert.equal(await page.locator("#ia-web-panel").isVisible(),false);
  await verifyCSP(await page.reload());
  await waitText(page,"#dialog",/puente/i,"IA_WEB_RELOAD_JA");
  await verifySaved(page,"1");
  assert.deepEqual(errors,[],"IA_WEB_UNCAUGHT_SCRIPT_ERRORS");
  console.log("IA_WEB_EDGE_NATIVE_DOM_SAVE_RELOAD_PASS");
 }finally{await browser.close();}
})().catch(e=>{console.error("IA_WEB_BROWSER_ACCEPTANCE_FAIL",e.message);process.exitCode=1;});
