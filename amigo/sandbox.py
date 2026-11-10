"""Fixed executables, isolated filesystem, no network or inherited credentials."""
import os
import subprocess
import selectors
import time
from pathlib import Path
from .policy import Denied
from .transactions import Cancelled

COMMANDS = {'man': '/usr/bin/man', 'pdf_info': '/usr/bin/pdfinfo',
            'pdf_text': '/usr/bin/pdftotext', 'pdf_pages': '/usr/bin/qpdf', 'archive':'/usr/bin/python'}

class Sandbox:
    def run(self, command, args, inputs=(), output=None, timeout=30, cancel=None):
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
        if command == 'archive':
            argv += ['--ro-bind',str(Path(__file__).with_name('archive_worker.py').resolve()),'/worker.py']
            args=['-I','/worker.py']
        # Limits are installed by a fixed executable, never via a shell/preexec_fn.
        argv += ['--', '/usr/bin/prlimit', '--as=2147483648', '--cpu=60',
                 '--fsize=2147483648', '--nofile=128', '--', COMMANDS[command], *args]
        process = subprocess.Popen(argv, env={'PATH':'/usr/bin'}, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        selector=selectors.DefaultSelector();buffers={'out':bytearray(),'err':bytearray()}
        selector.register(process.stdout,selectors.EVENT_READ,'out')
        selector.register(process.stderr,selectors.EVENT_READ,'err')
        deadline=time.monotonic()+timeout;seen=0
        try:
            while selector.get_map():
                if cancel and cancel.is_set():raise Cancelled('External operation cancelled')
                if time.monotonic()>deadline:raise TimeoutError('External operation timed out')
                for key,_ in selector.select(min(.1,max(0,deadline-time.monotonic()))):
                    data=os.read(key.fileobj.fileno(),16384)
                    if not data:selector.unregister(key.fileobj);continue
                    seen+=len(data)
                    if seen>8*1024**2:raise RuntimeError('External output limit exceeded')
                    buffer=buffers[key.data];buffer.extend(data[:max(0,64000-len(buffer))])
            code=process.wait(timeout=max(.1,deadline-time.monotonic()))
            if code:
                raise RuntimeError(f'{command} failed ({code}): '+buffers['err'].decode(errors='replace')[:1000])
            return buffers['out'].decode(errors='replace')
        finally:
            selector.close()
            if process.poll() is None:process.kill()
            process.wait();process.stdout.close();process.stderr.close()
