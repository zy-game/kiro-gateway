import sys
import io
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Test admin access
r = requests.get('http://127.0.0.1:8000/admin')
print(f'Status: {r.status_code}')
print(f'Content-Type: {r.headers.get("content-type")}')
print(f'Length: {len(r.text)}')
if r.status_code == 200:
    print(r.text[:500])
else:
    print(r.text)
