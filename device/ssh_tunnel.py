"""
SSH tunnel manager for seestar_alp.

Establishes a local port-forward tunnel so that connections to the Seestar's
command port (4700) arrive as localhost connections on the device.  The
firmware auth gate (firmware 7.18+) only enforces RSA challenge-response for
non-localhost connections; loopback connections are flagged localhost=1 and
skip the gate entirely.

Usage::

    tunnel = SshTunnel(logger, ssh_host="10.0.0.1", ssh_user="pi")
    if tunnel.start(remote_port=4700):
        sock.connect(("127.0.0.1", tunnel.local_port))
    ...
    tunnel.stop()
"""

import socket
import subprocess
import time


class SshTunnel:
    """Manages a single ``ssh -N -L`` port-forward subprocess."""

    def __init__(self, logger, ssh_host: str, ssh_user: str, ssh_key_path: str = ""):
        self.logger = logger
        self.ssh_host = ssh_host
        self.ssh_user = ssh_user
        self.ssh_key_path = ssh_key_path
        self._proc: subprocess.Popen | None = None
        self._local_port: int | None = None

    @property
    def local_port(self) -> int | None:
        return self._local_port

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self, remote_port: int = 4700) -> bool:
        """Start (or verify) the SSH tunnel.  Returns True when the local port
        is accepting connections."""
        if self.is_alive():
            return True

        self._local_port = self._free_port()
        cmd = [
            "ssh",
            "-N",
            "-L",
            f"{self._local_port}:127.0.0.1:{remote_port}",
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=10",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            "-o",
            "ExitOnForwardFailure=yes",
        ]
        if self.ssh_key_path:
            cmd += ["-i", self.ssh_key_path]
        cmd.append(f"{self.ssh_user}@{self.ssh_host}")

        self.logger.info(
            f"SSH tunnel: {self.ssh_user}@{self.ssh_host} "
            f"-> 127.0.0.1:{remote_port} on local port {self._local_port}"
        )
        self._proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )

        # Poll until the forwarded port accepts connections (up to ~5 s).
        for _ in range(25):
            time.sleep(0.2)
            if self._proc.poll() is not None:
                stderr = self._proc.stderr.read().decode(errors="replace").strip()
                self.logger.error(f"SSH tunnel process exited: {stderr}")
                self._proc = None
                return False
            try:
                with socket.create_connection(
                    ("127.0.0.1", self._local_port), timeout=0.5
                ):
                    self.logger.info(
                        f"SSH tunnel ready on 127.0.0.1:{self._local_port}"
                    )
                    return True
            except OSError:
                continue

        self.logger.error("SSH tunnel: timed out waiting for local port to open")
        self.stop()
        return False

    def stop(self) -> None:
        if self._proc is not None:
            self.logger.info("SSH tunnel: stopping")
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

    # ------------------------------------------------------------------
    @staticmethod
    def _free_port() -> int:
        """Return an unused TCP port on localhost."""
        with socket.socket() as s:
            s.bind(("", 0))
            return s.getsockname()[1]
