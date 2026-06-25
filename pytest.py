from __future__ import annotations

import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path


def _run_test(function) -> tuple[bool, str | None]:
    kwargs = {}
    cleanup = None
    if "tmp_path" in inspect.signature(function).parameters:
        cleanup = tempfile.TemporaryDirectory()
        kwargs["tmp_path"] = Path(cleanup.name)
    try:
        function(**kwargs)
        return True, None
    except Exception as exc:  # pragma: no cover - local fallback runner
        return False, repr(exc)
    finally:
        if cleanup:
            cleanup.cleanup()


def main() -> int:
    test_files = sorted(Path("tests").glob("test_*.py"))
    passed = 0
    failed: list[str] = []
    for file_path in test_files:
        module_name = file_path.with_suffix("").as_posix().replace("/", ".")
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if not spec or not spec.loader:
            failed.append(f"{file_path}: could not load")
            continue
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        for name, value in inspect.getmembers(module, inspect.isfunction):
            if not name.startswith("test_"):
                continue
            ok, error = _run_test(value)
            if ok:
                passed += 1
            else:
                failed.append(f"{file_path}::{name} - {error}")

    if failed:
        print("local pytest fallback failures:")
        for failure in failed:
            print(f"  {failure}")
        print(f"{passed} passed, {len(failed)} failed")
        return 1
    print(f"{passed} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

