import os
import struct

FILE = "resources.gpak"
OUT = "dump"

os.makedirs(OUT, exist_ok=True)

data = open(FILE, "rb").read()

# --------------------------------------------------
# 1. FIXED HEADER SKIP (THIS IS THE REAL FORMAT)
# --------------------------------------------------
offset = 4

entries = []

# --------------------------------------------------
# 2. Parse index until it breaks naturally
# --------------------------------------------------
while offset < len(data) - 10:
    try:
        name_len = struct.unpack_from("<H", data, offset)[0]

        # stop if clearly invalid
        if name_len == 0 or name_len > 300:
            break

        offset += 2

        name_bytes = data[offset:offset + name_len]
        offset += name_len

        # must look like a path
        if b"/" not in name_bytes:
            break

        name = name_bytes.decode("utf-8", errors="ignore")

        file_size = struct.unpack_from("<I", data, offset)[0]
        offset += 4

        entries.append((name, file_size))

    except:
        break

print(f"[+] parsed entries: {len(entries)}")

if not entries:
    raise Exception("Index parse failed (alignment issue)")

# --------------------------------------------------
# 3. Extract sequentially (sizes, not offsets)
# --------------------------------------------------
pos = offset  # files start right after the index

for name, size in entries:
    blob = data[pos:pos + size]
    pos += size

    out_path = os.path.join(OUT, name)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    with open(out_path, "wb") as f:
        f.write(blob)

    print("extracted:", name)

print("[+] done")