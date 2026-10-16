"""Exercise production boot selection, OnFailure and activation guard using spare units only."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from froeling_bridge.production import ProductionSystem, Production, LIVE, GUARD, PREVIEW, P4D, TEST, TIMER, ROLLBACK

FALLBACK = 'froeling-bridge-fallback.service'


class Spares(ProductionSystem):
    def __init__(self, base):
        self.mapping = {name: base + '-' + str(i) + ('.timer' if name.endswith('.timer') else '.service') for i, name in enumerate((LIVE, GUARD, PREVIEW, P4D, TEST, TIMER, ROLLBACK, FALLBACK))}

    def run(self, command, **kwargs):
        assert command[0] == '/usr/bin/systemctl'
        mapped = [self.mapping.get(arg, arg) for arg in command]
        assert not set(mapped) & set(self.mapping)
        mapped[0] = "/bin/systemctl"
        if mapped[1] in ('enable', 'disable'):
            mapped.insert(2, '--runtime')
        return super().run(mapped, **kwargs)

    def preflight_live(self):
        assert self.active(P4D)

    def port_free(self):
        pass

    def device_free(self):
        return True

    def live_ready(self, after):
        assert self.active(LIVE)
        return dict(successful_cycles=2)

    def resumed_recording(self, after):
        return self.active(P4D)


if len(sys.argv) == 4 and sys.argv[1] == 'rollback':
    Production(Spares(sys.argv[2]), Path(sys.argv[3])).rollback()
    raise SystemExit(0)
if sys.argv[1:] != ['--run-local-spares'] or os.geteuid() != 0:
    raise SystemExit('Run with sudo and --run-local-spares; no real heating services or databases are accessed.')
base = 'froeling-production-spare-' + uuid.uuid4().hex[:10]
system = Spares(base)
with tempfile.TemporaryDirectory(prefix=base) as temporary:
    state = Path(temporary)
    created = []
    try:
        originals = {
            P4D: '[Service]\nExecStart=/bin/sleep infinity\n[Install]\nWantedBy=multi-user.target\n',
            LIVE: '[Unit]\nAfter=' + P4D + '\nConflicts=' + P4D + '\nOnFailure=' + FALLBACK + '\n[Service]\nType=exec\nExecStart=/bin/sleep infinity\nRestart=no\n[Install]\nWantedBy=multi-user.target\n',
            FALLBACK: '[Unit]\nAfter=' + LIVE + '\n[Service]\nType=oneshot\nExecStart=' + str(ROOT / '.venv/bin/python') + ' -I ' + str(Path(__file__).resolve()) + ' rollback ' + base + ' ' + str(state) + '\nRestart=on-failure\nRestartSec=1\n',
            GUARD: '[Timer]\nOnActiveSec=2s\nAccuracySec=100ms\nUnit=' + FALLBACK + '\n',
        }
        for unused in (PREVIEW, TEST, TIMER, ROLLBACK):
            originals[unused] = ("[Timer]\nOnActiveSec=1h\nUnit=" + FALLBACK + "\n") if unused.endswith(".timer") else "[Service]\nExecStart=/bin/sleep infinity\n"
        for unit, text in originals.items():
            for original, spare in system.mapping.items():
                text = text.replace(original, spare)
            path = Path('/run/systemd/system') / system.mapping[unit]
            assert not path.exists()
            path.write_text(text)
            created.append(path)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        system.enable(P4D)
        system.start(P4D)
        control = Production(system, state)
        assert control.start()['live_active']
        assert system.enabled(LIVE) and not system.enabled(P4D)
        system.run(['/usr/bin/systemctl', 'kill', '--signal=SIGKILL', LIVE])
        for _ in range(100):
            if system.active(P4D) and not system.active(LIVE) and system.enabled(P4D) and not system.enabled(LIVE):
                break
            time.sleep(.1)
        else:
            raise AssertionError('OnFailure did not restore original and boot choice')
        print('PASS real systemd: production SIGKILL restores original and its boot selection.')
        # A separately armed guard works with no activation process remaining.
        system.stop(P4D)
        system.disable(P4D)
        system.enable(LIVE)
        system.start(LIVE)
        system.start(GUARD)
        for _ in range(100):
            if system.active(P4D) and not system.active(LIVE) and system.enabled(P4D):
                break
            time.sleep(.1)
        else:
            raise AssertionError('independent guard did not restore original')
        print('PASS real systemd: independent activation deadline restores original.')
    finally:
        for name in system.mapping.values():
            subprocess.run(['systemctl', 'stop', name], capture_output=True)
            subprocess.run(['systemctl', 'disable', '--runtime', name], capture_output=True)
        for path in created:
            path.unlink(missing_ok=True)
        subprocess.run(['systemctl', 'daemon-reload'], check=True)
        for name in system.mapping.values():
            subprocess.run(['systemctl', 'reset-failed', name], capture_output=True)
