# encoding: UTF-8
# Authored fixtures: no original game content or DLLs.
class Rect
  attr_reader :x,:y,:width,:height
  def initialize(x,y,w,h);@x=x;@y=y;@width=w;@height=h;end
end
class Color
  attr_accessor :red,:green,:blue,:alpha
  def initialize(r,g,b,a=255);@red=r;@green=g;@blue=b;@alpha=a;end
end
class Font
  attr_accessor :name,:size,:bold,:italic,:color
  def initialize;@name='Arial';@size=22;@bold=@italic=false;@color=Color.new(255,255,255);end
end
class Bitmap
  attr_reader :width,:height,:font,:draws,:fills
  def initialize(w,h);@width=w;@height=h;@font=Font.new;@draws=[];@fills=[];@disposed=false;end
  def disposed?;@disposed;end
  def dispose;@disposed=true;end
  def clear;@draws.clear;end
  def fill_rect(*a);@fills.push(a);end
  def blt(*a);end
  def stretch_blt(*a);end
  def set_pixel(*a);end
  def hue_change(*a);end
  def text_size(s);Rect.new(0,0,s.size*8,24);end
  def draw_text(*a)
    i=a[0].is_a?(Rect) ? 1 : 4
    @draws.push([a[i],@font.size,@font.color.red])
  end
end
class Window_Base
  attr_accessor :contents
  def initialize;self.contents=Bitmap.new(400,128);end
  def disposed?;false;end
  def draw_actor_name(a);contents.draw_text(0,0,140,32,a.name);end
end
class Window_Message < Window_Base
  attr_reader :painted,:paints
  def initialize
    super
    @contents_showing=false;@fade_in=@fade_out=false;@paints=0
  end
  def update
    if !@contents_showing && $game_temp.message_text
      refresh;@contents_showing=true
    end
  end
  def refresh
    @painted=$game_temp.message_text.dup
    @paints+=1
    $game_temp.message_text.replace('')
  end
end
class Window_NameInput < Window_Base;end
class Sprite
  attr_accessor :bitmap,:z,:x,:y
  def disposed?;false;end
end
module Graphics
  def self.update;end
end
class GameTemp
  attr_accessor :message_text,:choice_start,:choice_max,:choice_proc,:num_input_variable_id
  def initialize;@num_input_variable_id=0;@choice_max=0;end
end
Person=Struct.new(:name)
$data_actors=[nil,Person.new('Aster')]
$data_enemies=[nil,Person.new('Dark Knight')]
$data_classes=[nil,Person.new('Sentinel')]
require File.expand_path('../rpgxp/IATraductoraXP.rb',File.dirname(__FILE__))
def check(value,label);raise label unless value;end
class MockXP
  attr_accessor :ready
  attr_reader :requests
  def initialize;@ready=false;@requests=[];end
  def poll(lang,text)
    @requests.push([lang,text]) unless @requests.include?([lang,text])
    return nil unless @ready
    {'Listen to me, oh mighty king...'=>'Escúchame, poderoso rey...',
     'Praying Villager:'=>'Aldeano rezando:',
     'Please turn the wheel.'=>'Gira la rueda.',
     'Sentinel'=>'Centinela',
     'This is a secret passage.'=>'Este es un pasadizo secreto.',
     'Open the gate.'=>'Abre la puerta.',
     'Please lower the bridge.'=>'Baja el puente.'}[text]
  end
end
transport=MockXP.new
IATraductoraXP.attach(transport)
check(IATraductoraXP.source('Listen, oh mighty king...')=='en','broader prose')
check(IATraductoraXP.source('Praying Villager:')=='en','generic speaker role')
check(IATraductoraXP.source('Aster:')==nil,'speaker identity')
check(IATraductoraXP.source('Dark Knight',:term)==nil,'enemy identity')
check(IATraductoraXP.source('La puerta está cerrada.')==nil,'Spanish retranslation')
check(IATraductoraXP.source('Don’t leave me here…')=='en','typographic punctuation')
$game_temp=GameTemp.new
raw="Praying Villager:\nListen to me, oh mighty king...\n"
$game_temp.message_text=raw.dup
w=Window_Message.new
w.update
check(w.paints==0,'first paint gate')
transport.ready=true
w.update
check(w.painted=="Aldeano rezando:\nEscúchame, poderoso rey...\n",'untranslated role/prose')
check($game_temp.message_text==raw,'event data changed')
p=IATraductoraXP.plan("Please turn the wheel.\nSomething unavailable.\nOpen the gate.\nA choice not available.\n")
IATraductoraXP.advance(p)
p[:until]=Time.now.to_f-1
check(IATraductoraXP.advance(p),'bounded fallback')
shown=IATraductoraXP.render(p,"",2)
check(shown=="Gira la rueda.\nSomething unavailable.\nOpen the gate.\nA choice not available.\n",'partial dialogue and atomic choice fallback')
menu=Window_Base.new
b=menu.contents
b.draw_text(Rect.new(4,0,120,32),'Item')
b.draw_text(4,32,120,32,'Skill')
b.draw_text(4,64,120,32,'Play Time')
b.draw_text(4,96,42,32,'Level')
check(b.draws.map{|d|d[0]}==['Objetos','Habilidades','Tiempo de juego','Nivel'],'native labels')
check(b.text_size('Item').width=='Objetos'.size*8,'label measurement')
menu.draw_actor_name($data_actors[1])
check(b.draws.last[0]=='Aster','identity preserved')
name=Window_NameInput.new
name.contents.draw_text(4,0,100,32,'Item')
check(name.contents.draws.last[0]=='Item','name input preserved')
free=Bitmap.new(400,128)
free.draw_text(4,0,120,32,'Item')
check(free.draws.last[0]=='Item','unregistered artwork untouched')
w.contents.draw_text(4,0,40,32,'Item')
check(w.contents.draws.last[0]=='Item','no nested message glyph hook')
transport.ready=false
dynamic=Window_Base.new
db=dynamic.contents
db.font.size=19;db.font.color=Color.new(170,255,255)
db.draw_text(0,0,200,32,'Sentinel')
db.draw_text(0,32,300,32,'This is a secret passage.')
db.font.size=25;db.font.color=Color.new(100,100,100)
check(db.draws.size==2,'first native draws')
IATraductoraXPUI.tick
transport.ready=true
sleep 0.06
IATraductoraXPUI.tick
check(db.draws.include?(['Centinela',19,170]),'native async term replay')
check(db.draws.include?(['Este es un pasadizo secreto.',19,170]),'native async description replay')
check(db.font.size==25 && db.font.color.red==100,'font restored')
check(db.fills.size==2,'only own region restored')
transport.ready=false
stale=Window_Base.new
stale.contents.draw_text(0,0,200,32,'Please lower the bridge.')
stale.contents.fill_rect(0,0,200,32,Color.new(0,0,0))
before=stale.contents.draws.length
sleep 0.06;IATraductoraXPUI.tick
transport.ready=true
sleep 0.06;IATraductoraXPUI.tick
check(stale.contents.draws.length==before,'stale native region was replayed')
Graphics.update
badge=IATraductoraXPUI.instance_variable_get(:@badge)
check(badge && badge.bitmap.draws.last[0].index('IA Traductora')==0,'native status indicator')
puts 'IA_RPGXP_COVERAGE_NATIVE_UI_DIALOGUE_STATUS_PASS'
