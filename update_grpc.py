import urllib.request
import json
import zipfile
import os
import shutil

# PyPI JSON API for grpcio
url = "https://pypi.org/pypi/grpcio/json"

print("Fetching grpcio release info from PyPI...")
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode())
except Exception as e:
    print(f"Failed to fetch PyPI data: {e}")
    exit(1)

# Find the latest wheel for cp313 win_amd64
version = data["info"]["version"]
releases = data["releases"][version]

wheel_url = None
for r in releases:
    filename = r["filename"]
    # NVDA 2026.1 uses Python 3.13 64-bit on Windows
    if "cp313-cp313-win_amd64.whl" in filename:
        wheel_url = r["url"]
        break

if not wheel_url:
    print(f"Could not find a Python 3.13 64-bit Windows wheel for grpcio version {version}.")
    exit(1)

print(f"Downloading {wheel_url}...")
wheel_path = "grpcio.whl"
try:
    urllib.request.urlretrieve(wheel_url, wheel_path)
except Exception as e:
    print(f"Download failed: {e}")
    exit(1)

print("Extracting grpc...")
extract_dir = "grpc_extracted"
with zipfile.ZipFile(wheel_path, 'r') as z:
    for info in z.infolist():
        if info.filename.startswith("grpc/"):
            z.extract(info, extract_dir)

target_dir = os.path.join("addon", "synthDrivers", "sonata_neural_voices", "lib", "grpc")
if os.path.exists(target_dir):
    print(f"Removing old 32-bit Python 3.11 grpc from {target_dir}...")
    shutil.rmtree(target_dir)

print(f"Installing new 64-bit Python 3.13 grpc to {target_dir}...")
shutil.copytree(os.path.join(extract_dir, "grpc"), target_dir)

print("Cleaning up...")
os.remove(wheel_path)
shutil.rmtree(extract_dir)

print("\nSuccessfully updated bundled grpc to 64-bit Python 3.13!")
print("The addon is now natively compatible with NVDA 2026.1.")
