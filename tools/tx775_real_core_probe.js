"use strict";
// Executes exported TX710CleanCore.valid from exact original V95 JS in runner.
// No private plugin code or model data is uploaded or logged.
const fs=require("fs"),vm=require("vm");
const file=process.argv[2],stage=process.argv[3];
if(!file||!["original","patched"].includes(stage))process.exit(2);
const source=fs.readFileSync(file,"utf8");
const cut=source.indexOf('\n(function () {\n    "use strict";');
if(cut<=0)throw new Error("TX775_UNKNOWN_OWNER_CORE_BOUNDARY");
const host={module:{exports:{}},exports:{},Map,Date,Number,Object,Array,String,JSON};
vm.runInNewContext(source.slice(0,cut),host,{filename:"owner native V95 core"});
const core=host.module.exports;
if(!core||typeof core.valid!=="function")throw new Error("TX775_NATIVE_VALID_EXPORT_MISSING");
const original="\\N<隼人 \\N[2]>おはようございます。";
const accepted="\\N<隼人 \\N[2]>Buenos días.";
const rejects=[
  "\\N<隼人 \\N[2]>おはようございます。",
  "\\N<夏実 \\N[2]>Buenos días.",
  "Buenos días.",
  "\\N<隼人 \\N[2]>",
  "\\N<隼人 \\N[2]>Hola、まだです。",
];
const actual=Boolean(core.valid(original,accepted));
if(stage==="original"&&actual)throw new Error("TX775_BASELINE_UNKNOWN_ACTOR_GUARD");
if(stage==="patched"&&!actual)throw new Error("TX775_PATCHED_ACTOR_GUARD_NOT_RECOVERED");
for(let i=0;i<rejects.length;i++){
  if(core.valid(original,rejects[i]))
    throw new Error("TX775_BROKEN_ACTOR_GUARD_REJECT_CASE_"+i);
}
console.log("TX775_ACTUAL_V95_NATIVE_CORE_"+stage.toUpperCase()+"_GUARDS_PASS");
