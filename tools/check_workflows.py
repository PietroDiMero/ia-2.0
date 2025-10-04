import os, json, urllib.request, urllib.error
repo = os.getenv('GITHUB_REPOSITORY', 'PietroDiMero/ia-2.0')
token = os.getenv('GITHUB_TOKEN')
if not token:
    print('NO_TOKEN')
    raise SystemExit(2)
url = f'https://api.github.com/repos/{repo}/actions/workflows'
req = urllib.request.Request(url)
req.add_header('Authorization', f'Bearer {token}')
req.add_header('Accept', 'application/vnd.github+json')
try:
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.load(r)
    paths = [wf.get('path') for wf in data.get('workflows', []) if 'path' in wf]
    print('WORKFLOWS_FOUND:', len(paths))
    for p in paths:
        print(p)
except urllib.error.HTTPError as e:
    print('HTTPERROR', e.code)
    try:
        print(e.read().decode())
    except Exception:
        pass
except Exception as e:
    print('ERROR', e)
