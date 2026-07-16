#!/usr/bin/env python3
# Throwaway SSH server for the Step 4 live transport test (NOT for production).
# Password auth with a hardcoded credential, backed by a real bash PTY so `echo`
# and `stty size` behave for real and window-change actually resizes the PTY.
#
#   python3 tools/mock_sshd.py [port]      # default 42022, user=testuser pass=testpass
import fcntl
import os
import pty
import select
import signal
import socket
import struct
import subprocess
import sys
import termios
import threading

import paramiko

USER, PASSWORD = "testuser", "testpass"


class Server(paramiko.ServerInterface):
    def __init__(self):
        self.shell_ready = threading.Event()
        self.dims = (24, 80)          # (rows, cols)
        self.master_fd = None

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_auth_password(self, username, password):
        if username == USER and password == PASSWORD:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username):
        return "password"

    def check_channel_pty_request(self, chan, term, w, h, pw, ph, modes):
        self.dims = (h, w)
        return True

    def check_channel_shell_request(self, chan):
        self.shell_ready.set()
        return True

    def _set_winsize(self):
        if self.master_fd is not None:
            h, w = self.dims
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ,
                        struct.pack("HHHH", h, w, 0, 0))

    def check_channel_window_change_request(self, chan, w, h, pw, ph):
        self.dims = (h, w)
        self._set_winsize()
        return True


def serve_channel(chan, server):
    server.shell_ready.wait(10)
    master_fd, slave_fd = pty.openpty()
    # Deterministic test output: turn off input echo on the PTY so a caller reads
    # only command OUTPUT (no echoed command line, no readline meta-handling races).
    attrs = termios.tcgetattr(slave_fd)
    attrs[3] &= ~termios.ECHO          # lflags &= ~ECHO
    termios.tcsetattr(slave_fd, termios.TCSANOW, attrs)
    server.master_fd = master_fd
    server._set_winsize()
    env = {**os.environ, "PS1": "$ ", "TERM": "xterm", "HISTFILE": "/dev/null"}
    proc = subprocess.Popen(
        ["/bin/bash", "--norc", "--noprofile", "-i"],
        stdin=slave_fd, stdout=slave_fd, stderr=slave_fd,
        preexec_fn=os.setsid, env=env, close_fds=True)
    os.close(slave_fd)
    try:
        while True:
            r, _, _ = select.select([chan, master_fd], [], [], 0.1)
            if chan in r:
                data = chan.recv(4096)
                if not data:
                    break
                os.write(master_fd, data)
            if master_fd in r:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                chan.send(data)
            if proc.poll() is not None:
                break
    finally:
        for fn in (lambda: os.close(master_fd),
                   lambda: proc.send_signal(signal.SIGTERM),
                   chan.close):
            try:
                fn()
            except Exception:
                pass


def handle(client, hostkey):
    t = paramiko.Transport(client)
    t.add_server_key(hostkey)
    server = Server()
    try:
        t.start_server(server=server)
    except Exception:
        return
    chan = t.accept(20)
    if chan is not None:
        serve_channel(chan, server)
    t.close()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 42022
    hostkey = paramiko.RSAKey.generate(2048)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(5)
    print(f"mock sshd on 127.0.0.1:{port} (user={USER} pass={PASSWORD})", flush=True)
    while True:
        client, _ = sock.accept()
        threading.Thread(target=handle, args=(client, hostkey), daemon=True).start()


if __name__ == "__main__":
    main()
