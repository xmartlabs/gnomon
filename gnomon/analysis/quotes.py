import re


# Politeness markers in your own prompts (for the "how polite are you" card). Word-boundaried.
_POLITE_RE = re.compile(r'\b(thanks|thank you|thank u|thx|please|pls|appreciate|'
                        r'much appreciated|good (?:job|work)|nice work|well done)\b', re.I)

# --- "In your own words" cards: pulled VERBATIM from your real prompts. These quote raw
# session text, so they render ONLY on the local page and are deliberately kept OUT of the
# shareable download card (see card_data). HTML-escape every quote before injecting it. ---
_TYPO_WORDS = {"teh", "hte", "thge", "wrok", "adn", "nad", "recieve", "seperate", "definately",
               "thier", "alot", "wtih", "wiht", "taht", "thta", "jsut", "becuase", "plz", "pls",
               "u", "ur", "r", "y", "k", "yea", "yeah", "yep", "yup", "nope", "lol", "lmao", "idk",
               "dont", "wont", "cant", "doesnt", "didnt", "couldnt", "wouldnt", "isnt", "wasnt",
               "youre", "theyre", "thats", "whats", "hows", "im", "ive", "ill", "id", "hes", "shes",
               "wodn", "fo", "ot", "si", "hmm", "hmmm", "wat", "wut", "tho", "thru", "fix", "undo",
               "nvm", "rn", "btw", "fr", "ok", "okay", "kk", "gah", "ugh", "argh", "oof",
               "wtf", "wth", "omg", "ya", "nah", "meh", "huh", "welp", "oop", "oops", "aight"}


def _typo_score(text):
    """Rough 'how garbled/casual is this' score — counts likely-typo / texting tokens.
    Heuristic, not a spell-checker; only used to surface a genuinely odd REAL prompt."""
    s = 0
    for t in re.findall(r"[a-z0-9']+", text.lower()):
        if t in _TYPO_WORDS:
            s += 1
        elif len(t) >= 4 and not re.search(r'[aeiou]', t):   # a vowel-less chunk
            s += 1
        elif re.search(r'(.)\1\1', t):                        # 3+ of the same letter (loool, yesss)
            s += 1
        elif re.search(r'[a-z]\d|\d[a-z]', t):                # digits glued into a word
            s += 1
        elif "'" not in t and t.endswith(("nt", "re", "ll", "ve")) and t in _TYPO_WORDS:
            s += 1                                            # missing apostrophe (dont, youre)
    return s


def _caps_ratio(text):
    letters = [c for c in text if c.isalpha()]
    return (sum(1 for c in letters if c.isupper()) / len(letters)) if letters else 0.0


# Frustration / distress markers for the "biggest crash-out" card — these gate it, so a
# clean all-caps EXCITEMENT prompt ("ONWARDS", "PUSH THRU") doesn't read as a meltdown.
_RAGE_RE = re.compile(r'\b(wtf|wth|ffs|ugh+|argh+|seriously|literally|stop+|nope|why+|'
                      r'are you (?:kidding|serious|sure|joking)|come on|for real|already said|'
                      r'i said|told you|do ?not|dont|cant|never|jesus|christ|damn|hell|crap|'
                      r'shit|fuck\w*|wrong|broke|broken|nightmare|stuck|fail\w*|hate|pressure|'
                      r'stress\w*|overwhelm\w*|dying|exhaust\w*|help|no+\b|not\b)\b', re.I)


def _crashout_score(text, hour=None):
    """How 'heated' a prompt reads — caps, exclamation pile-ups, ALLCAPS words, frustration
    words, and BREVITY (terse all-caps menace — 'NO STOP', 'SOMETHING IS WRONG' — is funnier
    than a long rant). A 2–6am prompt gets extra weight too: the witching-hour grind is its
    own genre of crash-out. Pulls a REAL prompt, never invents one."""
    wc = len(text.split())
    caps = _caps_ratio(text)
    bangs = min(text.count("!") + text.count("?"), 5)
    allcaps = min(len(re.findall(r'\b[A-Z]{3,}\b', text)), 4)
    rage = min(len(_RAGE_RE.findall(text)), 3)
    brevity = max(0, 9 - wc) * 0.5
    witching = 1.8 if hour is not None and 2 <= hour < 6 else 0   # 2–6am: posted from the trenches
    return caps * 2.5 + brevity + allcaps * 0.4 + rage * 0.5 + bangs * 0.3 + witching


_FEELS_RE = re.compile(r'\b(worried|scared|nervous|anxious|stressed|exhausted|confused|'
                       r'stupid|dumb|idiot|hopeless|unemploy\w*|crying|sobbing|sad|miserable|'
                       r'overwhelmed|panic\w*|dying|losing my mind|cant anymore|please work)\b', re.I)
_EMOTICON_RE = re.compile(r"[:;=]['\-^]?[\(\)\[\]\/\\|dpox3<>]", re.I)
# Content-free affirmations/fillers — an "off the cuff" card needs more than "yep :)".
_FILLER = {"ok", "okay", "yes", "yep", "yup", "yeah", "ya", "sure", "nice", "great", "cool",
           "perfect", "thanks", "thank", "you", "done", "k", "kk", "good", "awesome", "love",
           "got", "it", "this", "that", "lol", "haha", "nvm", "fine", "right", "correct", "exactly"}


def _cryptic_score(text):
    """The funniest off-the-cuff prompts: tiny, typo'd, lowercase, vague, and — the gold —
    a stray emoticon or a flash of human vulnerability ('Im worried im unemploybale :(')."""
    wc = len(text.split())
    typ = _typo_score(text)
    vague = len(re.findall(r'\b(it|that|this|the thing|those|them|stuff|one)\b', text, re.I))
    lower = 1 if text == text.lower() else 0
    nopunct = 1 if not re.search(r'[.?!]', text.strip()) else 0
    short = max(0, 7 - wc) * 0.25
    emo = 1.6 if _EMOTICON_RE.search(text) else 0
    feels = 1.3 if _FEELS_RE.search(text) else 0
    return typ * 1.0 + vague * 0.55 + lower * 0.5 + nopunct * 0.35 + short + emo + feels


# A prompt can be surfaced verbatim only if it's actually the user's words — not a harness
# marker, and not carrying a secret. We NEVER alter a shown prompt (Max: zero redaction); we
# just refuse to SELECT one that's a credential or a system artifact rather than a real prompt.
_SECRET_RE = re.compile(r'eyJ[A-Za-z0-9_\-]{20,}|sk-[A-Za-z0-9]{16,}|gh[posru]_[A-Za-z0-9]{16,}|'
                        r'AKIA[0-9A-Z]{12,}|Bearer\s+\S{16,}|[A-Fa-f0-9]{32,}|[A-Za-z0-9_\-]{36,}', re.I)
_SYS_MARKER_RE = re.compile(r'\[request interrupted|\[image\b|\[image\s*#|\[pasted|\[tool|'
                            r'<system|<command|<local-command|this block is not|tool_use|caveat:', re.I)


def _safe_quote(text):
    if not text or len(text) > 140:
        return False
    if _SYS_MARKER_RE.search(text) or _SECRET_RE.search(text):
        return False
    if any(len(tok) > 32 for tok in text.split()):   # a giant unbroken token = key/url/hash, not a word
        return False
    toks = text.split()
    if len(toks) == 1 and re.fullmatch(r"[A-Z0-9]*\d[A-Z0-9]*", toks[0]) and len(toks[0]) >= 7:
        return False                                  # a lone caps+digits token = Slack/ID, not a prompt
    # PII guard — don't auto-SURFACE someone else's email / phone / long digit run. (This is a
    # safe DEFAULT for arbitrary users; it never alters a prompt, it just won't select this one.)
    if re.search(r'[\w.+-]+@[\w-]+\.[a-z]{2,}|\b\d{3}[\s.\-]?\d{3}[\s.\-]?\d{4}\b|\b\d{6,}\b', text, re.I):
        return False
    return True
