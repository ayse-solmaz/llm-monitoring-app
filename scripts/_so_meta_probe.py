"""List TVM VM metadata / function names from an MLC gemma-cpu.so (diag only)."""
from __future__ import annotations

import re
import sys

from tvm.runtime import load_module

KEYS = (
    "decode", "embed", "logit", "quant", "gemm", "prefill", "batch",
    "lm", "head", "matmul", "fused", "dequant", "softmax",
)


def get_fn(mod, name):
    try:
        return mod.get_function(name, allow_missing=True)
    except TypeError:
        try:
            return mod.get_function(name)
        except Exception:
            return None
    except Exception:
        return None


def extract_meta(mod) -> str | None:
    f = get_fn(mod, "_metadata")
    if f is not None:
        try:
            return str(f())
        except Exception as e:
            print("root _metadata call err:", e)
    # imports
    imps = []
    try:
        imps = list(mod.imported_modules)
    except Exception:
        try:
            imps = list(mod.imports)
        except Exception as e:
            print("no imports:", e)
    for i, im in enumerate(imps):
        print(f"import[{i}] type={type(im)}")
        f = get_fn(im, "_metadata")
        if f is not None:
            try:
                return str(f())
            except Exception as e:
                print(f"import[{i}] _metadata err:", e)
    # via vm_load_executable
    f = get_fn(mod, "vm_load_executable")
    if f is not None:
        try:
            exe = f()
            print("vm_load_executable ->", type(exe))
            mf = get_fn(exe, "_metadata") if hasattr(exe, "get_function") else None
            if mf is not None:
                return str(mf())
            # some executables expose .module
            if hasattr(exe, "module"):
                return extract_meta(exe.module)
        except Exception as e:
            print("vm_load_executable err:", e)
    return None


def main() -> None:
    label, path = sys.argv[1], sys.argv[2]
    print(f"======== {label}: {path} ========")
    mod = load_module(path)
    print("mod_type:", type(mod))
    print("dir_sample:", [x for x in dir(mod) if not x.startswith("_")][:40])

    meta = extract_meta(mod)
    if not meta:
        # strings fallback from binary via python (slow but ok)
        print("NO_METADATA_API — trying string scan of file")
        data = open(path, "rb").read()
        # printable C strings length >= 6
        strings = re.findall(rb"[ -~]{6,120}", data)
        decoded = [s.decode("ascii", "ignore") for s in strings]
        interesting = sorted({
            s for s in decoded
            if any(k in s.lower() for k in KEYS)
            and re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", s)
        })
        print("string_hits_count:", len(interesting))
        for s in interesting[:200]:
            print("  STR:", s)
        return

    print("metadata_chars:", len(meta))
    fns = sorted(set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]{2,})"', meta)))
    interesting = [x for x in fns if any(k in x.lower() for k in KEYS)]
    print("interesting_count:", len(interesting))
    for x in interesting:
        print("  FN:", x)

    # functions block
    m = re.search(r'"functions"\s*:\s*\{', meta)
    if m:
        # take a generous slice after functions
        slice_ = meta[m.start() : m.start() + 80000]
        keys = sorted(set(re.findall(r'"([A-Za-z_][A-Za-z0-9_]*)"\s*:', slice_)))
        top = [k for k in keys if any(x in k.lower() for x in (
            "decode", "embed", "prefill", "batch", "create", "softmax", "sample"
        ))]
        print("functions_like:", top)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: _so_meta_probe.py <label> <path.so>")
        sys.exit(2)
    main()
