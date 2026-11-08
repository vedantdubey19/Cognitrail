import json
import resource
import sys


def main():
    resource.setrlimit(resource.RLIMIT_CPU, (8,8))
    if sys.platform.startswith('linux'):
        resource.setrlimit(resource.RLIMIT_AS, (192*1024*1024,192*1024*1024))
    import pymupdf
    data = sys.stdin.buffer.read(5*1024*1024 + 1)
    with pymupdf.open(stream=data, filetype='pdf') as document:
        if document.needs_pass or len(document) > 30:
            return 1
        parts = []
        for page in document:
            parts.append(page.get_text())
            if sum(len(part) for part in parts) > 100000:
                return 1
        sys.stdout.write(json.dumps('\n'.join(parts)))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1)
