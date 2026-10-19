"""
Een slot op een ronde: er loopt nooit twee keer tegelijk hetzelfde werk op één ronde.

Twee keer tegelijk inplannen zou elke reel twee keer bij Zernio zetten; twee keer tegelijk
maken zou half gemaakte reels over elkaar heen schrijven. Het slot is een bestand met het
procesnummer erin. Bestaat dat proces niet meer (gestopt, Mac opnieuw gestart), dan telt
het slot niet meer.
"""

import os
from contextlib import contextmanager
from pathlib import Path


class SlotFout(Exception):
    pass


def _leeft(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def slot(map_, naam):
    pad = Path(map_) / f".{naam}.slot"
    for _ in range(2):
        try:
            fd = os.open(pad, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(str(os.getpid()))
            break
        except FileExistsError:
            try:
                pid = int(pad.read_text().strip() or 0)
            except (OSError, ValueError):
                pid = 0
            if pid and _leeft(pid):
                raise SlotFout(f"Er loopt al iets voor deze ronde (proces {pid}). Wacht tot dat klaar is en probeer het dan opnieuw.")
            pad.unlink(missing_ok=True)   # het slot van een proces dat niet meer bestaat
    else:
        raise SlotFout("Het slot op deze ronde lukt niet. Probeer het opnieuw.")
    try:
        yield
    finally:
        pad.unlink(missing_ok=True)
