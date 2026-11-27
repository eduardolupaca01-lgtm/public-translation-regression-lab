# encoding: UTF-8
# Acceptance-only semantic contract for an independently authored sentence.
# Desktop Ruby only; do not introduce modern Unicode APIs into RGSS1.
module RPGXPProseContract
  SOURCE='Hear me, mighty king!'
  def self.inspect_translation(value)
    text=value.is_a?(String) ? value : ''
    normalized=text.dup.encode('UTF-8').unicode_normalize(:nfd).gsub(/\p{Mn}/,'').downcase
    changed=!text.strip.empty? && normalized!=SOURCE.downcase
    royal=!!(normalized =~ /\b(?:rey|monarca)\b/)
    hear=!!(normalized =~ /\b(?:escuch(?:a|ad|e|en)(?:me)?|oye(?:me)?|oig(?:a|an)(?:me)?|oid(?:me)?|oirme|prest(?:a|ad|e|en)(?:me)?\s+atencion)\b/)
    negated=!!(normalized =~ /\b(?:no|nunca|jamas)\b/)
    {:changed=>changed,:royal=>royal,:hear=>hear,:negated=>negated,
     :ok=>changed && royal && hear && !negated}
  rescue EncodingError,ArgumentError
    {:changed=>false,:royal=>false,:hear=>false,:negated=>false,:ok=>false}
  end
  def self.self_test!
    ['Escúchame, poderoso rey!','Escúcheme, gran rey.',
     'Óyeme, rey poderoso.','Oídme, poderoso rey.',
     'Oiga mi voz, poderoso monarca.','Escucha mi voz, majestuoso rey.',
     'Escuchadme, gran rey.'].each do |value|
      raise 'valid Spanish hearing command rejected' unless inspect_translation(value)[:ok]
    end
    [SOURCE,'','Mighty king!','El rey es poderoso.',
     'Mata al rey poderoso.','Escúchame, poderoso soldado.',
     'No me escuches, rey poderoso.','No escuches, poderoso rey.'].each do |value|
      raise 'wrong or untranslated meaning accepted' if inspect_translation(value)[:ok]
    end
    # Demonstrate the prior false-negative without weakening the assertion.
    raise 'old checker unexpectedly accepts accented verb' if 'Escúchame, poderoso rey!' =~ /escuch|oye|oiga|o.d|o.r/i
    puts 'IA_RPGXP_EXPANDED_PROSE_SEMANTIC_CONTRACT_PASS'
  end
end
