import os
import time
import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """GNU Radio sink block for recording raw complex64 I/Q samples."""

    IDLE = "IDLE"
    RECORDING = "RECORDING"
    WAIT = "WAIT"

    def __init__(self, team='Team-00', lab=1, fc=100e6, fs=2.6e6,
                 gain=0.0, record=False, max_seconds=5.0, folder='.'):
        gr.sync_block.__init__(self,
                               name='SDR Lab IQ Recorder',
                               in_sig=[np.complex64],
                               out_sig=None)

        # Keep the parameter names exactly as declared: GNU Radio updates these
        # attributes when the corresponding block parameters change at runtime.
        self.team = team
        self.lab = lab
        self.fc = fc
        self.fs = fs
        self.gain = gain
        self.record = record
        self.max_seconds = max_seconds
        self.folder = folder

        # Internal state
        self._state = self.IDLE
        self._file = None
        self._written = 0
        self._n_max = 0
        self._start_settings = None

    def _open_file(self):
        """Create a new recording file and initialize its per-file counters."""
        os.makedirs(self.folder, exist_ok=True)

        self._n_max = int(np.floor(float(self.max_seconds) * float(self.fs)))
        # Round before converting to int, as required for floating-point
        # frequency/sample-rate values supplied by GNU Radio.
        fc_hz = int(round(float(self.fc)))
        fs_hz = int(round(float(self.fs)))
        gain_db = float(self.gain)

        # The required timestamp has one-second resolution. If a recording
        # with the same parameters already used this exact name in this second,
        # wait for the next timestamp rather than silently overwriting it.
        while True:
            timestamp = time.strftime('%Y%m%dT%H%M%S')
            filename = (
                f"{self.team}_lab{int(self.lab):02d}_"
                f"{fc_hz}_{fs_hz}_{gain_db:.1f}_{timestamp}.cf32"
            )
            filepath = os.path.join(self.folder, filename)
            if not os.path.exists(filepath):
                break
            time.sleep(0.05)

        self._file = open(filepath, 'wb')
        self._written = 0
        self._start_settings = (float(self.fc), float(self.fs), float(self.gain))

        print(f"[REC] start {filename}")

    def _close_file(self, reason):
        """Close the active file and print a summary of the recording."""
        if self._file is None:
            return

        # Use the sample rate captured when this file was opened. The live
        # parameter may already have changed when this helper is called.
        start_fs = self._start_settings[1]
        duration = (self._written / start_fs) if start_fs > 0 else 0.0

        self._file.close()
        self._file = None
        print(f"[REC] stop  {self._written} samples = {duration:.2f} s ({reason})")

    def work(self, input_items, output_items):
        x = input_items[0]

        if self._state == self.IDLE:
            if self.record:
                # Guard: a recording shorter than one sample makes no sense.
                # Go to WAIT so the message is printed once, not on every call.
                if float(self.max_seconds) * float(self.fs) < 1:
                    print("[REC] error: max_seconds * fs < 1 sample, "
                          "nothing to record")
                    self._state = self.WAIT
                    return len(x)

                # Guard: if the folder/file cannot be created, report it and
                # keep the flowgraph (spectrum displays) running. WAIT means
                # the next attempt happens only after Record is re-ticked.
                try:
                    self._open_file()
                except OSError as e:
                    print(f"[REC] error: cannot open file ({e})")
                    self._file = None
                    self._state = self.WAIT
                    return len(x)

                self._state = self.RECORDING

                # The first input batch must also be recorded.
                k = min(len(x), self._n_max - self._written)
                if k > 0:
                    x[:k].tofile(self._file)
                    self._written += k

                if self._written >= self._n_max:
                    self._close_file('max_seconds reached')
                    self._state = self.WAIT

        elif self._state == self.RECORDING:
            # Check conditions in the exact priority order from the lab spec.
            if not self.record:
                self._close_file('record off')
                self._state = self.IDLE

            elif ((float(self.fc), float(self.fs), float(self.gain))
                  != self._start_settings):
                self._close_file('settings changed')
                self._state = self.WAIT

            else:
                remaining = self._n_max - self._written
                k = min(len(x), remaining)
                if k > 0:
                    x[:k].tofile(self._file)
                    self._written += k

                if self._written >= self._n_max:
                    self._close_file('max_seconds reached')
                    self._state = self.WAIT

        elif self._state == self.WAIT:
            if not self.record:
                self._state = self.IDLE
            # While record remains True, do nothing. This prevents a second
            # file from starting until the user unchecks and checks Record.

        return len(x)

    def stop(self):
        if self._file is not None:
            self._close_file('flowgraph stopped')
        return True
