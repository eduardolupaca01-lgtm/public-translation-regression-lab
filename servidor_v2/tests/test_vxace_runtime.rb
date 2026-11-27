# encoding: UTF-8
# Independently written native-window contract fixture, not the RGSS DLL.
require 'tmpdir'
require 'fileutils'
require 'rbconfig'

class Game_Message
  attr_reader :texts, :choices
  attr_accessor :choice_proc
  def initialize
    @texts = []
    @choices = []
  end
end
class Window_Message
  attr_reader :painted, :selected
  def process_all_text
    @painted = $game_message.texts.dup
    Fiber.yield
  end
  def input_choice
    @selected = $game_message.choices.dup
    $game_message.choice_proc.call(1)
    Fiber.yield
  end
end
class Window_ScrollText
  attr_reader :painted
  def start_message
    @painted = $game_message.texts.dup
  end
end

def assert(value, label)
  raise label unless value
end

JA = 'おはようございます。'
EN = 'Thank you for your help.'
CHOICE = 'Open the door.'
CLOSE = 'Close the window.'
ANSWERS = {JA=>'Buenos días.', EN=>'Gracias por tu ayuda.', CHOICE=>'Abre la puerta.', CLOSE=>'Cierra la ventana.'}
PLUGIN = File.expand_path('../vxace/IATraductoraVXACE.rb', File.dirname(__FILE__))
SIDECAR = File.join('IA Traductora','.local','Rpg')
MOCK_TOKEN = 'a'*64

def fake_poll
  session = File.join(SIDECAR,'vxace-ipc',MOCK_TOKEN)
  Dir.glob(File.join(session,'*.req')).each do |file|
    fields = File.binread(file).split("\n")
    assert(fields[0]=='IA-VXACE-REQUEST-1' && fields[1]==MOCK_TOKEN,'request authentication')
    request_id = File.basename(file,'.req')
    texts = fields[3..-1].map { |item| [item].pack('H*').force_encoding('UTF-8') }
    output = texts.map { |text| ANSWERS.key?(text) ? ANSWERS[text].unpack('H*')[0] : '-' }
    File.delete(file)
    response = File.join(session,request_id+'.res')
    File.binwrite(response+'.part',(["IA-VXACE-RESPONSE-1",MOCK_TOKEN,request_id]+output).join("\n")+"\n")
    File.rename(response+'.part',response)
  end
end

def run_fiber(mock, label, &action)
  fiber=Fiber.new(&action)
  frames=0
  deadline=Time.now+60
  while fiber.alive?
    assert(Time.now<deadline,label+' timeout')
    fiber.resume
    frames+=1
    yield_frame = mock && frames>4
    fake_poll if yield_frame
    sleep 0.012 if fiber.alive?
    if mock && frames<=3 && label=='dialogue'
      assert($game_message.texts[0].include?(JA),'message changed before response')
    end
  end
  assert(frames>1,label+' did not use native fiber')
end

def checks(mock)
  $game_message=Game_Message.new
  original=['\C[2]'+JA+'\C[0]',EN]
  $game_message.texts.concat(original)
  # This is a native mutable choice array, not choices=.
  choices=[CHOICE,CLOSE]
  choices.each { |choice| $game_message.choices.push(choice) }
  chosen=nil
  $game_message.choice_proc=proc { |index| chosen=index }
  window=Window_Message.new
  run_fiber(mock,'dialogue') { window.process_all_text }
  assert(window.painted && window.painted.length==2,'native message missing')
  assert(window.painted[0].start_with?('\C[2]') && window.painted[0].end_with?('\C[0]'),'control codes changed')
  assert(window.painted[0]!=original[0] && window.painted[0] !~ /[ぁ-ゖァ-ヺ一-龯]/,'Japanese first paint unchanged')
  assert(window.painted[1]!=EN && window.painted[1] =~ /gracias|ayuda|agradez/i,'English first paint unchanged')
  assert($game_message.texts==original,'original event strings changed')
  run_fiber(mock,'choices') { window.input_choice }
  assert(window.selected[0]!=CHOICE && window.selected[0] =~ /puerta/i,'choice 0 untranslated')
  assert(window.selected[1]!=CLOSE && window.selected[1] =~ /ventana/i,'choice 1 untranslated')
  assert(chosen==1 && $game_message.choices==choices,'choice index or original list changed')
  # No second visit is needed. Scroll text uses a separate nonblocking gate.
  $game_message.texts.replace([EN])
  scroll=Window_ScrollText.new
  scroll.start_message
  assert(scroll.painted && scroll.painted[0]!=EN,'native scroll text was not reused')
  assert($game_message.texts==[EN],'scroll original changed')
  # Standalone choice, without a preceding message.
  $game_message.texts.clear
  $game_message.choices.replace([CHOICE,CLOSE])
  second=Window_Message.new
  count=IATraductoraVXACE.requests
  run_fiber(mock,'standalone choices') { second.input_choice }
  assert(second.selected==window.selected && IATraductoraVXACE.requests==count,'duplicate request or standalone choice failed')
  if mock
    assert(window.painted==['\C[2]Buenos días.\C[0]','Gracias por tu ayuda.'],'mock output mismatch')
    assert(window.selected==['Abre la puerta.','Cierra la ventana.'],'mock choices mismatch')
  end
  puts(mock ? 'IA_VXACE_SYNTHETIC_NATIVE_FIBER_PASS' : 'IA_VXACE_REAL_OPUS_DESKTOP_RUBY_NATIVE_CONTRACT_PASS')
end

if ARGV[0]=='--mock'
  Dir.mktmpdir('ia-vxace-') do |game|
    Dir.chdir(game) do
      File.binwrite('Game.exe','synthetic, never executed')
      dir=File.join(SIDECAR,'vxace-ipc',MOCK_TOKEN)
      FileUtils.mkdir_p(dir)
      File.binwrite(File.join(SIDECAR,'vxace-session.txt'),"IA-VXACE-SESSION-1\n#{MOCK_TOKEN}\n1234\n#{Process.pid}\n")
      load PLUGIN
      # No helper exists in this fixture: a valid session must not spawn it.
      assert(IATraductoraVXACE.session,'valid session was not recognized')
      assert(!IATraductoraVXACE.launch_failed?,'live session was treated as failed')
      assert(IATraductoraVXACE.instance_variable_get(:@launch_error).nil?,'duplicate launch attempted')
      # Reproduce the previous regression with a real session but a stale
      # startup failure. This must not suppress the pending Japanese response.
      IATraductoraVXACE.instance_variable_set(:@launch_error,'IA_VXACE_HELPER_NO_VERIFICADO')
      assert(!IATraductoraVXACE.launch_failed?,'startup error overrode a valid session')
      checks(true)
      puts 'IA_VXACE_ACTIVE_SESSION_OVERRIDES_STALE_LAUNCH_ERROR_PASS'

      # An expired plan must preserve the original and count failure once.
      p=IATraductoraVXACE.plan(['Unseen source.'])
      p[:deadline]=Time.now.to_f-1
      assert(IATraductoraVXACE.advance(p) && IATraductoraVXACE.result(p)==['Unseen source.'],'timeout fallback changed original')
      failures=IATraductoraVXACE.failures
      assert(IATraductoraVXACE.advance(p) && IATraductoraVXACE.failures==failures,'timeout counted twice')

      # A different parent process is not a valid session; do not bypass the
      # actual startup error, write requests or change the displayed original.
      descriptor=File.join(SIDECAR,'vxace-session.txt')
      File.binwrite(descriptor,"IA-VXACE-SESSION-1\n#{MOCK_TOKEN}\n1234\n#{Process.pid+1}\n")
      assert(!IATraductoraVXACE.session,'foreign session accepted')
      assert(IATraductoraVXACE.launch_failed?,'missing valid session hid launch failure')
      p=IATraductoraVXACE.plan(['Open another door.'])
      count=IATraductoraVXACE.requests
      assert(IATraductoraVXACE.advance(p),'known launch failure was not handled')
      assert(IATraductoraVXACE.result(p)==['Open another door.'],'foreign session changed original')
      assert(IATraductoraVXACE.requests==count,'request published to foreign session')
      puts 'IA_VXACE_FOREIGN_SESSION_FAILS_CLOSED_PASS'
    end
  end
elsif ARGV[0]=='--real'
  game=File.realpath(ARGV.fetch(1))
  Dir.chdir(game) do
    installed=File.expand_path(File.join(SIDECAR,'engine','vxace','IATraductoraVXACE.rb'))
    load installed
    deadline=Time.now+180
    until IATraductoraVXACE.session
      assert(!IATraductoraVXACE.launch_failed?, 'IA_VXACE_VERIFIED_LAUNCH_FAILED: '+IATraductoraVXACE.launch_diagnostic)
      assert(Time.now<deadline,'IA_VXACE_VERIFIED_WORKER_BOOT_TIMEOUT: '+IATraductoraVXACE.launch_diagnostic)
      sleep 0.2
    end
    checks(false)
  end
elsif ARGV[0]=='--launch-probe'
  game=File.realpath(ARGV.fetch(1))
  Dir.chdir(game) do
    load File.expand_path(File.join(SIDECAR,'engine','vxace','IATraductoraVXACE.rb'))
    deadline=Time.now+30
    loop do
      status=IATraductoraVXACE.launch_diagnostic
      break if status.include?('IA_VXACE_PROBE_READY')
      assert(!IATraductoraVXACE.launch_failed?, 'IA_VXACE_PROBE_LAUNCH_FAILED: '+status)
      assert(Time.now<deadline,'IA_VXACE_PROBE_TIMEOUT: '+status)
      sleep 0.1
    end
    puts 'IA_VXACE_RUBY_UNICODE_NATIVE_SPAWN_PASS'
  end
else
  raise 'use --mock, --real or --launch-probe <fixture>'
end
