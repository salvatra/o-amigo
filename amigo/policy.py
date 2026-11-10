"""Capabilities enforced outside prompts and generated text."""
from pathlib import Path
import os
import stat

class Denied(ValueError):
    pass

class Policy:
    def __init__(self, roots, protected=()):
        self.roots = tuple(Path(p).absolute().resolve() for p in roots)
        home = Path.home()
        self.protected = tuple(Path(p).absolute().resolve() for p in [
            home/'.config', home/'.local', home/'.ssh', home/'.gnupg', home/'.codex',
            home/'.mozilla', home/'.pki', home/'.aws', home/'.azure', home/'.kube',
            home/'.password-store', home/'.bashrc', home/'.zshrc', home/'.zshenv',
            home/'.profile', home/'.bash_profile', home/'.netrc', home/'.npmrc',
            Path(__file__).resolve().parents[1], *protected])

    def path(self, value, *, exists=True):
        path = Path(value).expanduser().absolute()
        if '..' in path.parts:
            raise Denied('Parent traversal is not permitted')
        # Reject symlinks in every component, including a dangling final link.
        for part in (path, *path.parents):
            if part.is_symlink():
                raise Denied('Symbolic links are not permitted')
        real = path.resolve(strict=exists)
        if not any(real == root or root in real.parents for root in self.roots):
            raise Denied('Path is outside authorized folders')
        if any(real == p or p in real.parents for p in self.protected):
            raise Denied('Protected path')
        if any(p in ('.git', '.obsidian', '.env', '__pycache__') or p.startswith('.env.') for p in real.parts):
            raise Denied('Protected metadata')
        if exists and not (real.is_file() or real.is_dir()):
            raise Denied('Devices and special files are not permitted')
        if exists and real.is_file() and real.stat().st_nlink > 1:
            raise Denied('Hard-linked files require explicit handling')
        return real

    def open_read(self, value):
        path = self.path(value)
        # Walk directory descriptors to reject component swaps and symlink races.
        fd = os.open('/', os.O_PATH | os.O_DIRECTORY)
        try:
            for component in path.parts[1:-1]:
                nxt = os.open(component, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                os.close(fd); fd = nxt
            result = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
            mode = os.fstat(result)
            if not stat.S_ISREG(mode.st_mode) or mode.st_nlink > 1:
                os.close(result)
                raise Denied('Not an independent regular file')
            return os.fdopen(result, 'rb')
        finally:
            os.close(fd)
