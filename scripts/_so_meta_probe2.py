from tvm.runtime import load_module
import re
mod = load_module("/model/gemma-cpu.so")
print("mod_type", type(mod))
print("dir", [x for x in dir(mod) if not x.startswith("__")])
# try imports
try:
    imps = mod.imports
    print("imports attr", imps)
except Exception as e:
    print("imports err", e)
try:
    print("imported_modules", mod.imported_modules)
except Exception as e:
    print("imported_modules err", e)
for name in ["vm_load_executable", "get_function_metadata", "_lookup_linked_param", "main", "_metadata"]:
    try:
        f = mod.get_function(name, allow_missing=True)
        print("fn", name, f)
    except TypeError:
        try:
            f = mod.get_function(name)
            print("fn", name, "found")
        except Exception as e:
            print("fn", name, "missing", type(e).__name__)
# After vm_load_executable
f = None
try:
    f = mod.get_function("vm_load_executable", allow_missing=True)
except TypeError:
    try:
        f = mod.get_function("vm_load_executable")
    except Exception:
        f = None
if f is not None:
    vm = f()
    print("vm", type(vm), [x for x in dir(vm) if not x.startswith("__")][:60])
    # try metadata
    for attr in ["_metadata", "metadata", "function_names", "list_functions"]:
        if hasattr(vm, attr):
            print("vm has", attr)
    try:
        meta = vm["_metadata"] if False else None
    except Exception as e:
        print("vm index err", e)
    # Executable API
    try:
        from tvm.runtime import vm as tvmvm
        print("tvmvm", dir(tvmvm)[:40])
    except Exception as e:
        print("no tvmvm", e)
