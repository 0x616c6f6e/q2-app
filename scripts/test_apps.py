"""Validate app identity, permissions, versioning, module bundling and repeatable archives."""

from pathlib import Path
import hashlib
import json
import tempfile
import shutil
import zipfile
from q2app import create, pack, manifest, VERSION, pack_factory

ROOT = Path(__file__).resolve().parents[1]
checks = 0


def check(value):
    global checks
    checks += 1
    assert value


with tempfile.TemporaryDirectory() as directory:
    tmp = Path(directory)
    for name in [
        "homepage",
        "settings",
        "device-info",
        "ui-demo",
        "key-demo",
        "network-test",
        "qrcode",
        "music-player",
    ]:
        source = ROOT / "apps" / name
        first = pack(source, tmp / (name + ".q2app"))
        second = pack(source, tmp / (name + ".q2app"))
        check(first == second)
        with zipfile.ZipFile(tmp / (name + ".q2app")) as z:
            check(z.testzip() is None)
            for path, digest in first["entries"].items():
                check(hashlib.sha256(z.read(path)).hexdigest() == digest)
                if path.startswith("assets/"):
                    check((tmp / (name + ".run") / path).read_bytes() == z.read(path))
            check(json.loads(z.read("manifest.json"))["id"] == first["id"])
    product = tmp / "product"
    shutil.copytree(ROOT / "apps", product / "apps")
    shutil.copyfile(ROOT / "factory.json", product / "factory.json")
    config = json.loads((product / "factory.json").read_text())
    built = pack_factory(product, tmp / "factory-dist")
    check(built["default_app"] == "homepage")
    check(len({x["id"] for x in built["apps"]}) == len(built["apps"]))
    for bad in [
        dict(config, format=True),
        dict(config, default_app="ui-demo"),
        dict(config, apps=config["apps"] + [config["apps"][0]]),
        dict(config, apps=[dict(config["apps"][0], factory=False), *config["apps"][1:]]),
        dict(config, apps=[dict(config["apps"][0], directory="../homepage"), *config["apps"][1:]]),
    ]:
        (product / "factory.json").write_text(json.dumps(bad))
        try:
            pack_factory(product, tmp / "bad-dist")
            check(False)
        except ValueError:
            check(True)
    project = tmp / "new"
    create(project, "Example")
    identity = manifest(project / "manifest.json")[0]["id"]
    check(all((project / "assets" / size).is_dir() for size in manifest(project / "manifest.json")[0]["supported_resolutions"]))
    check(pack(project, tmp / "new.q2app")["id"] == identity)
    try:
        create(project, "Replacement")
        check(False)
    except FileExistsError:
        check(manifest(project / "manifest.json")[0]["id"] == identity)
    original = json.loads((project / "manifest.json").read_text())
    # Regenerating a run directory must not leave removed assets visible to the runner.
    stale = tmp / "new.run/assets/stale.png"
    stale.parent.mkdir(exist_ok=True)
    stale.write_bytes(b"old")
    pack(project, tmp / "new.q2app")
    check(not stale.exists())
    oversized = project / "assets/large.png"
    oversized.write_bytes(b"x" * (256 * 1024 + 1))
    try:
        pack(project, tmp / "new.q2app")
        check(False)
    except ValueError:
        check(True)
    oversized.unlink()
    # File-count quota permits icon sets but still rejects excess tiny assets.
    for index in range(30):
        (project / "assets" / f"quota-{index}.txt").write_text("x")
    check(len(pack(project, tmp / "new.q2app")["entries"]) == 32)
    extra = project / "assets/quota-extra.txt"
    extra.write_text("x")
    try:
        pack(project, tmp / "new.q2app")
        check(False)
    except ValueError:
        check(True)
    for asset in (project / "assets").glob("quota-*.txt"):
        asset.unlink()
    # Legacy manifests remain valid; canonical resolution declarations and nested assets round-trip.
    legacy = dict(original)
    legacy.pop("supported_resolutions", None)
    (project / "manifest.json").write_text(json.dumps(legacy))
    check("supported_resolutions" not in manifest(project / "manifest.json")[0])
    valid = dict(original, supported_resolutions=["64x64", "1024x1024", "502x410"])
    (project / "manifest.json").write_text(json.dumps(valid))
    check(manifest(project / "manifest.json")[0]["supported_resolutions"] == valid["supported_resolutions"])
    nested = project / "assets/502x410/icon.png"
    nested.parent.mkdir(exist_ok=True)
    nested.write_bytes(b"package bytes")
    check("assets/502x410/icon.png" in pack(project, tmp / "variant.q2app")["entries"])
    check((tmp / "variant.run/assets/502x410/icon.png").read_bytes() == b"package bytes")
    for values in [None, "502x410", [], [123], [True], ["502X410"], ["0502x410"],
                   ["63x410"], ["1025x410"], ["502x410\n"], ["502x410", "502x410"],
                   ["../../secret"], ["999999999999x410"], [f"{64 + i}x64" for i in range(17)]]:
        (project / "manifest.json").write_text(json.dumps(dict(original, supported_resolutions=values)))
        try:
            manifest(project / "manifest.json")
            check(False)
        except ValueError:
            check(True)
    for replacement in [
        dict(original, version="01.0.0"),
        dict(original, id="not-a-uuid"),
        dict(original, capabilities={"required": ["system.info"], "optional": ["system.info"]}),
        dict(original, capabilities={"required": ["system.info"], "optional": [], "scopes": {}}),
        dict(original, api=True),
        dict(original, resources={"lua_heap_kib": True}),
        dict(original, description=123),
        dict(original, icon="assets/../secret.png"),
    ]:
        (project / "manifest.json").write_text(json.dumps(replacement))
        try:
            manifest(project / "manifest.json")
            check(False)
        except ValueError:
            check(True)
    for version in ["0.0.0", "1.2.3-rc.1+test.5", "1.0.0-0", "1.0.0+001"]:
        check(VERSION.fullmatch(version) is not None)
    for version in ["1.2", "v1.2.3", "01.2.3", "1.2.3-01", "1.2.3+", "1.2.3-a..b"]:
        check(VERSION.fullmatch(version) is None)
print(f"PASS: {checks} Q2-App checks")
