"""The container of one problem: files in, permissions, control calls, files out. Needs Docker."""
import json
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def sh(*cmd, check=True, input=None, timeout=600):
    r = subprocess.run(cmd, capture_output=True, text=True, input=input, timeout=timeout)
    if check and r.returncode:
        raise RuntimeError(f"{' '.join(cmd[:4])}...: {r.stderr.strip() or r.stdout.strip()}")
    return r


class Cell:
    def __init__(self, problem, runs_root, tag, image="lora-rtl:dev", egress_port=None):
        self.problem, self.image, self.tag = problem, image, tag
        self.tb_mode = None
        self.egress_port = egress_port      # None = egress open; a port = the container may reach only the host's recording proxy on that port (lock_network)
        slug = re.sub(r"[^a-zA-Z0-9_.-]", "_", problem["id"])[-40:]
        self.name = f"lora_{slug}_{tag}"
        self.run_dir = Path(runs_root) / f"{slug}-{tag}"

    # ---- lifecycle -----------------------------------------------------------
    def start(self):
        stage = self.run_dir / "stage"
        if stage.exists():
            raise FileExistsError(stage)
        for rel, text in self.problem["files"].items():
            (stage / rel).parent.mkdir(parents=True, exist_ok=True)
            (stage / rel).write_text(text)
        for d in ("rtl", "verif", "docs"):
            (stage / d).mkdir(exist_ok=True)
        (stage / "task.md").write_text(self.problem["task"])
        (stage / "spec.md").write_text(self.problem["spec"])
        sh("docker", "rm", "-f", self.name, check=False)
        sh("docker", "run", "-d", "--name", self.name, "--entrypoint", "sleep", self.image, "infinity")
        if self.egress_port:
            self.lock_network(self.egress_port)
        sh("docker", "exec", "-u", "root", self.name, "rm", "-rf", "/code")
        sh("docker", "cp", str(stage), f"{self.name}:/code")
        sh("docker", "exec", "-u", "root", self.name, "sh", "-c",
           "chown -R root:root /code && chmod -R go-w /code && chmod 755 /code && mkdir /code/work && chown agent:agent /code/work "
           "&& mkdir -p /tmp/agent && chown agent:agent /tmp/agent")
        args = ROOT / "tool" / "docker" / "qwen_args.json"
        sh("docker", "cp", str(args), f"{self.name}:/tmp/agent/qwen_args.json")
        sh("docker", "cp", str(ROOT / "tool" / "docker" / "run_agent.py"), f"{self.name}:/tmp/agent/run_agent.py")
        (self.run_dir / "cell.json").write_text(json.dumps({"container": self.name, "problem": self.problem["id"], "tag": self.tag}))

    def restore(self, snapshot):
        """Put a saved cell state (the after-NN-Hx directory of an earlier run: state/, work/, rtl/) into this freshly started cell, so that the flow continues from there (REVIEW_LOG #32:
        H3-only repeated measurements from the state after H2). The design under /code/rtl is the one the cell was started with; the state records its hash and the restore checks it."""
        import shutil
        snap = Path(snapshot)
        for d in ("state", "work"):
            if not (snap / d).is_dir():
                raise FileNotFoundError(snap / d)
        sh("docker", "exec", "-u", "root", self.name, "sh", "-c", "rm -rf /var/rtl && mkdir -p /var/rtl")
        sh("docker", "cp", f"{snap / 'state'}/.", f"{self.name}:/var/rtl")
        sh("docker", "exec", "-u", "root", self.name, "sh", "-c", "chown -R root:root /var/rtl && chmod -R go-w /var/rtl && chmod 755 /var/rtl")
        sh("docker", "cp", f"{snap / 'work'}/.", f"{self.name}:/code/work")
        sh("docker", "exec", "-u", "root", self.name, "sh", "-c", "chown -R agent:agent /code/work")
        if (snap / "rtl").is_dir():
            a = sh("docker", "exec", self.name, "sh", "-c", "cd /code/rtl && cat $(ls | sort) | sha256sum").stdout.split()[0]
            import hashlib
            h = hashlib.sha256()
            for f in sorted((snap / "rtl").iterdir()):
                h.update(f.read_bytes())
            if h.hexdigest() != a:
                raise RuntimeError("the design of the snapshot differs from the design of this cell")

    def set_testbench_mode(self, mode):
        """Write the testbench mode (provided | write) where the rtl tool reads it: /var/rtl/testbench_mode (root-owned; after restore(), which replaces /var/rtl)."""
        self.tb_mode = mode
        sh("docker", "exec", "-u", "root", self.name, "sh", "-c", f"echo {mode} > /var/rtl/testbench_mode && chmod 644 /var/rtl/testbench_mode")

    def lock_network(self, port, helper_image="lora-netlock:dev"):
        """Egress policy of a cell (REVIEW_LOG #28): the container may open connections only to the host gateway on `port` (the recording proxy); everything else, DNS included, is rejected.
        The rules are installed from a helper container that shares this container's network namespace, so the cell container itself never has NET_ADMIN and nothing in it, root included, can change them.
        host.docker.internal is resolved before the rules and written to /etc/hosts."""
        ip = sh("docker", "exec", self.name, "sh", "-c", "getent ahostsv4 host.docker.internal | head -1 | cut -d' ' -f1").stdout.strip()
        if not ip:
            raise RuntimeError("host.docker.internal does not resolve inside the cell")
        sh("docker", "exec", "-u", "root", self.name, "sh", "-c", f"echo '{ip} host.docker.internal' >> /etc/hosts")
        rules = (f"iptables -A OUTPUT -o lo -j ACCEPT && iptables -A OUTPUT -p tcp -d {ip} --dport {int(port)} -j ACCEPT && iptables -A OUTPUT -j REJECT && "
                 f"ip6tables -A OUTPUT -o lo -j ACCEPT && ip6tables -A OUTPUT -j REJECT")
        sh("docker", "run", "--rm", "--net", f"container:{self.name}", "--cap-add", "NET_ADMIN", helper_image, "sh", "-c", rules)

    def stop(self):
        sh("docker", "rm", "-f", self.name, check=False)

    # ---- calls ---------------------------------------------------------------
    def ctl(self, *args):
        return sh("docker", "exec", "-u", "root", self.name, "/opt/rtl/ctl", *args).stdout.strip()

    def exec_root(self, *cmd, input=None, check=True):
        return sh("docker", "exec", "-i", "-u", "root", self.name, *cmd, input=input, check=check).stdout

    def put_text(self, text, dest):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
            f.write(text)
            tmp = f.name
        sh("docker", "cp", tmp, f"{self.name}:{dest}")
        sh("docker", "exec", "-u", "root", self.name, "chown", "agent:agent", dest)
        Path(tmp).unlink()

    def popen_agent(self, argv, env):
        cmd = ["docker", "exec", "-w", "/code/work"]
        for k, v in env.items():
            cmd += ["-e", f"{k}={v}"]
        return subprocess.Popen(cmd + [self.name] + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    def kill_agent(self):
        for pat in ("run_agent.py", "qwen", "fake_agent"):
            sh("docker", "exec", "-u", "root", self.name, "pkill", "-f", pat, check=False)

    def pull(self, dest):
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)
        for src, name in (("/var/rtl", "state"), ("/code/work", "work"), ("/code/rtl", "rtl")):
            tgt = dest / name
            if tgt.exists():
                import shutil
                shutil.rmtree(tgt)
            sh("docker", "cp", f"{self.name}:{src}", str(tgt), check=False)

    def ledger(self):
        return json.loads(sh("docker", "exec", "-u", "root", self.name, "cat", "/var/rtl/ledger.json").stdout)
