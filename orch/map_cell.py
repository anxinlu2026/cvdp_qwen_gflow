"""The Qwen cell of MAP stage 2 (docs/MAP_STAGE2_CELL_AND_ROUNDS_DESIGN.md sections 2, 3, 6). A subclass of orch.cell.Cell that does NOT change the behaviour of the existing cells:
- a flattened image without the architecture products (tool/docker/stage2_cell); nothing in it that root runs is writable by the agent;
- /code/work is owned by root with the sticky bit (1777): the agent can create files but cannot delete or rename the root-owned input files and directories;
- resource limits on the container; egress only to the recording proxy;
- every step that runs as root inside the cell uses a fixed PATH (system directories only), absolute interpreter paths, a root-owned 700 tool directory and no path the agent can write (R2 A1, A2);
- the files of the agent leave the cell only through pack_work.py, after every process of the agent has been killed (no concurrent change while it walks, R2 A3), as tars;
  the carry-over into a new cell goes through unpack_carry.py;
- cell_checks before and after a round."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

from .cell import ROOT, Cell, sh

IMAGE = "lora-s2cell:v1-20261110"
TOOLS = ROOT / "tool" / "stage2"
BASELINE = ROOT / "tool" / "docker" / "stage2_cell" / "baseline.json"
AGENT_UID = 1001
TOOLDIR = "/usr/local/lib/s2"                 # root-owned, 700, created at start: the agent cannot create, replace or link anything here
ROOT_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"   # the PATH of every command that runs as root inside the cell (the system directories are root-owned, checked)
PY = "/usr/bin/python3 -I"
FORBIDDEN_NAMES = ["ip_models", "BLOCKS.txt", "MODEL.md", "SOURCE.md", "VALIDATION.md", "INDEPENDENT_CHECK.md", "aes_ref_qwen.py", "aes128_model.py",
                   "stage2_validate", "aes128_datafile", "rtl_identifiers"]
FORBIDDEN_PATHS = ["/opt/resources", "/opt/rtl", "/opt/skills", "/opt/pilot_tools", "/usr/local/bin/rtl", "/var/rtl", "/tmp/ip_work", "/state", "/workspace", "/etc/sudoers.d/rtl",
                   "/app", "/srv/aes", "/home/ubuntu"]
EXPECTED_ROOT_OWNED = {"/code", "/code/docs", "/code/docs/fips197.txt", "/code/task.md", "/code/verif", "/code/verif/tb_aes128_dec.sv", "/code/work", "/code/work/QWEN.md",
                       "/code/work/model_spec.md", "/code/work/top_spec.md", "/code/work/model", "/code/work/model/aes_model.py", "/code/work/.canary_file", "/code/work/.canary_dir",
                       "/code/work/.canary_dir/f"}
ENV_OK_EXTRA = {"PWD", "OLDPWD", "SHLVL", "_", "HOSTNAME", "TERM", "LANG"}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class MapCell(Cell):
    def __init__(self, runs_root, tag, image=IMAGE, egress_port=None, name_prefix="map2"):
        problem = {"id": f"{name_prefix}_aes0005", "task": "", "spec": "", "files": {}, "redacted": False, "converted": False}
        super().__init__(problem, runs_root, tag, image, egress_port=egress_port)
        self.inputs = {}

    # ---- root and agent commands -------------------------------------------------
    def exec_root(self, *cmd, input=None, check=True):
        return sh("docker", "exec", "-i", "-u", "root", "-e", f"PATH={ROOT_PATH}", self.name, *cmd, input=input, check=check).stdout

    def _ex(self, script, user=None, input=None):
        """user None = the agent (the image user); "root" = root with the fixed PATH."""
        cmd = ["docker", "exec", "-i"] + (["-u", "root", "-e", f"PATH={ROOT_PATH}"] if user == "root" else []) + [self.name, "sh", "-c", script]
        r = subprocess.run(cmd, capture_output=True, text=True, input=input, timeout=300)
        return r.returncode, r.stdout.strip()

    # ---- start ----------------------------------------------------------------
    def start(self, inputs, qwen_md, skill_md, fsize=16 * 1024 * 1024):
        """inputs: {cell path: (host file, expected sha256, mode)}; the host files are root-owned sources. qwen_md and skill_md: host files (the skill text)."""
        self.inputs = inputs
        self.run_dir.mkdir(parents=True, exist_ok=True)
        sh("docker", "rm", "-f", self.name, check=False)
        sh("docker", "run", "-d", "--name", self.name, "--entrypoint", "sleep",
           "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER", "--cap-add", "SETUID", "--cap-add", "SETGID", "--cap-add", "KILL",
           "--security-opt", "no-new-privileges", "--pids-limit", "256", "--memory", "8g", "--cpus", "4",
           "--ulimit", f"fsize={fsize}", "--ulimit", "nofile=1024", "--ulimit", "core=0", self.image, "infinity")
        if self.egress_port:
            self.lock_network(self.egress_port)
        d = ["/code/docs", "/code/verif", "/code/work/model", "/code/work/map", "/code/work/.canary_dir", "/tmp/agent", "/tmp/qwen-home/.qwen/skills/model-to-blocks", TOOLDIR]
        self.exec_root("sh", "-c", "rm -rf /code && mkdir -p " + " ".join(d))
        for dest, (src, want, mode) in inputs.items():
            if sha(src) != want:
                raise RuntimeError(f"input {dest}: the host file differs from the pinned hash")
            sh("docker", "cp", str(src), f"{self.name}:{dest}")
            self.exec_root("sh", "-c", f"chown root:root {dest} && chmod {mode} {dest}")
        sh("docker", "cp", str(qwen_md), f"{self.name}:/code/work/QWEN.md")
        sh("docker", "cp", str(skill_md), f"{self.name}:/tmp/qwen-home/.qwen/skills/model-to-blocks/SKILL.md")
        sh("docker", "cp", str(ROOT / "tool" / "docker" / "run_agent.py"), f"{self.name}:/tmp/agent/run_agent.py")
        args = json.loads((ROOT / "tool" / "docker" / "qwen_args.json").read_text())
        args["exclude_tools"] = [t for t in args["exclude_tools"] if t != "skill"]          # as M5C: the skill tool enabled
        self.put_text(json.dumps(args), "/tmp/agent/qwen_args.json")
        self.exec_root("sh", "-c",
                       "echo canary > /code/work/.canary_file && echo canary > /code/work/.canary_dir/f && chmod 644 /code/work/.canary_file /code/work/.canary_dir/f && chmod 755 /code/work/.canary_dir && "
                       "chown -R root:root /code/docs /code/verif /code/work/model /code/work/.canary_file /code/work/.canary_dir && "
                       "chown root:root /code /code/work && chmod 755 /code /code/docs /code/verif /code/work/model && "
                       "chown root:root /code/work/QWEN.md && chmod 444 /code/work/QWEN.md && "
                       "chmod 1777 /code/work && "                                                      # R2 A1 (first review): root-owned, sticky
                       "chown agent:agent /code/work/map && chmod 755 /code/work/map && "
                       "chown agent:agent /tmp/agent /tmp/qwen-home /tmp/qwen-home/.qwen && "
                       "chown -R root:root /tmp/qwen-home/.qwen/skills && chmod -R go-w /tmp/qwen-home/.qwen/skills && chmod 444 /tmp/qwen-home/.qwen/skills/model-to-blocks/SKILL.md && "
                       f"chown root:root {TOOLDIR} && chmod 700 {TOOLDIR}")
        (self.run_dir / "cell.json").write_text(json.dumps({"container": self.name, "problem": self.problem["id"], "tag": self.tag, "image": self.image}))

    # ---- checks ---------------------------------------------------------------
    def agent_processes(self):
        rc, out = self._ex("ps -eo pid,uid,args | tail -n +2", user="root")
        procs = []
        for l in out.splitlines():
            parts = l.split(None, 2)
            if len(parts) >= 2 and parts[1] == str(AGENT_UID) and parts[0] != "1" and "ps -eo" not in l and "tail -n" not in l and "<defunct>" not in l:
                procs.append(l.strip())
        return procs

    def kill_all_agent_processes(self):
        """After this the file system cannot change under a root step that walks it: the agent has no process left (R2 A3). Raises when one survives."""
        for _ in range(5):
            self._ex("ps -eo pid,uid | tail -n +2 | while read p u; do [ \"$u\" = 1001 ] && [ \"$p\" != 1 ] && kill -9 $p; done; true", user="root")
            if not self.agent_processes():
                return
            import time
            time.sleep(0.5)
        raise RuntimeError("an agent process survived: " + "; ".join(self.agent_processes())[:200])

    def checks(self, identifiers, skill_sha=None, image_id=None, start=False, image_identifiers=None):
        """The cell_checks of the design (section 3) that need the running cell; returns {name: result} and "ok".
        identifiers: the private RTL identifier list (never empty: an empty list would switch the scan off); image_identifiers: the ones that do not occur in the pristine image
        (fed through stdin, never stored in the cell)."""
        if not identifiers:
            raise ValueError("the identifier list is empty: the scan would be off")
        base = json.loads(BASELINE.read_text())
        c = {}
        c["image_id"] = sh("docker", "image", "inspect", "--format", "{{.Id}}", self.image).stdout.strip()
        rc, out = self._ex("for p in " + " ".join(FORBIDDEN_PATHS) + "; do [ -e $p ] && { [ ! -d $p ] || [ -n \"$(ls -A $p)\" ]; } && echo $p; done", user="root")
        c["forbidden_paths_present"] = out.split()
        pat = " -o ".join(f"-name {n}" for n in FORBIDDEN_NAMES)
        rc, out = self._ex(f"find / -xdev \\( {pat} \\) -not -path '/proc/*' 2>/dev/null | head -20", user="root")
        c["forbidden_names_present"] = out.split()
        rc, out = self._ex("find /code -maxdepth 3 -user root | sort", user="root")
        c["root_owned_tree"] = out.split()
        c["tree_ok"] = set(c["root_owned_tree"]) == EXPECTED_ROOT_OWNED
        rc, out = self._ex("find /code -maxdepth 3 -not -user root | sort", user="root")
        c["agent_created_tree"] = out.split()
        c["hashes"] = {}
        for dest, (src, want, mode) in self.inputs.items():
            rc, o = self._ex(f"sha256sum {dest}", user="root")
            c["hashes"][dest] = o.split()[0] if o else None
        c["hashes_ok"] = all(c["hashes"][d] == self.inputs[d][1] for d in self.inputs)
        rc, o = self._ex("sha256sum /code/work/QWEN.md /tmp/qwen-home/.qwen/skills/model-to-blocks/SKILL.md", user="root")
        c["skill_hashes"] = [x.split()[0] for x in o.splitlines()]
        # write tests as the agent. Inputs: opened for writing without writing anything (nothing is changed if the protection failed); canaries: really renamed and deleted
        w = []
        for p in ["/code/docs/fips197.txt", "/code/work/QWEN.md", "/code/work/model/aes_model.py", "/code/work/top_spec.md", "/code/work/model_spec.md", "/code/task.md", "/code/verif/tb_aes128_dec.sv"]:
            rc, o = self._ex(f"python3 -c \"import os,sys; os.close(os.open(sys.argv[1], os.O_WRONLY)); print('writable')\" {p} 2>/dev/null || echo refused")
            w.append((p, o))
        rc, o = self._ex("(mv /code/work/.canary_dir /code/work/.canary_dir2) 2>/dev/null && echo moved || echo refused")
        w.append(("rename root-owned dir", o))
        rc, o = self._ex("(mv /code/work/.canary_file /code/work/.canary_file2) 2>/dev/null && echo moved || echo refused")
        w.append(("rename root-owned file", o))
        rc, o = self._ex("(rm -f /code/work/.canary_file) 2>/dev/null; [ -e /code/work/.canary_file ] && echo refused || echo deleted")
        w.append(("delete root-owned file", o))
        rc, o = self._ex("(rm -f /code/work/.canary_dir/f) 2>/dev/null; [ -e /code/work/.canary_dir/f ] && echo refused || echo deleted")
        w.append(("delete in root-owned dir", o))
        rc, o = self._ex("(touch /code/work/map/probe_write && rm -f /code/work/map/probe_write) 2>/dev/null && echo writable || echo refused")
        w.append(("map/ writable", o))
        rc, o = self._ex("(touch /code/work/probe2 && rm -f /code/work/probe2) 2>/dev/null && echo writable || echo refused")
        w.append(("/code/work create", o))
        c["write_tests"] = w
        c["write_ok"] = all(o == "refused" for p, o in w[:-2]) and w[-2][1] == "writable" and w[-1][1] == "writable"
        # what root runs must not be writable by the agent: the PATH directories and their entries, the interpreter
        dirs = [x["dir"] for x in base["path_dirs"]]
        rc, o = self._ex("for d in " + " ".join(dirs) + "; do [ -w $d ] && echo $d; done")
        c["path_dirs_writable_by_agent"] = o.split()
        rc, o = self._ex("find " + " ".join(dirs) + " /usr/bin /usr/lib/python3.12 -maxdepth 1 \\( -user 1001 -o -perm -0002 \\) -not -type l 2>/dev/null | head", user="root")
        c["agent_owned_or_world_writable_in_root_path"] = o.split()
        rc, o = self._ex("find / -xdev \\( -name '*.pth' -o -name sitecustomize.py -o -name usercustomize.py \\) -not -path '/proc/*' 2>/dev/null | sort | while read f; do sha256sum \"$f\"; done", user="root")
        cur = {l.split()[1]: l.split()[0] for l in o.splitlines() if len(l.split()) == 2}
        c["startup_files_ok"] = cur == base["startup_files"]
        c["startup_files_diff"] = sorted(set(cur) ^ set(base["startup_files"])) + [p for p in cur if p in base["startup_files"] and cur[p] != base["startup_files"][p]]
        # the agent: environment keys and values, capabilities, docker socket
        rc, o = self._ex("env")
        keys = [l.split("=", 1)[0] for l in o.splitlines() if "=" in l]
        c["agent_env_keys_unexpected"] = sorted(set(keys) - set(base["env_keys"]) - ENV_OK_EXTRA)
        c["env_has_rtl"] = [l.split("=", 1)[0] for l in o.splitlines() if re.search(r"rtl|/opt", l, re.I)]
        rc, o = self._ex("grep -E '^Cap(Eff|Bnd|Prm|Inh|Amb)' /proc/self/status")
        caps = dict(l.split(":\t") for l in o.splitlines() if ":\t" in l)
        c["agent_caps"] = caps
        c["agent_caps_ok"] = caps.get("CapEff", "x") == "0000000000000000" and caps.get("CapPrm", "x") == "0000000000000000"
        rc, o = self._ex("ls /var/run/docker.sock /run/docker.sock 2>/dev/null")
        c["docker_socket"] = o.split()
        c["mount_points"] = self._ex("awk '{print $5}' /proc/self/mountinfo | sort", user="root")[1].split()
        c["mounts"] = json.loads(sh("docker", "inspect", "--format", "{{json .Mounts}}", self.name).stdout.strip() or "[]")
        c["privileged"] = sh("docker", "inspect", "--format", "{{.HostConfig.Privileged}}", self.name).stdout.strip()
        c["agent_uid"] = self._ex("id -u agent", user="root")[1]
        c["agent_uid_ok"] = c["agent_uid"] == str(AGENT_UID) and self._ex("id -u")[1] == str(AGENT_UID)     # R2: pkill, the owner filter and chown all use this number
        c["agent_processes"] = self.agent_processes()
        if image_identifiers:
            rc, o = self._ex("grep -rawliF -f /dev/stdin / --exclude-dir=proc --exclude-dir=sys --exclude-dir=dev --exclude-dir=code 2>/dev/null | head -20", user="root",
                             input="\n".join(image_identifiers) + "\n")
            c["identifier_hits_in_image"] = o.split()
        if image_id:                      # the facts that are only recorded (capabilities, mounts) hold because the image is the pinned one
            c["image_id_ok"] = c["image_id"] == image_id
        if skill_sha:
            c["skill_ok"] = len(c["skill_hashes"]) == 2 and all(h == skill_sha for h in c["skill_hashes"])
        if start:                         # at the start of a round no process of the agent is running except the container's own sleep
            c["processes_ok"] = not c["agent_processes"]
        extra = [c[k] for k in ("image_id_ok", "skill_ok", "processes_ok") if k in c]
        c["ok"] = (all(extra) and not c["forbidden_paths_present"] and not c["forbidden_names_present"] and c["tree_ok"] and c["hashes_ok"] and c["write_ok"] and c["agent_uid_ok"]
                   and not c["path_dirs_writable_by_agent"] and not c["agent_owned_or_world_writable_in_root_path"] and c["startup_files_ok"]
                   and not c["agent_env_keys_unexpected"] and not c["env_has_rtl"] and c["agent_caps_ok"] and not c["docker_socket"]
                   and c["privileged"] == "false" and not c.get("identifier_hits_in_image") and not c["mounts"])
        return c

    # ---- the agent ------------------------------------------------------------
    def kill_agent(self):
        for pat in ("run_agent.py", "qwen", "fake_agent"):
            sh("docker", "exec", "-u", "root", "-e", f"PATH={ROOT_PATH}", self.name, "pkill", "-f", pat, check=False)

    # ---- files out and in -----------------------------------------------------
    def pull(self, dest, final_only=False):
        """Overrides Cell.pull: every process of the agent is killed first, then the only things that leave the cell are the two tars made by pack_work.py (everything the agent created, and
        map/ alone) and their manifests. The tools and the output live in a root-owned 700 directory (R2 A1); the interpreter is /usr/bin/python3 -I (R2 A2)."""
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        self.kill_agent()
        self.kill_all_agent_processes()
        sh("docker", "cp", str(TOOLS / "pack_work.py"), f"{self.name}:{TOOLDIR}/pack_work.py")
        self.exec_root("sh", "-c",
                       f"chown root:root {TOOLDIR}/pack_work.py && chmod 600 {TOOLDIR}/pack_work.py && rm -rf {TOOLDIR}/out && mkdir -m 700 {TOOLDIR}/out && "
                       f"{PY} {TOOLDIR}/pack_work.py /code/work {TOOLDIR}/out/work_all.tar {TOOLDIR}/out/work_all.json --owner-uid {AGENT_UID} && "
                       f"{PY} {TOOLDIR}/pack_work.py /code/work {TOOLDIR}/out/map.tar {TOOLDIR}/out/map.json --owner-uid {AGENT_UID} --only map --max-file 1048576")
        out = {}
        for n in ("work_all.tar", "work_all.json", "map.tar", "map.json"):
            sh("docker", "cp", f"{self.name}:{TOOLDIR}/out/{n}", str(dest / n))
        for t, m in (("work_all.tar", "work_all.json"), ("map.tar", "map.json")):
            if (dest / m).stat().st_size > 1024 * 1024:
                raise RuntimeError("a manifest is larger than 1 MB")
            man = json.loads((dest / m).read_text())
            if man["tar_sha256"] != sha(dest / t):
                raise RuntimeError("the tar copied out differs from the manifest")
            out[t] = man
        return out

    def restore_carry(self, map_tar):
        """New cell, round 2 and 3: put the map/ of the previous round (from its map.tar) into /code/work/map (decision B: nothing else is carried over)."""
        sh("docker", "cp", str(TOOLS / "unpack_carry.py"), f"{self.name}:{TOOLDIR}/unpack_carry.py")
        sh("docker", "cp", str(map_tar), f"{self.name}:{TOOLDIR}/carry.tar")
        self.exec_root("sh", "-c", f"chown root:root {TOOLDIR}/unpack_carry.py {TOOLDIR}/carry.tar && chmod 600 {TOOLDIR}/unpack_carry.py {TOOLDIR}/carry.tar && "
                                    f"{PY} {TOOLDIR}/unpack_carry.py {TOOLDIR}/carry.tar /code/work --prefix map --uid {AGENT_UID} --gid {AGENT_UID} && rm -f {TOOLDIR}/carry.tar")
