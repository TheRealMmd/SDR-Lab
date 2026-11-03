
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from gnuradio import gr


class blk(gr.sync_block):
    """SDR Lab IQ Recorder"""

    def __init__(
        self,
        fc=945e6,
        fs=2.6e6,
        gain=10.0,
        record=False,
        max_seconds=10.0,
    ):
        gr.sync_block.__init__(
            self,
            name="SDR Lab IQ Recorder",
            in_sig=[np.complex64],
            out_sig=[]
        )

        # Parameters controlled by GRC
        self.fc = fc
        self.fs = fs
        self.gain = gain
        self.record = record
        self.max_seconds = max_seconds

        # Recording state
        self._file = None
        self._path = None
        self._samples_written = 0
        self._target_samples = 0
        self._armed = True
        self._metadata = None

    def _start_recording(self):
        fs = float(self.fs)
        duration = float(self.max_seconds)

        if fs <= 0 or duration <= 0:
            raise ValueError(
                "fs and max_seconds must be positive"
            )

        folder = Path.home() / "SDR_Lab_Recordings"
        folder.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S_%f"
        )
        self._path = folder / f"iq_{timestamp}.c64"

        self._file = open(self._path, "wb")
        self._samples_written = 0
        self._target_samples = max(
            1, int(fs * duration)
        )

        self._metadata = {
            "center_frequency_hz": float(self.fc),
            "sample_rate_hz": fs,
            "rx_gain_db": float(self.gain),
            "max_seconds": duration,
            "data_type": "complex64",
            "started_utc": datetime.now(
                timezone.utc
            ).isoformat(),
        }

        print("Recording started:", self._path)

    def _stop_recording(self, reason):
        if self._file is None:
            return

        self._file.close()
        self._file = None

        self._metadata["samples_written"] = (
            self._samples_written
        )
        self._metadata["recorded_seconds"] = (
            self._samples_written
            / self._metadata["sample_rate_hz"]
        )
        self._metadata["stop_reason"] = reason

        metadata_path = self._path.with_suffix(
            ".json"
        )

        with open(
            metadata_path, "w", encoding="utf-8"
        ) as f:
            json.dump(self._metadata, f, indent=2)

        print("Recording saved:", self._path)

    def work(self, input_items, output_items):
        samples = input_items[0]
        n = len(samples)

        # Checkbox disabled
        if not bool(self.record):
            if self._file is not None:
                self._stop_recording("User stopped")

            self._armed = True
            return n

        # Start only once per checkbox activation
        if self._armed and self._file is None:
            self._start_recording()

        if self._file is not None:
            remaining = (
                self._target_samples
                - self._samples_written
            )
            count = min(n, remaining)

            if count > 0:
                self._file.write(
                    samples[:count].tobytes()
                )
                self._samples_written += count

            if (
                self._samples_written
                >= self._target_samples
            ):
                self._stop_recording(
                    "Maximum duration reached"
                )
                self._armed = False

        return n

    def stop(self):
        self._stop_recording("Flowgraph stopped")
        return True
