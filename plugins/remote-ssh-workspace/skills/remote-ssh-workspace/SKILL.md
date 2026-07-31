---
name: remote-ssh-workspace
description: Reliable workflow for working on remote hosts over SSH. Use whenever Codex must inspect, edit, build, test, benchmark, profile, or operate files/services on a remote server; especially when work involves SSH multiplexing, sshfs mounts, files owned by a different remote user such as postgres, long-running commands, logs, sudo, heredocs, SQL, awk, or fragile shell quoting.
---

# Remote SSH Workspace

Use a remote workspace instead of ad hoc SSH commands. The goal is to make the remote host feel like a stable worktree: fast SSH reuse, local file editing through `sshfs`, correct remote file ownership, detached long jobs with logs, and simple command invocations.

## Required Contract

Before doing real work on a remote host, establish and report:

- `HOST`: the exact SSH target or alias.
- `CONTROLLER`: where orchestration runs; prefer the local machine, not a remote-to-remote SSH hop.
- `REMOTE_PATH`: the remote directory being inspected or edited.
- `TARGET_USER`: the user that should own created files, if different from the SSH login user.
- `TARGET_GROUP`: the group that should own created files; do not assume it equals `TARGET_USER`.
- `MOUNT`: the local `sshfs` mount point, when files will be read or edited repeatedly.
- `LOG_DIR`: the remote directory where long command logs and status files will be written.

If any item cannot be established, stop and state the blocker before modifying remote state.

Before using templates below, verify required local and remote tools. At minimum check local `ssh`, `sshfs`, `findmnt` or platform equivalent, and `fusermount3`/`umount`; check remote `bash`, `sudo -n`, `stat`, `setsid`, and project binaries. If the controller or remote host is not Linux, state the equivalent commands before proceeding.

Never interpolate raw, user-provided, or discovered paths directly into a remote shell command. Prefer a mounted script with constants inside the script. If a remote command must receive values, pass them as script arguments and quote each argument for the remote shell, for example with local `printf '%q'`, then inspect the final command. Treat inline examples below as templates for simple absolute paths only.

## Workflow

### 1. Enable SSH reuse first

Inspect the effective SSH config before repeated access:

```bash
ssh -o BatchMode=yes -o ConnectTimeout=10 -G "$HOST" |
  egrep '^(user|hostname|controlmaster|controlpath|controlpersist|serveralive)'
```

If multiplexing is not enabled for the host, add or request a narrow host-specific OpenSSH config block:

```sshconfig
Host <alias-or-host>
  HostName <host>
  User <login-user>
  ControlMaster auto
  ControlPath ~/.ssh/cm/%C
  ControlPersist yes
  ServerAliveInterval 30
  ServerAliveCountMax 3
```

Then verify reuse:

```bash
mkdir -p ~/.ssh/cm
ssh -o BatchMode=yes -o ConnectTimeout=10 "$HOST" true
ssh -O check "$HOST"
```

Do not invent custom SSH poolers before trying OpenSSH multiplexing.

Use `BatchMode=yes` and a short `ConnectTimeout` for probes. If an SSH probe hangs and leaves stale local SSH processes, stop and clean them up before continuing; do not stack more probes on top of a stuck connection.

### 2. Mount remote files before editing

Use `sshfs` for iterative remote file work. Do not push source files, scripts, or configs back and forth with `scp`/`tar|ssh` unless it is a one-time bulk transfer and `sshfs` is unavailable or unsuitable.

Basic mount:

```bash
mkdir -p "$MOUNT"
if findmnt --target "$MOUNT" >/dev/null 2>&1; then
  findmnt --target "$MOUNT"
  # Continue only if the existing mount already points to the intended HOST:REMOTE_PATH.
fi
sshfs "$HOST:$REMOTE_PATH" "$MOUNT" -o reconnect -o ServerAliveInterval=15 -o ServerAliveCountMax=3
findmnt "$MOUNT"
```

If files must be created as another remote user, mount through that user's `sftp-server`:

```bash
SFTP_SERVER=$(ssh "$HOST" 'command -v sftp-server || { test -x /usr/lib/openssh/sftp-server && echo /usr/lib/openssh/sftp-server; } || { test -x /usr/libexec/openssh/sftp-server && echo /usr/libexec/openssh/sftp-server; }')
test -n "$SFTP_SERVER"
ssh "$HOST" "sudo -n -u $TARGET_USER test -d '$REMOTE_PATH'"
sshfs "$HOST:$REMOTE_PATH" "$MOUNT" \
  -o "sftp_server=sudo -n -u $TARGET_USER $SFTP_SERVER" \
  -o reconnect -o ServerAliveInterval=15 -o ServerAliveCountMax=3
```

Always prove remote ownership after mounting:

```bash
touch "$MOUNT/.sshfs-owner-test"
ssh "$HOST" "stat -c '%U:%G %a %n' '$REMOTE_PATH/.sshfs-owner-test'"
rm -f "$MOUNT/.sshfs-owner-test"
```

If ownership is wrong, fix the mount. Do not use the pattern "copy as login user, then chown" as the default workflow.

Also prove the mount boundary before editing sibling directories:

```bash
findmnt --target "$MOUNT"
realpath "$MOUNT"
```

Do not use `..` from inside a mount and assume the parent is remote. If work needs both `src` and `tools`, mount their common remote parent, not only `src`.

Treat `sshfs` as file transport, not as a good place for broad repository operations. Avoid tree-wide `git status`, `git diff`, or recursive scans over `sshfs`. Use a local Git worktree to determine changed files only after proving it matches the remote repo identity and revision: toplevel, branch, `HEAD`, and dirty state. Otherwise inspect Git state on the remote host and transfer only explicitly selected files.

When copying through `sshfs`, do not preserve owner/group/mode unless the mount supports it. If `rsync` returns partial-transfer errors because `chown`, `chgrp`, or mode changes failed on FUSE, rerun without preserving owner/group/perms and verify file content explicitly.

### 3. Avoid fragile remote one-liners

Use remote one-liners only for short, simple checks. If a command contains SQL, `awk`, JSON, heredocs, nested quotes, or more than a few shell statements, create a script file through `sshfs`, validate it, and run that script with a simple SSH command.

Preferred pattern:

```bash
# Edit locally under $MOUNT/tools/job.sh, then:
bash -n "$MOUNT/tools/job.sh"
ssh "$HOST" "sudo -n -u $TARGET_USER bash '$REMOTE_PATH/tools/job.sh'"
```

Inside scripts that run as `TARGET_USER`, set a deterministic `PATH` or use full paths for project binaries. Do not rely on login-shell startup files under `sudo -u`/`runuser`; commands such as `createdb`, `pgbench`, `psql`, `perf`, or project tools should resolve predictably.

If a privileged command writes a log, make the redirection privileged too. Prefer `sudo sh -c 'command >log 2>&1'`, `sudo tee`, or a wrapper script. Do not assume `sudo command >root-owned-log` writes as root; the shell redirection still belongs to the caller.

If creating a new file directly on `sshfs` is unreliable, create it in a local temporary directory, validate it, then copy it through the mount:

```bash
bash -n /tmp/job.sh
cp /tmp/job.sh "$MOUNT/tools/job.sh"
ssh "$HOST" "stat -c '%U:%G %a %n' '$REMOTE_PATH/tools/job.sh'"
```

### 4. Detach long remote commands

Any remote command expected to run longer than about 10 seconds, produce large output, build software, run tests, benchmark, restore data, or profile must run detached on the remote host with output saved to a remote log file.

This includes service starts/stops, backup/restore, `rclone`, `pgbench`, package installs, `drop_caches`, hugepage allocation, `perf`, `bpftrace`, and large `find`/`grep`/`du` scans.

Use a checked-in or mounted job script plus a launcher script. The job script should write a log and an exit-code file:

```bash
#!/usr/bin/env bash
set -uo pipefail

LOG=${LOG:-/tmp/remote-job.log}
RC=${RC:-/tmp/remote-job.rc}

(
  set -euo pipefail
  echo "started=$(date -Is)"
  # Put the real command here.
  echo "finished=$(date -Is)"
) > "$LOG" 2>&1
status=$?
echo "$status" > "$RC"
exit "$status"
```

Put launch redirections and PID/RC writes inside a launcher script executed as `TARGET_USER`. Do not write `PID_FILE` or `LAUNCH_LOG` from the SSH login user's shell unless that ownership is intentional and verified.

Launcher script template:

```bash
#!/usr/bin/env bash
set -euo pipefail

REMOTE_SCRIPT=$1
LOG=$2
RC=$3
PID_FILE=$4
LAUNCH_LOG=$5

mkdir -p "$(dirname "$LOG")" "$(dirname "$RC")" "$(dirname "$PID_FILE")" "$(dirname "$LAUNCH_LOG")"
setsid env LOG="$LOG" RC="$RC" bash "$REMOTE_SCRIPT" > "$LAUNCH_LOG" 2>&1 < /dev/null &
echo "$!" > "$PID_FILE"
```

Launch the launcher with a simple SSH command after validating it with `bash -n`.

After launching, immediately report:

- remote script path;
- main log path;
- launch log path;
- PID file path;
- RC file path.

Do not keep a long build, test, benchmark, restore, or profiler attached to the terminal.

For multi-stage jobs, write stage markers and stage-specific evidence into the log. A restore can copy data successfully and still fail later when hugepages or service startup fail; report both the last completed stage and the final `RC`.

### 5. Monitor by logs and status files

Watch progress by polling the remote log and process state:

```bash
ssh "$HOST" "pid=\$(cat '$PID_FILE' 2>/dev/null || true); test -n \"\$pid\" && ps -p \"\$pid\" -o pid,ppid,stat,etime,cmd || true; tail -n 80 '$LOG' 2>/dev/null || tail -n 80 '$LAUNCH_LOG'"
```

When the process exits, read the exit-code file and the final log tail:

```bash
ssh "$HOST" "cat '$RC' 2>/dev/null; tail -n 120 '$LOG' 2>/dev/null || tail -n 120 '$LAUNCH_LOG'"
```

Do not declare success from a clean SSH return code if the real command was detached. The detached job's `RC` file is the result.

### 6. Keep multi-host orchestration local

When a task involves more than one remote host, prefer local fan-out from the controller machine:

```bash
ssh "$SERVER" "tail -n 40 '$SERVER_LOG'"
ssh "$CLIENT" "tail -n 40 '$CLIENT_LOG'"
```

For multi-host work, define a per-host table first: role, SSH target, target user/group, remote path, log dir, clock/timezone check, and cleanup responsibility. Use role-prefixed log, PID, and RC files to avoid collisions.

Do not make server A SSH into server B unless that hop is explicitly required and preflighted. Remote-to-remote SSH often fails on host key trust, missing SSH config, wrong user, or unavailable credentials. If a remote-to-remote hop is required, verify it first with `BatchMode=yes`, `ConnectTimeout`, `ssh -G`, and a harmless command.

For network or benchmark smoke checks, use read-only probes first:

```bash
ssh "$CLIENT" "psql -h '$SERVER_IP' -p '$PORT' -U postgres -d postgres -c 'select 1'"
```

Do not run a write workload as a smoke test against a benchmark data set. A short `pgbench` write smoke still changes the database and can invalidate a clean-restore comparison.

### 7. Close out remote work

Before finishing, verify the actual remote state relevant to the task:

- edited files exist on the remote host and have the expected owner;
- scripts pass `bash -n` or the relevant linter/check;
- long jobs have exited and their `RC` is `0`, or failures are explained from logs;
- no unintended long-running `pgbench`, build, monitor, profiler, or restore process remains;
- services or APIs touched by the task are checked through their real status/log/API path.
- benchmark or restore state is still methodologically valid; if a smoke test, scheduler change, restored config, page cache, dirty-page setting, or service restart changed the baseline, say so and rerun from a clean state.
- each `sshfs` mount is either unmounted with `fusermount3 -u "$MOUNT"` or the final answer explicitly says it was intentionally left mounted.

For bulk copy and restore jobs, verify the real artifact, not just the copy command. For PostgreSQL this means checking required empty directories, `pg_controldata` where appropriate, `pg_isready`, effective settings, and a read-only SQL query before any write workload.

## Fallbacks

If `sshfs` is missing or blocked, say so explicitly and use the narrowest fallback:

- create scripts locally in `/tmp`;
- validate locally where possible;
- transfer once to a temporary remote path;
- move into place with `sudo install -o "$TARGET_USER" -g "$TARGET_GROUP"` or the project-appropriate owner/group;
- keep all long commands detached with logs and status files.

If shell quoting fails once, stop trying variants of the same long one-liner. Switch to a mounted script or a local temporary script copied through the established file path.
