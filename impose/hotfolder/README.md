# Hot folder

The folder half of impose: a watcher that imposes every PDF dropped into a
directory, and the two service templates that keep one running.

| File | What it is |
| --- | --- |
| `watch-inotify.sh` | The watcher, on Linux, over `inotify-tools`. The commentary on the folder layout, the lock, the claim and the exit statuses is in this one. |
| `watch-fswatch.sh` | The same watcher on macOS, over `fswatch`. It differs in one place, `settled()`, because FSEvents has no close event. |
| `impose-folder@.service` | A systemd unit, one instance per folder: `systemctl enable --now impose-folder@a4-nup`. |
| `impose-folder.plist` | A launchd agent, one copy per folder. |

They are here, inside the package, because an install from a wheel has no
checkout to copy them out of — `impose-hotfolder` prints their paths and makes
copies, and `cli.py` beside them is that command. A copy is written 0755 from
its name rather than from the mode of the file it came from — a wheel keeps
the executable bit, measured, but a checkout that did not would mean a
watcher `ExecStart=` could not start.

**Worked examples, not supported code.** What a folder is for is written in
the folder, in its `policy.conf`, and these scripts are one shape for the
thing that reads it. Read the one you are about to run; it is commented
throughout for exactly that reading. [RUNNING.md](../../RUNNING.md) is the
procedure they belong to, and the watched-folder section of
[README.md](../../README.md) is why each refusal is a refusal.

Both scripts are in the gate: `shellcheck impose/hotfolder/*.sh`, and
`bats tests/shell` starts `watch-inotify.sh` on a temporary folder. The unit
is read by `systemd-analyze verify` in CI, which is the only place in this
project that has a systemd to read it with.
