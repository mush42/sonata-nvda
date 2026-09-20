import urllib.request
import json
import zipfile
import os
import shutil
import glob

# PyPI JSON API for cffi
url = "https://pypi.org/pypi/cffi/json"

print("Fetching cffi release info from PyPI...")
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
    print(f"Could not find a Python 3.13 64-bit Windows wheel for cffi version {version}.")
    exit(1)

print(f"Downloading {wheel_url}...")
wheel_path = "cffi.whl"
try:
    urllib.request.urlretrieve(wheel_url, wheel_path)
except Exception as e:
    print(f"Download failed: {e}")
    exit(1)

print("Extracting cffi...")
extract_dir = "cffi_extracted"
backend_pyd_name = None
with zipfile.ZipFile(wheel_path, 'r') as z:
    for info in z.infolist():
        if info.filename.startswith("cffi/") or info.filename.startswith("_cffi_backend"):
            z.extract(info, extract_dir)
            if info.filename.startswith("_cffi_backend") and info.filename.endswith(".pyd"):
                backend_pyd_name = info.filename

if backend_pyd_name is None:
    print("Could not find _cffi_backend .pyd in wheel.")
    exit(1)

target_dir = os.path.join("addon", "synthDrivers", "sonata_neural_voices", "lib")

print(f"Removing old 32-bit Python 3.11 _cffi_backend .pyd from {target_dir}...")
for old in glob.glob(os.path.join(target_dir, "_cffi_backend*.pyd")):
    print(f"  removing {old}")
    os.remove(old)

cffi_target = os.path.join(target_dir, "cffi")
if os.path.exists(cffi_target):
    print(f"Removing old cffi package from {cffi_target}...")
    shutil.rmtree(cffi_target)

print(f"Installing new 64-bit Python 3.13 cffi to {target_dir}...")
shutil.copy(os.path.join(extract_dir, backend_pyd_name), os.path.join(target_dir, backend_pyd_name))
shutil.copytree(os.path.join(extract_dir, "cffi"), cffi_target)

print("Cleaning up...")
os.remove(wheel_path)
shutil.rmtree(extract_dir)

print("\nSuccessfully updated bundled cffi to 64-bit Python 3.13!")
print("The addon is now natively compatible with NVDA 2026.1.")
