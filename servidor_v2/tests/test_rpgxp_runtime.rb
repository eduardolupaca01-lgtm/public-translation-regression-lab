# encoding: UTF-8
# An independently authored XP-style fixture; not a proprietary RGSS DLL.
class Game_Temp
  attr_accessor :message_text,:choice_start,:choice_max,:choice_proc,:num_input_variable_id
  def initialize
    @num_input_variable_id=0
  end
end
class Window_Message
  attr_reader :painted,:paints,:selected
  def initialize
    @contents_showing=false
    @fade_in=@fade_out=false
    @paints=0
  end
  def update
    if !@contents_showing && $game_temp.message_text
      refresh
      @contents_showing=true
    end
  end
  def refresh
    @paints+=1
    @painted=$game_temp.message_text.dup
    $game_temp.message_text.replace('')
  end
  def choose(i)
    @selected=i
    $game_temp.choice_proc.call(i)
  end
end
def check(value,message)
  raise message unless value
end
require File.expand_path('../rpgxp/IATraductoraXP.rb',File.dirname(__FILE__))
class MockTransport
  attr_reader :requests
  def initialize
    @requests=[]
    @ready=false
    @answers={
      ['en','Please open the door.']=>'Abre la puerta.',
      ['en','Wait here.']=>'Espera aquí.',
      ['ja','おはようございます。']=>'Buenos días.',
      ['en','You have 7 coins.']=>'Tienes 7 monedas.'
    }
  end
  def ready!
    @ready=true
  end
  def poll(lang,text)
    key=[lang,text]
    @requests << key unless @requests.include?(key)
    @ready ? @answers[key] : nil
  end
end
transport=MockTransport.new
IATraductoraXP.attach(transport)
$game_temp=Game_Temp.new
raw="\\C[2]Please open the door.\\C[0]\nおはようございます。\nWait here.\n"
$game_temp.message_text=raw.dup
$game_temp.choice_start=2
$game_temp.choice_max=1
chosen=nil
callback=proc { |i| chosen=i }
$game_temp.choice_proc=callback
window=Window_Message.new
window.update
check(window.paints==0,'original leaked before translation')
check($game_temp.message_text==raw,'pending event changed')
transport.ready!
window.update
check(window.paints==1,'native refresh count')
check(window.painted=="\\C[2]Abre la puerta.\\C[0]\nBuenos días.\nEspera aquí.\n",'native mixed-language translation')
check($game_temp.message_text==raw,'original raw string changed')
check($game_temp.choice_start==2 && $game_temp.choice_max==1 && $game_temp.choice_proc.equal?(callback),'choice state changed')
window.choose(0)
check(chosen==0,'choice index changed')
count=transport.requests.length
$game_temp.message_text=raw.dup
reopened=Window_Message.new
reopened.update
check(reopened.paints==1 && reopened.painted==window.painted,'cache did not paint immediately')
check(transport.requests.length==count,'cache repeated request')
$game_temp.message_text="\\CUSTOM[abc]Please open the door."
unsafe=Window_Message.new;unsafe.update
check(unsafe.paints==1 && unsafe.painted=="\\CUSTOM[abc]Please open the door.",'unknown control modified')
$game_temp.message_text="You have 7 coins."
$game_temp.num_input_variable_id=3
name=Window_Message.new;name.update
check(name.paints==1 && name.painted=="You have 7 coins.",'number input interfered')
$game_temp.num_input_variable_id=0
p=IATraductoraXP.plan("You have 7 coins.")
check(IATraductoraXP.advance(p),'numeric text not translated')
check(IATraductoraXP.render(p,"You have 7 coins.")=="Tienes 7 monedas.",'number not retained')
check(!IATraductoraXP.valid?('en','You have 7 coins.','Tienes 8 monedas.'),'numeric corruption accepted')
check(!IATraductoraXP.valid?('en','Please open the door.',"\\V[5]Abre la puerta."),'injected control accepted')
check(IATraductoraXP.plan([255].pack('C*'))==nil,'invalid UTF-8 accepted')
IATraductoraXP.attach(nil)
$game_temp.message_text="Please open the door."
offline=Window_Message.new;offline.update
check(offline.paints==1 && offline.painted=="Please open the door.",'missing transport blocked game')
puts 'IA_RPGXP_NATIVE_FIRST_VIEW_CHOICES_CACHE_CONTROLS_PASS'
