"""OS containment for trusted synthetic children; not a hostile-code sandbox."""

import ctypes
import os
import signal
import subprocess
from ctypes import wintypes
from typing import Any


class ProcessTree:
    def __init__(self) -> None:
        self.handle: Any = None
        if os.name == "nt":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)  # type: ignore[attr-defined]
            self.kernel = kernel
            kernel.CreateJobObjectW.restype = wintypes.HANDLE
            kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
            kernel.SetInformationJobObject.argtypes = [
                wintypes.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.DWORD,
            ]
            kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
            kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]

            class Basic(ctypes.Structure):
                _fields_ = [
                    ("process_time", ctypes.c_int64),
                    ("job_time", ctypes.c_int64),
                    ("flags", wintypes.DWORD),
                    ("min_ws", ctypes.c_size_t),
                    ("max_ws", ctypes.c_size_t),
                    ("active", wintypes.DWORD),
                    ("affinity", ctypes.c_size_t),
                    ("priority", wintypes.DWORD),
                    ("scheduling", wintypes.DWORD),
                ]

            class Extended(ctypes.Structure):
                _fields_ = [
                    ("basic", Basic),
                    ("io", ctypes.c_uint64 * 6),
                    ("process_memory", ctypes.c_size_t),
                    ("job_memory", ctypes.c_size_t),
                    ("peak_process", ctypes.c_size_t),
                    ("peak_job", ctypes.c_size_t),
                ]

            self.handle = kernel.CreateJobObjectW(None, None)
            if not self.handle:
                raise OSError("CONTAINMENT_UNAVAILABLE")
            limits = Extended()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            if not kernel.SetInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            ):
                self.close()
                raise OSError("CONTAINMENT_UNAVAILABLE")

    def attach(self, child: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            if not self.kernel.AssignProcessToJobObject(self.handle, int(child._handle)):  # type: ignore[attr-defined]
                child.kill()
                child.wait(timeout=5)
                raise OSError("CONTAINMENT_UNAVAILABLE")

    def terminate(self, child: subprocess.Popen[bytes]) -> None:
        if os.name == "nt":
            if not self.kernel.TerminateJobObject(self.handle, 1):
                raise OSError("TREE_TERMINATION_FAILED")
        else:
            try:
                os.killpg(child.pid, signal.SIGKILL)  # type: ignore[attr-defined]
            except ProcessLookupError:
                pass

    def close(self) -> None:
        if self.handle is not None:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
