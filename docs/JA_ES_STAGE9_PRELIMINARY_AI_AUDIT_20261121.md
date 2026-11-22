# Etapa 9 — Revisión lingüística preliminar de 40 traducciones (IA, NO validación humana)

Investigación japonés → español latinoamericano, 21-11-2026. Se han comparado los **textos japoneses originales, las traducciones españolas y los intentos rechazados** de los artefactos inmutables de GitHub Actions: etapa 6 run 44931094612 (artifact 14719586946), etapa 7 run 44931094546 (artifact 14719153169) y etapa 8 run 44931420612 (artifact 14720919124).

**Naturaleza de esta revisión:** lectura lingüística preliminar asistida por IA, no revisión bilingüe humana acreditada. Las anotaciones «aparentemente fiel» significan solo que no observé pérdida material con este examen; no equivalen a aprobar la traducción ni certifican su corrección total. Ningún texto de destino, evaluación histórica ni hash del artefacto se modificó. Las 40 fichas para el revisor humano continúan pendientes.

## Etapa 6 — 16/16 por rúbrica original

| Caso | Lectura preliminar del original y la traducción | Acción antes de cierre |
|---|---|---|
| npc_two_condition_variables | Condiciones 0 y 1, puerta y control preservados | Validar humana |
| shop_tomorrow_day_after | Mañana a las 20:00 y pasado mañana a las 09:00 conservados; «al día siguiente» depende del contexto | Revisar legibilidad de fecha relativa |
| search_not_found_roles | Acción y negación preservadas; «Todos están buscando a él» no es español idiomático | Corrección gramatical del modelo necesaria |
| sword_companion_return | Espada, propiedad, bolsa y devolución a ella conservadas | Resolver posible ambigüedad de «suya» |
| sibling_map_chain | Hermano mayor → hermana menor → narrador; mapa conservado | Validar humana |
| permission_changed_today | Japonés concede permiso ayer y prohíbe entrar hoy. «Podrías haber entrado» puede expresar posibilidad contrafactual en lugar de permiso real | **Revisión de significado prioritaria** |
| two_speakers_departure_crlf | \\N[2] no sale todavía, \\N[8] se adelanta; saltos conservados | Validar humana |
| green_appearance_apple | Japonés dice manzana 青い (azul/ao-i) cuya apariencia es verde; traducción literal «azul» puede resultar extraña en contexto | Revisión de terminología/contexto, no modificar sin evidencia |
| two_item_cost_total | 1500 + 900 = 2400 yenes correcto; «Si compras ambos, costará» necesita concordancia/expresión plural | Corrección gramatical |
| before_after_bridge_left | Antes del puente detenerse; después girar izquierda y no derecha | Validar humana |
| files_delete_only_old | Permiso de eliminar antiguos y prohibición absoluta de nuevos conservados, pero «en absoluto» es rígido | Mejorar naturalidad |
| herb_qty_condition | 3 o más → vender una; solo 2 → no vender | Validar humana |
| rebook_saturday_not_thursday | Cambio jueves → sábado mañana, viernes prohibido; «en lugar de el jueves» tiene error de contracción | Corrección «del jueves» |
| train_one_hour_delay | Tren retrasa una hora, reunión pasa de las 10 a las 11 | Revisar estilo, sin cambio semántico obvio |
| luggage_opposite_conditions | Recepción y habitación condicionadas en oposición | Validar humana |
| two_speakers_ask_sara | Japonés usa exhortación colectiva 聞きましょう («preguntémosle»); modelo da «pregúntenselo», orden dirigida a terceros, cambiando la perspectiva del hablante | **Revisión de acto de habla prioritaria** |

## Etapa 7 — 12/12 por rúbrica original, pero no 12 traducciones certificadas

| Caso | Lectura preliminar | Acción |
|---|---|---|
| npc_gate_two_variables | 0 prohíbe entrar; 2 permite abrir puerta este. «No se permite entrada» suena antinatural | Revisar naturalidad y matices |
| sara_tom_unread_letter | Sara da carta a Tom, Tom todavía no la lee | Validar humana |
| not_first_room | Llave tercer cuarto segundo piso, no primer cuarto primer piso | Validar humana |
| shop_discount_only_today | 900 yenes ayer, 700 hoy, mañana no se vende; «no venderá» omite sujeto y objeto explícito, introduciendo ambigüedad | Revisar agencia |
| rpg_two_speakers_sibling | Hermano mayor creído vs hermana menor llegada; «Pensé que vino»/«Quien vino es» necesitan coherencia temporal y naturalidad | Revisar tiempos |
| torch_bridge_order | Apagar antorcha antes del puente; volver a encender después; pronombre «la» correcto | Validar humana |
| nobody_saw_mika_depart | Mika se fue y nadie la vio salir; «nadie» equivale a negación completa | Validar humana |
| younger_sister_joint_trip | Hermana menor termina tarea y narrador va con ella al río | Validar humana |
| six_stones_sell_three | Seis piedras azules, vender tres y conservar resto | Validar humana |
| old_new_docs_reception | Documentos antiguos a recepción, nuevos retener | Validar humana |
| train_speaker_time_correction | Dos hablantes corrigen 17:00 a 18:00, \\N preservado | Validar humana |
| medicine_variable_strict_gt | **Error semántico confirmado:** «\\V[2] es mayor que 1 solo si se usa una medicina» invierte la condición; el japonés manda usar una medicina **solo si \\V[2] > 1**, y no usarla en caso contrario | **Rechazar traducción y repetir inferencia** |

## Etapa 8 — 9/12 por rúbrica original

| Caso | Lectura preliminar | Acción |
|---|---|---|
| letter_younger_brother | Mina entregó carta a hermano menor, que aún no la devuelve | Validar humana |
| rain_stops_choice | Si lluvia cesa esperar afuera, si sigue esperar adentro | Validar humana |
| variable_sword_sell_not_shield | \\V[8] > 2 → vender espada, nunca escudo | Validar humana |
| shop_hours_sunday | Modelo: «La tienda abre a las 10 de la mañana y cierra a las 6 de la tarde. No abre los domingos.» **Traducción semánticamente válida** rechazada por regex singular | Falso rechazo: prueba corregida, no alterar salida histórica |
| taro_hana_mika_witness | Japonés: Tarō vio salir a Hana, Mika no. El modelo produjo «Han» o «Hanako» y «no lo ve»/«no lo está viendo». **Cambio real de nombre, género y perspectiva temporal** | **Repetir inferencia; rechazo correcto** |
| red_blue_bag_stones | 4 piedras rojas, 1 azul, prohibido tomar de bolsa azul | Validar humana |
| younger_brother_bridge_station | Hermano menor al otro lado del puente o buscar detrás de estación | Validar humana |
| npc_first_second_speakers | Primer hablante no irá delante; segundo sí. Códigos y CRLF conservados | Validar humana |
| medicine_three_two_one | 3 medicamentos comprados, 2 sin usar y solo 1 usado | Validar humana |
| variable_boundary_two_cases | «\\V[5] es 4 o menos, no abra esta puerta. Si es 5 o más, se puede abrir.» **Límites inclusivos correctos** y permiso conservado; falso rechazo por regex | Prueba corregida, no modificar salida histórica |
| reserve_wednesday_friday | Reserva miércoles → viernes, no ir jueves | Validar humana |
| two_speakers_aria_sara | Llave en Aria y no Sara; «pregúntenselo» cambia exhortación colectiva japonesa 聞きましょう por imperativo plural | Revisión de acto de habla |

## Alcance y criterios de salida

Un resultado verde del evaluador no es certificado de fidelidad. La etapa 9 debe terminar con revisor japonés/ES-419 independiente, notas y decisión por caso, y corrección verificable de las inversiones y de cambios de persona. La etapa 10 debe superar nuevos recibos de inferencia, regresión en Ubuntu y Windows, reinicio SQLite, revisión humana y un conjunto de prueba realmente externo/ciego antes de permitir revisión de integración. **No se ha aprobado ni fusionado este PR**. Las fichas y los resultados de GitHub se conservan.
