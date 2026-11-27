"use strict";
// Acceptance contract for the single authored R42 English notice.
// Do not log the translated sentence or infer success from the mere
// presence of a door. Require an affirmative close command, the wooden
// door, exact native delimiters, and unchanged original event text.
const assert=require("node:assert/strict");
const BODY="Please close the wooden door.";
const RAW='※"'+BODY+'" 【M】';
const closeCommand=/^(?:por favor,?\s+)?(?:cierra|cierre|cierren|cerrad|cerrar)(?:,?\s+por favor,?)?\s+la\s+puerta\s+de\s+madera(?:,?\s+por favor)?[.!]?$/i;
function inspect(painted,original){
    const value=typeof painted==="string"?painted:"";
    const match=/^※"([^"\r\n]+)" 【M】$/.exec(value);
    const body=match?match[1].normalize("NFC").trim():"";
    const unchanged=original===RAW;
    const changed=!!match&&body!==BODY;
    const semantic=changed&&closeCommand.test(body);
    return {envelope:!!match,changed,unchanged,semantic,
        legacyClose:/cerr/i.test(body),ok:!!match&&changed&&unchanged&&semantic};
}
function selfTest(){
    for(const body of ["Por favor, cierre la puerta de madera.","Cierra la puerta de madera.",
        "Cerrad la puerta de madera, por favor.","Cierra, por favor, la puerta de madera.",
        "Por favor cerrar la puerta de madera."]){
        assert.ok(inspect('※"'+body+'" 【M】',RAW).ok,"accept valid Spanish imperatives");
    }
    for(const body of [BODY,"No cierre la puerta de madera.","Abre la puerta de madera.",
        "Cierra la puerta de metal.","Cierra la puerta.","Cierra la puerta de madera y abre la ventana."]){
        assert.equal(inspect('※"'+body+'" 【M】',RAW).ok,false,"reject changed meaning or English");
    }
    for(const value of ['"Cierra la puerta de madera." 【M】','※"Cierra la puerta de madera." 【N】',
        '※Cierra la puerta de madera. 【M】','※"Cierra la puerta de madera." 【M】 extra']){
        assert.equal(inspect(value,RAW).ok,false,"reject damaged format");
    }
    assert.equal(inspect('※"Cierra la puerta de madera." 【M】',"changed event").ok,false);
    assert.equal(inspect('※"Cierra la puerta de madera." 【M】',RAW).legacyClose,false,
        "old substring check rejects a valid Spanish imperative");
}
if(require.main===module){selfTest();console.log("IA_R42_NOTICE_SEMANTIC_CONTRACT_PASS");}
module.exports={BODY,RAW,inspect,selfTest};
