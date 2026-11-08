import json
import subprocess
import sys
from pathlib import Path


def parse_document(data, filename, settings):
    if not filename or Path(filename).name != filename or '\\' in filename or len(filename) > 180:
        raise ValueError('Invalid filename')
    if len(data) > settings.max_file_bytes:
        raise ValueError('File exceeds 5 MB limit')
    if filename.lower().endswith('.txt') and not data.startswith(b'%PDF') and b'\0' not in data:
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError as exc:
            raise ValueError('Text must be UTF-8') from exc
    elif filename.lower().endswith('.pdf') and data.startswith(b'%PDF-'):
        try:
            result = subprocess.run([sys.executable,'-m','app.pdf_worker'], input=data, capture_output=True,
                                    timeout=10, check=True, env={'PATH':'/usr/bin:/bin','PYTHONUTF8':'1'})
            text = json.loads(result.stdout)
        except (subprocess.SubprocessError, ValueError) as exc:
            raise ValueError('PDF rejected: extraction failed or exceeded limits') from exc
    else:
        raise ValueError('Only PDF and UTF-8 TXT files are supported')
    if not text.strip() or len(text) > settings.max_source_chars:
        raise ValueError('Source text is empty or exceeds character budget')
    return text
