import urllib.request
import json
import sys

def test_friends(server, username):
    url = f"https://{server}/friends/{username}"
    print(f"Testing: {url}")
    try:
        resp = urllib.request.urlopen(url, timeout=5.0)
        data = json.loads(resp.read().decode("utf-8"))
        print(f"Success: {data}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    server = sys.argv[1] if len(sys.argv) > 1 else "katto-server-production.up.railway.app"
    user = sys.argv[2] if len(sys.argv) > 2 else "faeemaxp"
    test_friends(server, user)
