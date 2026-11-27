"use strict";
const assert=require("node:assert/strict");
const {chromium}=require(process.argv[3]);
(async()=>{
 const browser=await chromium.launch({channel:"msedge",headless:true});
 try{
  const page=await browser.newPage();
  await page.goto(process.argv[2]+"/#/");
  await page.waitForFunction(()=>/ventana/i.test(document.querySelector("#dialog")?.textContent||""),null,{timeout:120000});
  assert.equal(await page.locator("#next").textContent(),"Siguiente");
  assert.equal(await page.locator("#save").textContent(),"Guardar");
  assert.equal(await page.locator("#name").inputValue(),"Please keep my name.");
  assert.equal(await page.locator("#identity").textContent(),"Alice");
  await page.locator("#next").click();
  await page.waitForFunction(()=>/puente/i.test(document.querySelector("#dialog")?.textContent||""),null,{timeout:120000});
  await page.locator("#save").click();
  assert.equal(await page.evaluate(()=>localStorage.getItem("fixture-save")),"1");
  await page.keyboard.press("F10");
  assert.equal(await page.locator("#ia-web-panel").isVisible(),true);
  await page.keyboard.press("F10");
  assert.equal(await page.locator("#ia-web-panel").isVisible(),false);
  await page.reload();
  await page.waitForFunction(()=>/puente/i.test(document.querySelector("#dialog")?.textContent||""),null,{timeout:120000});
  assert.equal(await page.evaluate(()=>localStorage.getItem("fixture-save")),"1");
  console.log("IA_WEB_REAL_EDGE_NATIVE_DOM_OPUS_SAVE_RELOAD_PASS");
 }finally{await browser.close();}
})().catch(e=>{console.error("IA_WEB_BROWSER_ACCEPTANCE_FAIL",e.message);process.exitCode=1;});
