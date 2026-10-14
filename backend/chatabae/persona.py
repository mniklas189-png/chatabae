"""The user's persona: who the user is in a chat, from their profile or from what they say about themselves."""
from __future__ import annotations

import re

NAME = re.compile(r"(?<!\w)(?:my name is|my name's|i am called|i'm called|im called|call me|ich heiße|ich heisse|mein name ist|nenn mich)\s+([^\W\d_][\w'-]{0,29})", re.IGNORECASE)
NOT_NAMES = {"not", "no", "just", "a", "an", "the", "nicht", "kein", "keine", "so", "you", "du", "dich", "me", "mich"}
# An age is only read when the number ends the phrase ("I'm 16", "im 16 and ..."), not in "ur 2 hot" or "I'm 5 minutes away".
UNITS = r"(?=\s*(?:$|[.,!?;:)*~\n]|-\s|(?:and|und|but|aber|lol|btw|now|too|jetzt|years?|yrs?|yo|y/o|jahre?|j|so|tho|though|haha|already|schon|myself|selbst|today|heute|your|you|ur|u|du|i|ich|my|mein|meine)(?!\w)))"
SELF_AGE = re.compile(r"(?<!\w)(?:i am|i'm|im|i’m|ich bin|bin)\s+(?:only\s+|just\s+|erst\s+|nur\s+)?(\d{1,3})(?!\d)" + UNITS, re.IGNORECASE)
OTHER_AGE = re.compile(r"(?<!\w)(?:you are|you're|you’re|youre|your|ur|u r|du bist|he is|he's|she is|she's|they are|they're|er ist|sie ist|sie sind)\s+(?:only\s+|just\s+|erst\s+|nur\s+)?(\d{1,3})(?!\d)" + UNITS, re.IGNORECASE)
YEARS_OLD = re.compile(r"(?<!\d)(\d{1,3})\s*(?:-|\s)?(?:years?[\s-]*old|yrs?[\s-]*old|y/?o\b|yo\b|jahre alt|jahre jung|jährig|jaehrig)", re.IGNORECASE)
MINOR_WORDS = re.compile(r"(?<!\w)(?:minderjährig\w*|underage|under\s*18|unter\s*18)(?!\w)", re.IGNORECASE)
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
                "eins": 1, "zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10, "elf": 11, "zwölf": 12, "dreizehn": 13, "vierzehn": 14, "fünfzehn": 15, "sechzehn": 16, "siebzehn": 17}
WORD_AGE = re.compile(r"(?<!\w)(?:i am|i'm|im|ich bin|you are|you're|your|du bist|he is|she is|er ist|sie ist)\s+(?:only\s+|just\s+|erst\s+|nur\s+)?(" + "|".join(NUMBER_WORDS) + r")(?:\s+(?:years?|jahre))?(?!\w)", re.IGNORECASE)


def clean_persona(value):
    """A saved profile persona: name, optional age and a short description."""
    if not isinstance(value, dict):
        return {}
    persona = {}
    name = str(value.get("name") or "").strip()[:60]
    about = str(value.get("about") or "").strip()[:600]
    age = value.get("age")
    if name:
        persona["name"] = name
    if about:
        persona["about"] = about
    if isinstance(age, int) and not isinstance(age, bool) and 1 <= age <= 120:
        persona["age"] = age
    return persona


def read_statements(text):
    """Name and age the user gives for themselves, and whether anyone in the text is said to be under 18."""
    found = {}
    name = NAME.search(text)
    if name and name.group(1).casefold() not in NOT_NAMES:
        found["name"] = name.group(1)[:1].upper() + name.group(1)[1:]
    ages = [int(m.group(1)) for m in SELF_AGE.finditer(text)]
    ages += [NUMBER_WORDS[m.group(1).casefold()] for m in WORD_AGE.finditer(text) if m.group(0).casefold().startswith(("i", "ich"))]
    ages = [age for age in ages if 1 <= age <= 120]
    if ages:
        found["age"] = ages[-1]
    stated = ages + [int(m.group(1)) for m in OTHER_AGE.finditer(text)] + [int(m.group(1)) for m in YEARS_OLD.finditer(text)]
    stated += [NUMBER_WORDS[m.group(1).casefold()] for m in WORD_AGE.finditer(text)]
    if any(1 <= age < 18 for age in stated) or MINOR_WORDS.search(text):
        found["minor"] = True
    return found


def chat_persona(saved, conversation, user_messages):
    """Merge the profile persona with what the user said in this chat; a stated minor stays for the whole chat."""
    persona = {**clean_persona(saved), **{k: v for k, v in (conversation or {}).items() if k in {"name", "age", "minor"}}}
    for text in user_messages:
        found = read_statements(text)
        if found.get("minor"):
            persona["minor"] = True
        for key in ("name", "age"):
            if key in found:
                persona[key] = found[key]
    if isinstance(persona.get("age"), int) and persona["age"] < 18:
        persona["minor"] = True
    return persona


def describe(persona):
    """The persona as a line for the system prompt."""
    parts = []
    if persona.get("name"):
        parts.append("name " + persona["name"])
    if persona.get("age"):
        parts.append(f"age {persona['age']}")
    if persona.get("about"):
        parts.append("about them: " + persona["about"])
    if not parts:
        return ""
    return ("The user you are talking to (call them by their name now and then): " + "; ".join(parts)
            + ". If the user tells you something new about who they are, go with it.")
