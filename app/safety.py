import re
import unicodedata

SECRETS = re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bAKIA[A-Z0-9]{16}\b|\bAIza[A-Za-z0-9_-]{35}\b|\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}\b')
INJECTION = re.compile(r'ignore.{0,30}(?:instructions|rules)|(?:^|\n)\s*(?:system|developer)\s*:|reveal.{0,30}(?:secret|key)|<\|im_start\|>|(?:execute|run)\s+(?:shell|command)', re.I)


def clean_input(text):
    if SECRETS.search(text):
        raise ValueError('Possible real credential detected; remove sensitive data')
    return text


def inspect_source(text):
    normalized = unicodedata.normalize('NFKC', text)
    normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Cf')
    return bool(INJECTION.search(normalized))


def words(text):
    return set(re.findall(r'\w+', text.casefold())) - {'the','a','an','is','are','and','or','of','in','to','what','how','for','with','does','do','on','it','this','that','research','evidence','question'}
