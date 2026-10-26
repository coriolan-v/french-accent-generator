"""Rewrite English phonemes (misaki / Kokoro notation) the way a French speaker says them.

Strength 1 = light, 2 = medium, 3 = thick ("Inspector Clouseau").
"""
import re

# Each level adds to the previous ones. Order matters: multi-character patterns first.
LIGHT = [
    ('θ', 's'), ('ð', 'z'),          # think -> sink, the -> ze
    ('h', ''),                       # hello -> 'ello
    ('ɪ', 'i'), ('ᵻ', 'i'),          # it -> eet
]
MEDIUM = [
    ('ɜɹ', 'œʁ'), ('əɹ', 'œʁ'),      # bird, butter
    ('ɹ', 'ʁ'),                      # French uvular R
    ('ʊ', 'u'),                      # good -> goud
    ('æ', 'a'), ('ɑ', 'a'), ('ɐ', 'a'), ('ʌ', 'œ'),
    ('A', 'e'), ('O', 'o'),          # flatten diphthongs: day -> dé, go -> gô
    ('I', 'aj'), ('W', 'aw'), ('Y', 'ɔj'),
    ('ɾ', 't'), ('ʔ', 't'),          # crisp T instead of American flap
    ('ᵊ', 'ə'),
]
THICK = [
    ('ə', 'œ'),                      # full vowels instead of reduced schwa
]

VOWELS = 'aeiouyøœɛɔəɑæʌɪʊɜAIOWYᵊᵻ'


def _apply(ph, rules):
    for a, b in rules:
        ph = ph.replace(a, b)
    return ph


def _final_stress(word):
    """French stresses the last syllable of a word and lengthens it."""
    word = word.replace('ˈ', '').replace('ˌ', '')
    vowel_starts = [m.start() for m in re.finditer(f'[{VOWELS}]+', word)]
    if not vowel_starts:
        return word
    i = vowel_starts[-1]
    m = re.match(f'[{VOWELS}]+', word[i:])
    j = i + m.end()
    return word[:i] + 'ˈ' + word[i:j] + 'ː' + word[j:] if len(vowel_starts) > 1 else word


def frenchify(phonemes: str, strength: int = 3) -> str:
    ph = _apply(phonemes, LIGHT)
    if strength >= 2:
        ph = _apply(ph, MEDIUM)
    if strength >= 3:
        ph = _apply(ph, THICK)
        ph = re.sub(r'ŋ(?=[\s,.!?;:]|$)', 'ŋɡ', ph)     # sing -> sing-g
        ph = re.sub(r'[^\s,.!?;:—…"()]+', lambda m: _final_stress(m.group(0)), ph)
    return re.sub(r' {2,}', ' ', ph).strip()
