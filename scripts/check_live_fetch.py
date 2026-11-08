"""Opt-in network integration: reads one public documentation page, without search/model keys."""
from app.fetcher import fetch, parse_html

if __name__=='__main__':
    result=fetch('https://www.python.org/doc/')
    title,text,published=parse_html(result['body'],result['url'],100000)
    assert len(text)>100 and 'Python' in text
    print('Public HTTPS fetch passed with certificate validation and DNS pinning:',title)
