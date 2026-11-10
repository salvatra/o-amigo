"""Fixed executables, isolated filesystem, no network or inherited credentials."""
import os
import subprocess
from pathlib import Path
from .policy import Denied

COMMANDS = {'man': '/usr/bin/man', 'pdf_info': '/usr/bin/pdfinfo',
            'pdf_text': '/usr/bin/pdftotext', 'pdf_pages': '/usr/bin/qpdf'}

class Sandbox:
    def run(self, command, args, inputs=(), output=None, timeout=30):
        if command not in COMMANDS:
            raise Denied('Unknown executable capability')
        argv = ['/usr/bin/bwrap', '--unshare-all', '--die-with-parent', '--new-session',
                '--cap-drop', 'ALL', '--ro-bind', '/usr', '/usr',
                '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib',
                '--symlink', 'usr/lib', '/lib64', '--proc', '/proc', '--dev', '/dev',
                '--tmpfs', '/tmp', '--dir', '/home', '--dir', '/input',
                '--clearenv', '--setenv', 'PATH', '/usr/bin', '--setenv', 'HOME', '/tmp',
                '--setenv', 'LANG', 'C.UTF-8', '--setenv', 'PAGER', 'cat',
                '--setenv', 'MANPAGER', 'cat', '--setenv', 'MAN_DISABLE_SECCOMP', '0']
        # Only caller-owned staged inputs, never arbitrary host paths from a tool request.
        for index, path in enumerate(inputs):
            argv += ['--ro-bind', str(Path(path).resolve()), f'/input/{index}']
        if output:
            argv += ['--bind', str(Path(output).resolve()), '/output']
        if command == 'man':
            argv += ['--dir', '/etc', '--ro-bind', '/etc/man_db.conf', '/etc/man_db.conf']
        result = subprocess.run(argv + ['--', COMMANDS[command], *args],
                                env={'PATH':'/usr/bin'}, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError(f'{command} failed ({result.returncode}): ' + result.stderr.decode(errors='replace')[:1000])
        return result.stdout.decode(errors='replace')[:64000]
