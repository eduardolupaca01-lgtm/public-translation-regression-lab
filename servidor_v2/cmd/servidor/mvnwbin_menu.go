package main

import (
 "encoding/json"
)

// Only standard visible vocabulary in System.terms is localized. Match
// exact original labels/keys rather than changing arbitrary database data,
// plugin parameters, locale, actor names, or executable resources.
var mvJSONMenuLabels=map[string]string{
 "Level":"Nivel","lvl":"nv.","Lv":"Nv.","HP":"PV","MP":"PM",
 "Fight":"Luchar","Escape":"Huir","Attack":"Atacar","Guard":"Defender",
 "Item":"Objetos","Items":"Objetos","Skill":"Habilidades","Equip":"Equipo",
 "Equipment":"Equipo","Status":"Estado","Formation":"Formación",
 "Save":"Guardar","Game End":"Salir","Options":"Opciones","Weapon":"Arma",
 "Armor":"Armadura","Key Item":"Objeto clave","Optimize":"Optimizar",
 "Clear":"Quitar todo","New Game":"Nueva partida","Continue":"Continuar",
 "To Title":"Al título","Cancel":"Cancelar","Buy":"Comprar","Sell":"Vender",
 "Quest Log":"Misiones","Max HP":"PV máx.","Max MP":"PM máx.",
 "Defense":"Defensa","M.Attack":"At. mágico","M.Defense":"Def. mágica",
 "Agility":"Agilidad","Luck":"Suerte","Hit Rate":"Precisión","Evasion Rate":"Evasión",
}
var mvJSONMenuMessages=map[string]map[string]string{
 "alwaysDash":{"Always Dash":"Correr siempre"},
 "commandRemember":{"Command Remember":"Recordar comando"},
 "bgmVolume":{"BGM Volume":"Vol. música"},
 "bgsVolume":{"BGS Volume":"Vol. ambiente"},
 "meVolume":{"Me Volume":"Vol. melodías","ME Volume":"Vol. melodías"},
 "seVolume":{"SE Volume":"Vol. efectos"},
 "expNext":{"EXP Next":"EXP siguiente","Next EXP":"EXP siguiente"},
 "expTotal":{"EXP Total":"EXP total","Total EXP":"EXP total"},
 "file":{"File":"Archivo"},
 "loadMessage":{"What file do you want to upload?":"¿Qué partida quieres cargar?","Which file would you like to load?":"¿Qué partida quieres cargar?"},
 "saveMessage":{"What file do you want to save to?":"¿Dónde quieres guardar?","Which file would you like to save to?":"¿Dónde quieres guardar?"},
 "possession":{"Possession":"En posesión"},
}
func mvJSONLocalizeSystem(raw []byte)([]byte,int,error){
 doc,e:=mvJSONDecode(raw);if e!=nil{return nil,0,e}
 root,ok:=doc.(map[string]any);if !ok{return nil,0,mvJSONError("JSON_INVALIDO")}
 terms,ok:=root["terms"].(map[string]any)
 if !ok{return raw,0,nil}
 count:=0
 for _,key:=range []string{"basic","commands","params"}{
  if entries,ok:=terms[key].([]any);ok{
   for i,v:=range entries{
    if s,ok:=v.(string);ok{
     if out,ok:=mvJSONMenuLabels[s];ok&&out!=s{
      // Attack in the parameter list is a noun, not a command.
      if key=="params"&&s=="Attack"{out="Ataque"}
      entries[i]=out;count++
     }
    }
   }
  }
 }
 if messages,ok:=terms["messages"].(map[string]any);ok{
  for key,v:=range messages{
   if s,ok:=v.(string);ok{
    if out,ok:=mvJSONMenuMessages[key][s];ok&&out!=s{messages[key]=out;count++}
   }
  }
 }
 if count==0{return raw,0,nil}
 out,e:=json.Marshal(doc)
 if e!=nil||len(out)>16*1024*1024{return nil,0,mvJSONError("RESULTADO_INVALIDO")}
 return out,count,nil
}
