"""Play one bundled blade-swipe effect per completed task."""

from pathlib import Path
from random import shuffle
import winsound


class TaskSounds:
    def __init__(self) -> None:
        self.sounds = sorted(Path(__file__).with_name("slice_sounds").glob("slice-*.wav"))
        self.pending = []
        self.last = None

    def complete(self) -> None:
        if not self.sounds:
            return
        if not self.pending:
            self.pending = self.sounds.copy()
            shuffle(self.pending)
            if len(self.pending) > 1 and self.pending[-1] == self.last:
                self.pending[0], self.pending[-1] = self.pending[-1], self.pending[0]
        self.last = self.pending.pop()
        try:
            winsound.PlaySound(str(self.last), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except RuntimeError:
            pass
