from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "addons" / "vaillant-ebus-control"


def test_pin_matches_dockerfile():
    lock = (ROOT / "build/ebusd-source.lock").read_text()
    sha = re.search(r"^EBUSD_COMMIT=([0-9a-f]{40})$", lock, re.M).group(1)
    docker = (APP / "Dockerfile").read_text()
    assert f"ARG EBUSD_COMMIT={sha}" in docker
    assert "git checkout --detach" in docker
    assert "github.com/Alec-99/ebusd.git" in docker
    assert "--target ebusd" in docker


def test_install_is_readonly_by_design():
    config = (APP / "config.yaml").read_text()
    launcher = (APP / "app/run_ebusd.py").read_text()
    assert "enable_bus: false" in config
    assert '"--readonly"' in launcher
    assert "enable_control" not in config
    assert "--accesslevel=*" not in launcher
    assert "SetMode" not in (APP / "app/vaillant_control/ebusd_client.py").read_text().split("ALLOWED = ", 1)[1].split("\n",1)[0]


def test_s6_service_files_and_order():
    root = APP / "rootfs/etc/s6-overlay"
    for name in ("ebusd", "vaillant-controller", "vaillant-webui"):
        assert (root / "s6-rc.d" / name / "type").read_text().strip() == "longrun"
        assert (root / "s6-rc.d" / name / "run").read_text().startswith("#!/")
        assert (root / "user-bundles.d/user/contents.d" / name).exists()
    assert (root / "s6-rc.d/ebusd/dependencies.d/base").exists()
    assert (root / "s6-rc.d/vaillant-controller/dependencies.d/ebusd").exists()
    assert (root / "s6-rc.d/vaillant-webui/dependencies.d/vaillant-controller").exists()
