import urllib.request
import json
import sys

packages = ["mutagen", "rich", "pillow", "pystray", "markdown-it-py", "mdurl", "Pygments"]

for pkg in packages:
    url = f"https://pypi.org/pypi/{pkg}/json"
    try:
        req = urllib.request.urlopen(url)
        data = json.loads(req.read())
        version = data["info"]["version"]
        releases = data["releases"][version]
        # Prefer source tarball
        source = next((r for r in releases if r["packagetype"] == "sdist"), None)
        # If no sdist, prefer wheel (pillow has issues building from source sometimes)
        if pkg == "pillow":
            source = next((r for r in releases if r["packagetype"] == "bdist_wheel" and "manylinux" in r["filename"] and "x86_64" in r["filename"] and "cp310" in r["filename"]), source)
        
        if source:
            print(f"- name: python3-{pkg}")
            print(f"  buildsystem: simple")
            print(f"  build-commands:")
            print(f"    - pip3 install --no-build-isolation --prefix=/app {source['filename']}")
            print(f"  sources:")
            print(f"    - type: file")
            print(f"      url: {source['url']}")
            print(f"      sha256: {source['digests']['sha256']}")
            print()
        else:
            print(f"# No source found for {pkg}")
    except Exception as e:
        print(f"Error fetching {pkg}: {e}")
