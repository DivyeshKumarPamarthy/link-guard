"""The loop: work through docs/phase1-tasks.md with headless Claude Code (`claude -p`).

For each runnable task it: creates branch task/<ID> from main, asks Claude to implement
the task, rejects edits to protected paths, runs the task's verify command itself, sends
failures back to the same Claude session (max 3 correction rounds), asks a separate
read-only Claude session to review the diff, and on approval ticks the box, logs the
result and commits on the branch. It never merges and never pushes: a human merges.

Python 3.12, standard library only. See docs/loop/README.md.

    uv run --no-project --python 3.12 python scripts/loop.py --dry-run
"""

import argparse
import datetime
import fnmatch
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MIN_CLAUDE_VERSION = (2, 1, 259)  # first version with --permission-prompts
MAX_CORRECTIONS = 3  # fix rounds + review rounds, per task
OUTPUT_TAIL_LINES = 200
VERIFY_TIMEOUT_S = 30 * 60
CLAUDE_TIMEOUT_S = 60 * 60

IMPLEMENT_TOOLS = (
    "Read,Edit,Write,Grep,Glob,Bash(make *),Bash(uv *),Bash(npm *),Bash(npx *),"
    "Bash(git status),Bash(git diff *)"
)
REVIEW_TOOLS = "Read,Grep,Glob,Bash(git diff *)"


# --- paths -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Paths:
    """Every file the loop reads or writes, so tests can point it at a temporary folder."""

    repo: Path

    @property
    def tasks(self) -> Path:
        return self.repo / "docs" / "phase1-tasks.md"

    @property
    def prompts(self) -> Path:
        return self.repo / ".loop" / "prompts"

    @property
    def result_schema(self) -> Path:
        return self.repo / ".loop" / "result.schema.json"

    @property
    def review_schema(self) -> Path:
        return self.repo / ".loop" / "review.schema.json"

    @property
    def protected(self) -> Path:
        return self.repo / ".loop" / "protected.txt"

    @property
    def log(self) -> Path:
        return self.repo / "docs" / "loop" / "log.md"

    @property
    def questions(self) -> Path:
        return self.repo / "docs" / "loop" / "questions.md"


# --- task file parsing ---------------------------------------------------------------


class TaskFileError(ValueError):
    """docs/phase1-tasks.md does not have the shape the loop needs."""


@dataclass
class Task:
    id: str
    text: str  # the task's own lines, for the prompt
    done: bool
    mode: str  # auto | pair | human
    verify: str | None  # shell command, or None for "verify: none"
    depends: list[str]
    section: int  # index into the section list


@dataclass
class Section:
    heading: str
    gate: str | None  # "G1" when the heading names a gate
    gate_passed: bool
    tasks: list[Task] = field(default_factory=list)


TASK_LINE = re.compile(r"^- \[(?P<box>[ x])\] \*\*(?P<id>T\d+\.\d+)\b")
TAG_LINE = re.compile(
    r"^\s+mode: (?P<mode>auto|pair|human) · verify: (?P<verify>.+?) · depends: (?P<depends>.+?)\s*$"
)
GATE_IN_HEADING = re.compile(r"\bGate (G\d+)\b")
GATE_PASSED_LINE = re.compile(r"^gate: (G\d+) passed \S+")
TASK_ID = re.compile(r"^T\d+\.\d+$")


def parse_tasks(text: str) -> list[Section]:
    """Read sections, gates and tagged tasks from the task file."""
    sections: list[Section] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            gate = GATE_IN_HEADING.search(line)
            sections.append(
                Section(
                    heading=line[3:].strip(),
                    gate=gate.group(1) if gate else None,
                    gate_passed=False,
                )
            )
        elif (passed := GATE_PASSED_LINE.match(line)) and sections:
            if passed.group(1) == sections[-1].gate:
                sections[-1].gate_passed = True
        elif match := TASK_LINE.match(line):
            if not sections:
                raise TaskFileError(f"task {match['id']} appears before any '## ' heading")
            block = [line]
            while i + 1 < len(lines) and lines[i + 1].startswith("  "):
                i += 1
                block.append(lines[i])
            tags = [m for m in (TAG_LINE.match(b) for b in block) if m]
            if len(tags) != 1:
                raise TaskFileError(
                    f"task {match['id']} needs exactly one 'mode: … · verify: … · "
                    f"depends: …' line (found {len(tags)})"
                )
            tag = tags[0]
            verify = tag["verify"].strip().strip("`")
            depends_text = tag["depends"].strip()
            depends = [] if depends_text == "none" else [d.strip() for d in depends_text.split(",")]
            for dep in depends:
                if not TASK_ID.match(dep):
                    raise TaskFileError(f"task {match['id']}: bad dependency {dep!r}")
            sections[-1].tasks.append(
                Task(
                    id=match["id"],
                    text="\n".join(b for b in block if not TAG_LINE.match(b)),
                    done=match["box"] == "x",
                    mode=tag["mode"],
                    verify=None if verify == "none" else verify,
                    depends=depends,
                    section=len(sections) - 1,
                )
            )
        i += 1
    ids = [t.id for s in sections for t in s.tasks]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise TaskFileError(f"duplicate task ids: {', '.join(duplicates)}")
    unknown = sorted({d for s in sections for t in s.tasks for d in t.depends} - set(ids))
    if unknown:
        raise TaskFileError(f"depends on unknown tasks: {', '.join(unknown)}")
    return sections


def tick_task(text: str, task_id: str) -> str:
    """Return the task file text with `task_id`'s box ticked."""
    pattern = re.compile(rf"^- \[ \] \*\*{re.escape(task_id)}\b", re.M)
    new, count = pattern.subn(f"- [x] **{task_id}", text, count=1)
    if count != 1:
        raise TaskFileError(f"could not find an unticked box for {task_id}")
    return new


# --- choosing the next task ------------------------------------------------------------


@dataclass
class Pick:
    task: Task


@dataclass
class Stop:
    message: str


def task_branch(task_id: str) -> str:
    return f"task/{task_id}"


def choose_next(
    sections: list[Section], open_branches: set[str], only: str | None = None
) -> Pick | Stop:
    """The next auto task whose dependencies are ticked on main, or why there is none.

    A task committed on an unmerged task/<ID> branch is NOT done: its box is only ticked on
    that branch. Gates: tasks after a section whose heading names a gate wait until a line
    `gate: G<n> passed <date>` is under that heading.
    """
    tasks = {t.id: t for s in sections for t in s.tasks}
    if only is not None:
        return _choose_only(sections, tasks, open_branches, only)

    waiting: list[str] = []  # why skipped auto tasks could not run
    for index, section in enumerate(sections):
        for task in section.tasks:
            if task.done or task.mode != "auto":
                continue
            if task_branch(task.id) in open_branches:
                waiting.append(
                    f"{task.id} is committed on unmerged branch "
                    f"{task_branch(task.id)}: merge it (or delete the branch) first"
                )
                continue
            blocker = _dependency_blocker(task, tasks, open_branches)
            if blocker:
                waiting.append(blocker)
                continue
            return Pick(task)
        work_after_gate = any(not t.done for later in sections[index + 1 :] for t in later.tasks)
        if section.gate and not section.gate_passed and work_after_gate:
            reasons = "".join(f"\n  - {w}" for w in waiting)
            return Stop(
                f"Gate {section.gate} is not passed ('{section.heading}'). Check its "
                f"criteria, then add 'gate: {section.gate} passed <date>' under that "
                f"heading.{reasons}"
            )
    if waiting:
        return Stop("No auto task can run:" + "".join(f"\n  - {w}" for w in waiting))
    return Stop("No unticked auto tasks left.")


def _dependency_blocker(task: Task, tasks: dict[str, Task], open_branches: set[str]) -> str | None:
    for dep_id in task.depends:
        dep = tasks[dep_id]
        if dep.done:
            continue
        if task_branch(dep_id) in open_branches:
            return (
                f"{task.id} needs {dep_id}, which is committed on unmerged branch "
                f"{task_branch(dep_id)}: merge it into main first"
            )
        if dep.mode in ("pair", "human"):
            return f"{task.id} needs {dep_id}, a {dep.mode} task: do it yourself first"
        return f"{task.id} needs {dep_id}, which is not done yet"
    return None


def _choose_only(
    sections: list[Section], tasks: dict[str, Task], open_branches: set[str], only: str
) -> Pick | Stop:
    task = tasks.get(only)
    if task is None:
        return Stop(f"No task {only} in the task file.")
    if task.done:
        return Stop(f"{only} is already ticked.")
    if task.mode != "auto":
        return Stop(f"{only} is a {task.mode} task: the loop only runs auto tasks.")
    if task_branch(only) in open_branches:
        return Stop(f"{only} already has branch {task_branch(only)}: merge or delete it first.")
    for earlier in sections[: task.section]:
        if earlier.gate and not earlier.gate_passed:
            return Stop(f"{only} comes after gate {earlier.gate}, which is not passed yet.")
    blocker = _dependency_blocker(task, tasks, open_branches)
    return Stop(blocker) if blocker else Pick(task)


# --- protected paths -------------------------------------------------------------------


def load_patterns(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def is_protected(path: str, patterns: Sequence[str]) -> bool:
    """`dir/**` protects everything under dir; other patterns are exact paths or globs."""
    for pattern in patterns:
        if pattern.endswith("/**"):
            if path.startswith(pattern[:-2]):
                return True
        elif fnmatch.fnmatchcase(path, pattern):
            return True
    return False


def protected_changes(changed: Sequence[str], patterns: Sequence[str]) -> list[str]:
    return [p for p in changed if is_protected(p, patterns)]


# --- running commands ------------------------------------------------------------------


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str = ""


Runner = Callable[..., Result]


def real_runner(
    args: Sequence[str], *, cwd: Path, input: str | None = None, timeout: float | None = None
) -> Result:
    try:
        done = subprocess.run(
            list(args),
            cwd=cwd,
            input=input,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        out = exc.stdout if isinstance(exc.stdout, str) else ""
        return Result(124, out, f"timed out after {timeout} s")
    return Result(done.returncode, done.stdout, done.stderr)


def tail(text: str, lines: int = OUTPUT_TAIL_LINES) -> str:
    return "\n".join(text.splitlines()[-lines:])


def strings(value: object) -> list[str]:
    """A JSON list of strings from Claude's structured output; anything else becomes []."""
    return [str(item) for item in value] if isinstance(value, list) else []


def parse_version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(x) for x in match.groups()) if match else None


# --- the per-task loop --------------------------------------------------------------------


@dataclass
class Outcome:
    task_id: str
    status: str  # done | blocked | needs_human | rejected
    message: str
    corrections: int = 0
    cost_usd: float = 0.0


@dataclass
class ClaudeReply:
    ok: bool
    data: dict[str, object]
    session_id: str | None
    cost_usd: float
    error: str = ""


class Loop:
    def __init__(
        self,
        paths: Paths,
        run: Runner,
        budget_usd: float,
        verbose: bool = False,
        dry_run: bool = False,
        echo: Callable[[str], None] = print,
    ) -> None:
        self.paths = paths
        self.run_cmd = run
        self.budget_usd = budget_usd
        self.verbose = verbose
        self.dry_run = dry_run
        self.echo = echo

    # helpers ------------------------------------------------------------------------

    def sh(
        self, args: Sequence[str], *, input: str | None = None, timeout: float | None = None
    ) -> Result:
        if self.verbose:
            self.echo("$ " + " ".join(args))
        return self.run_cmd(args, cwd=self.paths.repo, input=input, timeout=timeout)

    def git(self, *args: str) -> Result:
        result = self.sh(["git", *args])
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result

    def open_branches(self) -> set[str]:
        out = self.sh(["git", "branch", "--list", "task/*", "--format=%(refname:short)"]).stdout
        return {line.strip() for line in out.splitlines() if line.strip()}

    def check_start(self) -> str | None:
        """Refuse to start on a dirty tree or off main. Returns the reason, or None."""
        if self.sh(["git", "status", "--porcelain"]).stdout.strip():
            return "The working tree is not clean. Commit or stash your changes first."
        branch = self.sh(["git", "branch", "--show-current"]).stdout.strip()
        if branch != "main":
            return f"You are on '{branch}'. Switch to main first."
        return None

    def check_claude_version(self) -> str | None:
        result = self.sh(["claude", "--version"])
        version = parse_version(result.stdout) if result.returncode == 0 else None
        if version is None:
            return "Could not run 'claude --version'. Is Claude Code installed and on PATH?"
        if version < MIN_CLAUDE_VERSION:
            need = ".".join(map(str, MIN_CLAUDE_VERSION))
            have = ".".join(map(str, version))
            return (
                f"Claude Code {have} is too old: the loop needs {need} or later "
                "(--permission-prompts). Update Claude Code and try again."
            )
        return None

    def claude(
        self,
        prompt: str,
        *,
        tools: str,
        mode: str,
        schema: Path,
        budget: float,
        resume: str | None = None,
        stdin: str | None = None,
    ) -> ClaudeReply:
        if budget <= 0:
            return ClaudeReply(False, {}, resume, 0.0, "the task's budget is used up")
        args = [
            "claude",
            "-p",
            prompt,
            "--permission-mode",
            mode,
            "--allowedTools",
            tools,
            "--permission-prompts",
            "none",
            "--max-budget-usd",
            f"{budget:.2f}",
            "--output-format",
            "json",
            "--json-schema",
            schema.read_text(),
        ]
        if resume:
            args += ["--resume", resume]
        result = self.sh(args, input=stdin, timeout=CLAUDE_TIMEOUT_S)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return ClaudeReply(
                False,
                {},
                None,
                0.0,
                f"claude exited {result.returncode}: {tail(result.stderr, 20)}",
            )
        cost = float(payload.get("total_cost_usd") or 0.0)
        session = payload.get("session_id")
        data = payload.get("structured_output")
        if not isinstance(data, dict) and isinstance(payload.get("result"), str):
            try:
                data = json.loads(payload["result"])
            except json.JSONDecodeError:
                data = None
        if payload.get("is_error") or not isinstance(data, dict):
            reason = payload.get("subtype") or payload.get("result") or "no structured output"
            return ClaudeReply(False, {}, session, cost, f"claude did not finish: {reason}")
        return ClaudeReply(True, data, session, cost)

    def prompt(self, name: str) -> str:
        return (self.paths.prompts / f"{name}.md").read_text()

    def staged_changes(self) -> list[str]:
        """Every path changed on this branch compared with main, new files included."""
        self.git("add", "-A")
        out = self.git("diff", "--cached", "--name-only", "main").stdout
        return [line for line in out.splitlines() if line]

    def append(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)

    def log_line(self, outcome: Outcome, branch: str) -> None:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        summary = " ".join(outcome.message.split()).replace("|", "/")
        self.append(
            self.paths.log,
            f"| {now} | {outcome.task_id} | {branch} | {outcome.status} | "
            f"{outcome.corrections} | ${outcome.cost_usd:.2f} | {summary} |\n",
        )

    def write_questions(self, task: Task, summary: str, questions: Sequence[str]) -> None:
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        items = (
            "".join(f"- **Q:** {q}\n  **A:** \n" for q in questions) or "- (no questions given)\n"
        )
        self.append(
            self.paths.questions,
            f"\n## {task.id} · {now} · branch {task_branch(task.id)}\n\n{summary}\n\n{items}",
        )

    def park(self, task: Task, outcome: Outcome) -> Outcome:
        """Leave the branch with everything committed on it, log, and go back to main."""
        branch = task_branch(task.id)
        self.log_line(outcome, branch)
        self.git("add", "-A")
        self.git(
            "commit",
            "--allow-empty",
            "-m",
            f"WIP {task.id} ({outcome.status}): {outcome.message[:72]}",
        )
        self.git("switch", "main")
        return outcome

    # one task -------------------------------------------------------------------------

    def run_task(self, task: Task) -> Outcome:
        patterns = load_patterns(self.paths.protected.read_text())
        branch = task_branch(task.id)
        self.git("switch", "-c", branch, "main")
        spent = 0.0

        def remaining() -> float:
            return self.budget_usd - spent

        verify_line = task.verify or "(none)"
        implement = (
            f"{self.prompt('implement')}\n\nTASK: {task.id}\n\n{task.text}\n\n"
            f"VERIFY COMMAND (the loop runs it after you finish): {verify_line}\n\n"
            f"PROTECTED PATHS (never edit):\n{chr(10).join(patterns)}\n"
        )
        reply = self.claude(
            implement,
            tools=IMPLEMENT_TOOLS,
            mode="acceptEdits",
            schema=self.paths.result_schema,
            budget=remaining(),
        )
        spent += reply.cost_usd
        session = reply.session_id
        corrections = 0

        while True:
            if not reply.ok:
                return self.park(task, Outcome(task.id, "blocked", reply.error, corrections, spent))
            status = str(reply.data.get("status", ""))
            summary = str(reply.data.get("summary", "")).strip() or "(no summary)"
            if status in ("blocked", "needs_human"):
                questions = strings(reply.data.get("questions"))
                self.write_questions(task, summary, questions)
                return self.park(
                    task,
                    Outcome(
                        task.id,
                        status,
                        f"{summary} (questions in docs/loop/questions.md)",
                        corrections,
                        spent,
                    ),
                )

            # 5. protected paths
            touched = protected_changes(self.staged_changes(), patterns)
            if touched:
                return self.park(
                    task,
                    Outcome(
                        task.id,
                        "rejected",
                        "edited protected paths: " + ", ".join(touched),
                        corrections,
                        spent,
                    ),
                )

            # 6. verify, run by the loop itself
            feedback: str | None = None
            if task.verify:
                result = self.sh(["sh", "-c", task.verify], timeout=VERIFY_TIMEOUT_S)
                if result.returncode != 0:
                    output = tail(result.stdout + "\n" + result.stderr)
                    feedback = (
                        f"{self.prompt('fix')}\n\nVERIFY COMMAND: {task.verify}\n"
                        f"EXIT CODE: {result.returncode}\n\nOUTPUT (last "
                        f"{OUTPUT_TAIL_LINES} lines):\n{output}\n"
                    )

            # 7. review, a separate read-only session
            if feedback is None:
                diff = self.git("diff", "--cached", "main").stdout
                review_prompt = (
                    f"{self.prompt('review')}\n\nTASK: {task.id}\n\n{task.text}\n\n"
                    "The diff against main is on standard input."
                )
                review = self.claude(
                    review_prompt,
                    tools=REVIEW_TOOLS,
                    mode="dontAsk",
                    schema=self.paths.review_schema,
                    budget=remaining(),
                    stdin=diff,
                )
                spent += review.cost_usd
                if not review.ok:
                    return self.park(
                        task,
                        Outcome(
                            task.id, "blocked", f"review failed: {review.error}", corrections, spent
                        ),
                    )
                if review.data.get("verdict") == "approve":
                    return self.finish(task, Outcome(task.id, "done", summary, corrections, spent))
                problems = strings(review.data.get("problems"))
                feedback = f"{self.prompt('fix')}\n\nThe reviewer asked for changes:\n" + "".join(
                    f"- {p}\n" for p in problems
                )

            # a correction round (fix or review); max MAX_CORRECTIONS per task
            corrections += 1
            if corrections > MAX_CORRECTIONS:
                return self.park(
                    task,
                    Outcome(
                        task.id,
                        "blocked",
                        f"still failing after {MAX_CORRECTIONS} correction rounds",
                        MAX_CORRECTIONS,
                        spent,
                    ),
                )
            reply = self.claude(
                feedback,
                tools=IMPLEMENT_TOOLS,
                mode="acceptEdits",
                schema=self.paths.result_schema,
                budget=remaining(),
                resume=session,
            )
            spent += reply.cost_usd
            session = reply.session_id or session

    def finish(self, task: Task, outcome: Outcome) -> Outcome:
        """Approved: tick the box, log, commit on the branch, go back to main. Never merge."""
        self.paths.tasks.write_text(tick_task(self.paths.tasks.read_text(), task.id))
        self.log_line(outcome, task_branch(task.id))
        self.git("add", "-A")
        self.git("commit", "-m", f"{task.id}: {outcome.message[:72]}")
        self.git("switch", "main")
        return outcome

    # the whole run ----------------------------------------------------------------------

    def run(self, max_tasks: int, only: str | None) -> int:
        if not self.dry_run:
            problem = self.check_claude_version()
            if problem:
                self.echo(f"STOP: {problem}")
                return 2
        problem = self.check_start()
        if problem:
            self.echo(f"STOP: {problem}")
            return 2

        simulated_branches: set[str] = set()  # dry run: tasks it would have committed
        for _ in range(max_tasks):
            sections = parse_tasks(self.paths.tasks.read_text())
            choice = choose_next(sections, self.open_branches() | simulated_branches, only)
            if isinstance(choice, Stop):
                self.echo(f"STOP: {choice.message}")
                return 0
            task = choice.task
            if self.dry_run:
                self.echo(
                    f"[dry run] would run {task.id} on branch {task_branch(task.id)}; "
                    f"verify: {task.verify or '(none)'}"
                )
                simulated_branches.add(task_branch(task.id))
                if only:
                    return 0
                continue
            self.echo(f"--- {task.id}: starting on {task_branch(task.id)}")
            outcome = self.run_task(task)
            self.echo(
                f"--- {task.id}: {outcome.status} after {outcome.corrections} correction "
                f"round(s), ${outcome.cost_usd:.2f}: {outcome.message}"
            )
            if outcome.status != "done":
                self.echo(
                    f"STOP: {task.id} is {outcome.status}. Branch {task_branch(task.id)} "
                    "is left for you; see docs/loop/README.md."
                )
                return 1
            if only:
                self.echo(
                    f"STOP: {task.id} is done on {task_branch(task.id)}. Review and merge it."
                )
                return 0
        self.echo(
            f"STOP: reached --max-tasks {max_tasks}. Review and merge the task/* branches; "
            "tasks that depend on them stay blocked until they are merged into main."
        )
        return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run LinkGuard tasks with headless Claude Code.")
    parser.add_argument("--max-tasks", type=int, default=3, help="stop after N tasks (default 3)")
    parser.add_argument("--task", help="run only this task id, e.g. T1.5")
    parser.add_argument("--budget", type=float, default=3.0, help="USD per task (default 3)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would happen; no Claude calls, no git changes",
    )
    parser.add_argument("--verbose", action="store_true", help="print every command")
    args = parser.parse_args(argv)
    if args.task and not TASK_ID.match(args.task):
        parser.error("--task must look like T1.5")
    loop = Loop(
        Paths(REPO), real_runner, budget_usd=args.budget, verbose=args.verbose, dry_run=args.dry_run
    )
    try:
        return loop.run(args.max_tasks, args.task)
    except (TaskFileError, RuntimeError) as exc:
        print(f"STOP: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
