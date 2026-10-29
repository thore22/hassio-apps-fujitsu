"""Offline regression checks; no host network or audio settings are changed."""

import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "airplay_2_multiroom_audio"
sys.path.insert(0, str(ADDON))
import airplay_interface


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.options = Path(self.tmp.name) / "options.json"
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.index = patch.object(airplay_interface.socket, "if_nametoindex", return_value=2).start()
        self.addCleanup(patch.stopall)

    def test_fujitsu_default(self):
        self.assertEqual(airplay_interface.resolve_interface(self.options), "enp1s0")
        self.index.assert_called_with("enp1s0")

    def test_option_is_reread_after_restart(self):
        for interface in ("enp1s0", "eth0"):
            self.options.write_text(json.dumps({"airplay_interface": interface}))
            self.assertEqual(airplay_interface.resolve_interface(self.options), interface)

    def test_existing_environment_override(self):
        self.options.write_text('{"airplay_interface": "enp1s0"}')
        os.environ["AIRPLAY_INTERFACE"] = "eth0"
        self.assertEqual(airplay_interface.resolve_interface(self.options), "eth0")

    def test_missing_interface_is_actionable(self):
        self.index.side_effect = OSError("not found")
        with patch.object(airplay_interface.socket, "if_nameindex", return_value=[(1, "lo"), (2, "eth0")]):
            with self.assertRaisesRegex(ValueError, "does not exist; available: lo, eth0"):
                airplay_interface.resolve_interface(self.options)

    def test_unsafe_or_empty_names_are_rejected(self):
        for interface in ("", "lo", 'eth0\";', "eth0\n", "a" * 16, None, 1, "../eth0"):
            with self.subTest(interface=interface):
                self.options.write_text(json.dumps({"airplay_interface": interface}))
                with self.assertRaises(ValueError):
                    airplay_interface.resolve_interface(self.options)

    def test_corrupt_options_fail_instead_of_using_wrong_default(self):
        self.options.write_text("{")
        with self.assertRaises(ValueError):
            airplay_interface.resolve_interface(self.options)


class GeneratedConfigTests(unittest.TestCase):
    def test_cast_configs_are_rewritten_with_selected_interface(self):
        # Import the real manager without requiring Cast hardware/dependencies.
        zc = types.ModuleType("zeroconf")
        zc.ServiceListener = object
        with patch.dict(sys.modules, {"pychromecast": types.ModuleType("pychromecast"), "zeroconf": zc}):
            spec = importlib.util.spec_from_file_location("manager_test", ADDON / "cast_bridge_manager.py")
            manager = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(manager)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            def fake_spawn(*args, **kwargs):
                # Real Popen duplicates the descriptor; our mock must not keep
                # the parent's file open when the temporary directory is removed.
                kwargs["stdout"].close()
                return Mock()
            with patch.multiple(manager, CONFIG_DIR=folder, LOG_DIR=folder, PIPE_DIR=folder), \
                    patch.object(manager.subprocess, "Popen", side_effect=fake_spawn), \
                    patch.object(manager.os.path, "exists", return_value=True):
                for interface in ("enp1s0", "eth0"):
                    manager.AIRPLAY_INTERFACE = interface
                    manager.start_shairport("Schlafzimmer_speaker", str(folder / "speaker.pipe"), 5150, 6800)
                    text = (folder / "Schlafzimmer_speaker-ap2.conf").read_text()
                    self.assertIn(f'interface = "{interface}";', text)
                    self.assertIn('output_backend = "pipe";', text)
                    self.assertIn('mdns_backend = "avahi";', text)

    @unittest.skipUnless(os.name == "posix", "Full service generation uses Linux shell tools; run CI for this check")
    def test_shell_generates_avahi_sink_and_cast_services_each_start(self):
        bash = shutil.which("bash")
        self.assertIsNotNone(bash)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tools = root / "bin"
            tools.mkdir()
            (root / "tmp").mkdir()
            scripts = {
                "pactl": 'if [ "$*" = "list sinks short" ]; then echo "1 Test_Sink module-remap-sink"; fi\n',
                "ss": "exit 0\n",
                "flock": "exit 0\n",
                "python3": 'printf "%s\\n" "$TEST_INTERFACE"\n',
            }
            for name, body in scripts.items():
                path = tools / name
                path.write_text("#!/bin/sh\n" + body)
                path.chmod(0o755)
            script = (ADDON / "generate_airplay2_services.sh").read_text()
            # Replace in one pass: root itself can start with /tmp/.
            script = re.sub(r"/(?:etc|config|tmp)/", lambda match: str(root) + match.group(), script)
            generated = root / "generate.sh"
            generated.write_text(script)
            env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ["PATH"])
            for interface in ("enp1s0", "eth0"):
                # A container restart recreates /etc; persistent /config remains.
                shutil.rmtree(root / "etc", ignore_errors=True)
                env["TEST_INTERFACE"] = interface
                result = subprocess.run([bash, str(generated)], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f"Using LAN interface {interface} (exists)", result.stdout)
                base = root / "etc/s6-overlay/s6-rc.d"
                avahi = (base / "airplay2-avahi/run").read_text()
                self.assertIn(f'awk -v iface="{interface}"', avahi)
                self.assertIn('export AIRPLAY_INTERFACE="' + interface + '"', (base / "airplay2-castbridge-manager/run").read_text())
                conf = root / "config/shairport-sync/config/Test_Sink-ap2.conf"
                self.assertIn(f'interface = "{interface}";', conf.read_text())
                self.assertIn("exec nqptp", (base / "airplay2-nqptp/run").read_text())
                for run in base.glob("*/run"):
                    subprocess.run([bash, "-n", str(run)], check=True)
                # Exercise Avahi's generated awk config update on a fixture only.
                avahi_conf = root / "etc/avahi/avahi-daemon.conf"
                avahi_conf.parent.mkdir(parents=True)
                avahi_conf.write_text("[server]\nallow-interfaces=old\nhost-name=old\n[publish]\npublish-addresses=yes\n")
                update = avahi[avahi.index("awk -v"):avahi.index("exec avahi-daemon")]
                subprocess.run([bash, "-c", update], check=True)
                self.assertEqual(avahi_conf.read_text().count("allow-interfaces="), 1)
                self.assertIn("allow-interfaces=" + interface, avahi_conf.read_text())


class PackagingTests(unittest.TestCase):
    def test_home_assistant_metadata_and_build_context(self):
        import yaml
        config = yaml.safe_load((ADDON / "config.yaml").read_text())
        self.assertIsInstance(config["version"], str)
        self.assertEqual(config["options"], {"airplay_interface": "enp1s0"})
        self.assertEqual(config["schema"], {"airplay_interface": "str"})
        self.assertEqual(config["slug"], "airplay_2_multiroom_audio_fujitsu")
        self.assertIn("amd64", config["arch"])
        self.assertTrue(config["host_network"])
        self.assertFalse(config["init"])
        self.assertIn("addon_config:rw", config["map"])
        self.assertNotIn("image", config)  # Supervisor builds this fork's Dockerfile.
        docker = (ADDON / "Dockerfile").read_text()
        for line in docker.splitlines():
            if line.startswith("COPY ") and not line.startswith("COPY --from="):
                self.assertTrue((ADDON / shlex.split(line)[1]).is_file(), line)
        for flag in ("--with-airplay-2", "--with-avahi", "--with-pipe", "--with-pulseaudio"):
            self.assertIn(flag, docker)
        repo = yaml.safe_load((ROOT / "repository.yaml").read_text())
        self.assertEqual(repo["url"], "https://github.com/thore22/hassio-apps-fujitsu")
        for path in ADDON.glob("*"):
            if path.suffix in (".py", ".sh", ".yaml"):
                self.assertNotIn("enp5s0", path.read_text(), str(path))


if __name__ == "__main__":
    unittest.main()

