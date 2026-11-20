"""The Qwen cell of the MAP stage 3 EXPLORATION round (docs/MAP_STAGE3_DESIGN.md; exploration only: no evidence, no scoring). A subclass of MapCell with EXPLORATION-GRADE ISOLATION:
- the image is lora-rtl:v5.5-probea (it has the rtl tool, iverilog, sudo); the architecture products are removed at start;
- `no-new-privileges` is NOT set (sudo needs it), so the isolation is weaker than that of the stage 2 cell: the only sudo rule is a root-owned allowlist program (/opt/rtl/rtl.s3) that
  passes sim, probe, show, log, status, history and diff to the real rtl tool and refuses every other sub-command; every file that root runs is root-owned and not writable by the agent;
- the design (/code/rtl), the testbench, the map (/code/work/map) and the inputs are root-owned and read-only; the agent writes /code/work/align and other new files in /code/work;
- cell_checks before and after the round detect a changed input, a changed tool and the facts of the stage 2 checks that still apply."""
import json
import re
from pathlib import Path

from . import map_cell as mc
from .cell import ROOT, sh
from .map_cell import MapCell, sha

IMAGE = "lora-s3xcell:v4-20261111"       # v4 adds align_values --chain (v3: s3x3; v2: s3x2 with a faulty name check; v1: s3x1, s3x1-1)
RTL_DIR = "/opt/rtl"
ALLOWED = ("sim", "probe", "show", "log", "status", "history", "diff")
WRAPPER = '''#!/usr/bin/python3 -I
import os, sys
ALLOWED = %r
if len(sys.argv) < 2 or sys.argv[1] not in ALLOWED:
    sys.stderr.write("rtl: the commands of this order are " + ", ".join(ALLOWED) + "\\n")
    sys.exit(2)
if any(a == "--check" or a.startswith("--check=") for a in sys.argv[2:]):
    sys.stderr.write("rtl: option not available\\n")
    sys.exit(2)
os.execv("/opt/rtl/rtl.real", ["/opt/rtl/rtl.real"] + sys.argv[1:])
''' % (ALLOWED,)
SUDOERS = "Defaults env_reset\nDefaults secure_path=\"/usr/sbin:/usr/bin:/sbin:/bin\"\nagent ALL=(root) NOPASSWD: /opt/rtl/rtl.s3, /opt/s3/align_values.s3\n"
USER_RTL = "#!/bin/sh\nexec sudo -n /opt/rtl/rtl.s3 \"$@\"\n"
REMOVE = ["/opt/resources", "/opt/skills", "/opt/pilot_tools", "/tmp/ip_work", "/state", "/workspace", "/code", "/srv", "/home/ubuntu", "/var/tmp/*"]
S3_FORBIDDEN_PATHS = ["/opt/resources", "/opt/skills", "/opt/pilot_tools", "/tmp/ip_work", "/state", "/workspace", "/app", "/srv/aes", "/home/ubuntu"]


class S3Cell(MapCell):
    def __init__(self, runs_root, tag, image=IMAGE, egress_port=None, tools=True):
        super().__init__(runs_root, tag, image, egress_port=egress_port, name_prefix="map3x")
        self.rtl_files = {}
        self.tools = tools  # False: no simulator for the agent (the sudo allowlist and the rtl / align_values wrappers are removed at start)

    def start(self, inputs, qwen_md, skills, fsize=16 * 1024 * 1024, carry_align=None):
        """inputs: {cell path: (host file, sha256, mode)} (root-owned in the cell); skills: {name: host SKILL.md} (installed as skills; qwen_md is the QWEN.md text)."""
        self.inputs = inputs
        self.skills = skills
        self.run_dir.mkdir(parents=True, exist_ok=True)
        sh("docker", "rm", "-f", self.name, check=False)
        sh("docker", "run", "-d", "--name", self.name, "--entrypoint", "sleep",
           "--cap-drop", "ALL", "--cap-add", "CHOWN", "--cap-add", "DAC_OVERRIDE", "--cap-add", "FOWNER", "--cap-add", "SETUID", "--cap-add", "SETGID", "--cap-add", "KILL",
           "--cap-add", "AUDIT_WRITE", "--pids-limit", "512", "--memory", "8g", "--cpus", "4",
           "--ulimit", f"fsize={fsize}", "--ulimit", "nofile=1024", "--ulimit", "core=0", self.image, "infinity")
        if self.egress_port:
            self.lock_network(self.egress_port)
        d = ["/code/docs", "/code/rtl", "/code/verif", "/code/work/model", "/code/work/map", "/code/work/.canary_dir", "/tmp/agent", "/var/rtl", mc.TOOLDIR]
        d += sorted({str(Path(k).parent) for k in inputs})
        d += ["/tmp/qwen-home/.qwen/skills"] + [f"/tmp/qwen-home/.qwen/skills/{n}" for n in skills]
        self.exec_root("sh", "-c", "mkdir -p " + " ".join(d))
        if not self.tools:
            self.exec_root("sh", "-c", "rm -f /etc/sudoers.d/rtl /usr/local/bin/rtl /usr/local/bin/align_values")
        for dest, (src, want, mode) in inputs.items():
            if sha(src) != want:
                raise RuntimeError(f"input {dest}: the host file differs from the pinned hash")
            sh("docker", "cp", str(src), f"{self.name}:{dest}")
            self.exec_root("sh", "-c", f"chown root:root {dest} && chmod {mode} {dest}")
        sh("docker", "cp", str(qwen_md), f"{self.name}:/code/work/QWEN.md")
        for n, p in skills.items():
            sh("docker", "cp", str(p), f"{self.name}:/tmp/qwen-home/.qwen/skills/{n}/SKILL.md")
        sh("docker", "cp", str(ROOT / "tool" / "docker" / "run_agent.py"), f"{self.name}:/tmp/agent/run_agent.py")
        args = json.loads((ROOT / "tool" / "docker" / "qwen_args.json").read_text())
        args["exclude_tools"] = [t for t in args["exclude_tools"] if t != "skill"]
        self.put_text(json.dumps(args), "/tmp/agent/qwen_args.json")
        self.exec_root("sh", "-c", "echo provided > /var/rtl/testbench_mode && chmod 644 /var/rtl/testbench_mode && chown -R root:root /var/rtl && chmod 755 /var/rtl")
        self.exec_root("sh", "-c",
                       "echo canary > /code/work/.canary_file && echo canary > /code/work/.canary_dir/f && chmod 644 /code/work/.canary_file /code/work/.canary_dir/f && chmod 755 /code/work/.canary_dir && "
                       "chown -R root:root /code/docs /code/rtl /code/verif /code/work/model /code/work/map /code/work/.canary_file /code/work/.canary_dir && "
                       "chmod 755 /code /code/docs /code/rtl /code/verif /code/work/model /code/work/map && "
                       "chown root:root /code /code/work && chmod 755 /code && "
                       "chown root:root /code/work/QWEN.md && chmod 444 /code/work/QWEN.md && "
                       "mkdir -p /code/work/align && chown agent:agent /code/work/align && chmod 755 /code/work/align && chmod 1777 /code/work && "
                       "chown agent:agent /tmp/agent /tmp/qwen-home /tmp/qwen-home/.qwen && chown -R root:root /tmp/qwen-home/.qwen/skills && chmod -R go-w /tmp/qwen-home/.qwen/skills && "
                       f"chown root:root {mc.TOOLDIR} && chmod 700 {mc.TOOLDIR}")
        if carry_align:  # revision round: the align/ files of the previous round, agent-owned (the agent revises them)
            for f in sorted(Path(carry_align).iterdir()):
                if f.is_file():
                    sh("docker", "cp", str(f), f"{self.name}:/code/work/align/{f.name}")
            self.exec_root("sh", "-c", "chown -R agent:agent /code/work/align && chmod 644 /code/work/align/*")
        (self.run_dir / "cell.json").write_text(json.dumps({"container": self.name, "problem": self.problem["id"], "tag": self.tag, "image": self.image, "isolation": "exploration-grade", "carry_align": str(carry_align) if carry_align else None}))

    # ---- checks ----------------------------------------------------------------
    def checks(self, skill_hashes=None, start=False, image_id=None):
        """The stage 2 checks that still apply (through MapCell.checks with this cell's expected tree and forbidden paths), plus the checks of the exploration cell."""
        expected = {"/code", "/code/docs", "/code/rtl", "/code/verif", "/code/work", "/code/work/QWEN.md", "/code/work/model", "/code/work/map", "/code/work/.canary_file",
                    "/code/work/.canary_dir", "/code/work/.canary_dir/f"} | set(self.inputs) | {str(Path(k).parent) for k in self.inputs}
        saved = (mc.FORBIDDEN_PATHS, mc.EXPECTED_ROOT_OWNED)
        mc.FORBIDDEN_PATHS, mc.EXPECTED_ROOT_OWNED = S3_FORBIDDEN_PATHS, expected
        try:
            c = super().checks(["x"], None, image_id, start=start, image_identifiers=None)
        finally:
            mc.FORBIDDEN_PATHS, mc.EXPECTED_ROOT_OWNED = saved
        # the write tests of MapCell look at paths of the stage 2 inputs; the ones of this cell
        w = []
        for p in list(self.inputs) + ["/code/work/QWEN.md"]:
            rc, o = self._ex(f"python3 -c \"import os,sys; os.close(os.open(sys.argv[1], os.O_WRONLY)); print('writable')\" {p} 2>/dev/null || echo refused")
            w.append((p, o))
        rc, o = self._ex("(touch /code/work/align/probe_write && rm -f /code/work/align/probe_write) 2>/dev/null && echo writable || echo refused")
        w.append(("align/ writable", o))
        rc, o = self._ex("(touch /code/work/probe2 && rm -f /code/work/probe2) 2>/dev/null && echo writable || echo refused")
        w.append(("/code/work create", o))
        rc, o = self._ex("(touch /code/work/map/probe_write) 2>/dev/null && echo writable || echo refused")
        w.append(("map/ not writable", o))
        c["s3_write_tests"] = w
        c["s3_write_ok"] = all(o == "refused" for p, o in w[:-3]) and w[-3][1] == "writable" and w[-2][1] == "writable" and w[-1][1] == "refused"
        if not self.tools:  # no simulator: no sudo rule, no wrappers, the simulators not executable by the agent
            rc, o = self._ex("sudo -n -l 2>&1")
            c["sudo_rules"] = o
            rc, o2 = self._ex("command -v rtl align_values; for b in iverilog vvp verilator yosys; do /usr/local/bin/$b -V >/dev/null 2>&1 && echo RUNS:$b; done; echo end")
            c["no_tools_probe"] = o2
            c["s3_ok"] = bool(c["s3_write_ok"] and "NOPASSWD" not in o and o2.strip() == "end")
            c["ok_stage2_part"] = c["ok"]
            c["ok"] = bool(c["tree_ok"] and c["hashes_ok"] and not c["forbidden_paths_present"] and not c["forbidden_names_present"] and c["agent_uid_ok"]
                           and not c["path_dirs_writable_by_agent"] and not c["agent_owned_or_world_writable_in_root_path"] and c["startup_files_ok"]
                           and not c["docker_socket"] and c["privileged"] == "false" and not c["mounts"] and c["s3_ok"] and (c.get("processes_ok", True)))
            return c
        # the rtl command: the allowlist works, the other sub-commands and the real tool are not reachable
        rc, o = self._ex("rtl apply --help 2>&1; echo rc=$?")
        c["rtl_apply_refused"] = "the commands of this order are" in o
        rc, o = self._ex("sudo -n /opt/rtl/rtl.real status 2>&1; echo rc=$?")
        c["rtl_real_not_reachable"] = "rc=0" not in o
        rc, o = self._ex("sudo -n -l 2>&1")
        c["sudo_rules"] = o
        c["sudo_ok"] = o.count("NOPASSWD") == 1 and "/opt/rtl/rtl.s3" in o and "/opt/s3/align_values.s3" in o and "ALL" not in o.split("NOPASSWD:")[1].replace("(ALL)", "")
        rc, o = self._ex("ls -ld /opt/rtl /opt/rtl/rtl.s3 /opt/rtl/rtl.real /var/rtl /opt/s3 /opt/s3/align_values.py /opt/s3/align_values.s3 2>&1", user="root")
        c["rtl_files"] = o
        c["rtl_files_ok"] = all(l.split()[2] == "root" and l[5] in "-" and l[8] == "-" for l in o.splitlines() if l.startswith(("d", "-")))
        c["s3_ok"] = bool(c["s3_write_ok"] and c["rtl_apply_refused"] and c["rtl_real_not_reachable"] and c["sudo_ok"] and c["rtl_files_ok"])
        c["ok_stage2_part"] = c["ok"]
        c["ok"] = bool(c["tree_ok"] and c["hashes_ok"] and not c["forbidden_paths_present"] and not c["forbidden_names_present"] and c["agent_uid_ok"]
                       and not c["path_dirs_writable_by_agent"] and not c["agent_owned_or_world_writable_in_root_path"] and c["startup_files_ok"]
                       and not c["docker_socket"] and c["privileged"] == "false" and not c["mounts"] and c["s3_ok"] and (c.get("processes_ok", True)))
        return c

    def pull(self, dest, final_only=False):
        return self.pull3(dest)

    def pull3(self, dest):
        """Like MapCell.pull, for align/ (not map/); plus the rtl state (ledger, events, run outputs: for the analysis only) copied out as it is."""
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        self.kill_agent()
        self.kill_all_agent_processes()
        sh("docker", "cp", str(mc.TOOLS / "pack_work.py"), f"{self.name}:{mc.TOOLDIR}/pack_work.py")
        self.exec_root("sh", "-c",
                       f"chown root:root {mc.TOOLDIR}/pack_work.py && chmod 600 {mc.TOOLDIR}/pack_work.py && rm -rf {mc.TOOLDIR}/out && mkdir -m 700 {mc.TOOLDIR}/out && "
                       f"{mc.PY} {mc.TOOLDIR}/pack_work.py /code/work {mc.TOOLDIR}/out/work_all.tar {mc.TOOLDIR}/out/work_all.json --owner-uid {mc.AGENT_UID} && "
                       f"{mc.PY} {mc.TOOLDIR}/pack_work.py /code/work {mc.TOOLDIR}/out/align.tar {mc.TOOLDIR}/out/align.json --owner-uid {mc.AGENT_UID} --only align --max-file 1048576")
        out = {}
        for n in ("work_all.tar", "work_all.json", "align.tar", "align.json"):
            sh("docker", "cp", f"{self.name}:{mc.TOOLDIR}/out/{n}", str(dest / n))
        for t, m in (("work_all.tar", "work_all.json"), ("align.tar", "align.json")):
            man = json.loads((dest / m).read_text())
            if man["tar_sha256"] != sha(dest / t):
                raise RuntimeError("the tar copied out differs from the manifest")
            out[t] = man
        sh("docker", "cp", f"{self.name}:/var/rtl", str(dest / "rtl_state"), check=False)
        return out
