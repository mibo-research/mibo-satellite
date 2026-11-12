"""Public reproducibility audit: exact approved snapshot; all provider sockets denied."""
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath
import socket
import sys
import tempfile
import zipfile


def deny(*args, **kwargs):
    raise AssertionError("Publication CI cannot contact models or resolve credentials")


def main():
    root = Path(__file__).resolve().parent
    package = root / "MIBO-Education-W01-v1.1-registration-preparation-DRAFT-20261112.zip"
    assert sha256(package.read_bytes()).hexdigest() == "4854f94fb63fe7d63a7d318a45372c9daeae718c696b724239c76f2c17398da3"
    socket.socket.connect = socket.socket.connect_ex = socket.socket.sendto = deny
    socket.create_connection = socket.getaddrinfo = socket.gethostbyname = deny
    for key in list(os.environ):
        if key.endswith(("_KEY", "_TOKEN")) or "SECRET" in key or "CREDENTIAL" in key:
            os.environ.pop(key, None)
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    sys.dont_write_bytecode = True
    # A dedicated short temporary path also supports Windows' legacy path limit.
    # Only the validated per-audit child is automatically cleaned up.
    parent = Path(tempfile.gettempdir()) / "miboe-v11-publication-audit"
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="snapshot-", dir=parent) as temporary:
        temporary = Path(temporary).resolve()
        assert temporary.is_relative_to(parent.resolve()), "Cleanup must stay in the dedicated test directory"
        with zipfile.ZipFile(package) as archive:
            assert archive.testzip() is None
            names = archive.namelist()
            manifest = json.loads(archive.read("PACKAGE-MANIFEST.json"))
            assert len(names) == 369 and len(set(names)) == len(names)
            assert set(names) == set(manifest) | {"PACKAGE-MANIFEST.json"}
            for name in names:
                path = PurePosixPath(name)
                assert not path.is_absolute() and ".." not in path.parts
                assert "/L0_raw/" not in name and "/.env" not in name and "/governance/records/" not in name
                if name in manifest:
                    raw = archive.read(name)
                    assert len(raw) == manifest[name]["bytes"]
                    assert sha256(raw).hexdigest() == manifest[name]["sha256"]
            archive.extractall(temporary)
        education = temporary / "mibo-education"
        sys.path[:0] = [str(education / "src"), str(education / "tests")]
        from miboe import w01_v11
        plan = w01_v11.load_plan(education)
        assert plan["lock"]["release_sha256"] == "64c257ffaf13e447dca643275fa46e8dcdf7beef9ab100a4ed1fb7fc26438f36"
        import pytest
        code = pytest.main([str(education / "tests/test_w01_v11.py"), "-q", "-p", "no:cacheprovider", "-c", str(education / "pyproject.toml")])
        assert code == 0, "Frozen W01 offline suite failed; never alter the adopted snapshot to manufacture passage"
    print(json.dumps({"approved_package_files": 369, "frozen_release_verified": True,
        "provider_sockets_denied": True, "model_API_calls": 0, "Core_or_other_waves_executed": False}))


if __name__ == "__main__":
    main()
