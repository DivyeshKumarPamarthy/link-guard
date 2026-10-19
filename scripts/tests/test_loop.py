"""Unit tests for scripts/loop.py. git and claude are faked; nothing real is called.

Run: make test-loop
"""

import json
import shutil
import tempfile
import unittest
from collections.abc import Sequence
from pathlib import Path

from scripts import loop
from scripts.loop import (
    Loop,
    Paths,
    Pick,
    Result,
    Stop,
    TaskFileError,
    choose_next,
    is_protected,
    load_patterns,
    parse_tasks,
    parse_version,
    protected_changes,
    tick_task,
)

REPO = Path(__file__).resolve().parents[2]


def tasks_file(*, g0_passed: bool = True, t11_done: bool = False, extra: str = "") -> str:
    gate = "gate: G0 passed 2026-10-19\n" if g0_passed else ""
    box = "x" if t11_done else " "
    return f"""# Tasks

## Phase A — Foundations. Gate G0: contract tagged.
{gate}
- [x] **T0.1 Skeleton (C).** Layout.
  Accept: make setup works.
  mode: auto · verify: `make setup && make test` · depends: none
- [ ] **T0.9 Docs (all).** Threat model.
  mode: human · verify: none · depends: none

## Phase B, sprint 1

- [{box}] **T1.1 Demo server (C).** Endpoints.
  Accept: smoke tests.
  mode: auto · verify: `cd demo && uv run pytest -q` · depends: T0.1
- [ ] **T1.2 URL validation (A).** SSRF.
  mode: pair · verify: `cd backend && uv run pytest tests/ssrf -q` · depends: T0.1
- [ ] **T1.5 Detection (B).** Signatures.
  Accept: every format detected.
  mode: auto · verify: `cd backend && uv run pytest tests/unit/test_detect_type.py -q` · depends: T0.1
- [ ] **T1.6 Web skeleton (C).** Screens.
  mode: auto · verify: `cd web && npm test` · depends: T1.1

## Phase B, sprint 3. Gate G1: all rows green.

- [ ] **T3.1 Router (A).** classify().
  mode: auto · verify: `make test` · depends: T1.2
{extra}"""


# --- parsing --------------------------------------------------------------------------


class ParseTests(unittest.TestCase):
    def test_sections_tasks_and_tags(self) -> None:
        sections = parse_tasks(tasks_file())
        self.assertEqual([s.gate for s in sections], ["G0", None, "G1"])
        self.assertTrue(sections[0].gate_passed)
        self.assertFalse(sections[2].gate_passed)
        t01, t09 = sections[0].tasks
        self.assertTrue(t01.done)
        self.assertEqual(t01.verify, "make setup && make test")  # backticks stripped
        self.assertEqual(t01.depends, [])
        self.assertEqual(t09.mode, "human")
        self.assertIsNone(t09.verify)  # "verify: none"
        t16 = sections[1].tasks[3]
        self.assertEqual((t16.id, t16.depends, t16.section), ("T1.6", ["T1.1"], 1))

    def test_task_text_keeps_accept_line_but_not_tag_line(self) -> None:
        t11 = parse_tasks(tasks_file())[1].tasks[0]
        self.assertIn("Accept: smoke tests.", t11.text)
        self.assertNotIn("mode:", t11.text)

    def test_gate_not_passed_without_line(self) -> None:
        self.assertFalse(parse_tasks(tasks_file(g0_passed=False))[0].gate_passed)

    def test_gate_line_for_another_gate_does_not_count(self) -> None:
        text = tasks_file(g0_passed=False).replace(
            "## Phase A — Foundations. Gate G0: contract tagged.\n",
            "## Phase A — Foundations. Gate G0: contract tagged.\ngate: G1 passed 2026-10-19\n",
        )
        self.assertFalse(parse_tasks(text)[0].gate_passed)

    def test_missing_tag_line_is_an_error(self) -> None:
        text = tasks_file().replace("  mode: human · verify: none · depends: none\n", "", 1)
        with self.assertRaisesRegex(TaskFileError, "T0.9 needs exactly one"):
            parse_tasks(text)

    def test_two_tag_lines_is_an_error(self) -> None:
        text = tasks_file().replace(
            "  mode: human · verify: none · depends: none\n",
            "  mode: human · verify: none · depends: none\n" * 2,
        )
        with self.assertRaisesRegex(TaskFileError, "found 2"):
            parse_tasks(text)

    def test_unknown_dependency_is_an_error(self) -> None:
        with self.assertRaisesRegex(TaskFileError, "unknown tasks: T9.9"):
            parse_tasks(tasks_file().replace("depends: T1.1", "depends: T9.9"))

    def test_duplicate_ids_are_an_error(self) -> None:
        dup = "- [ ] **T1.5 Again (B).** x\n  mode: auto · verify: none · depends: none\n"
        with self.assertRaisesRegex(TaskFileError, "duplicate task ids: T1.5"):
            parse_tasks(tasks_file(extra=dup))

    def test_the_real_task_file_parses(self) -> None:
        sections = parse_tasks((REPO / "docs" / "phase1-tasks.md").read_text())
        tasks = [t for s in sections for t in s.tasks]
        self.assertEqual(len(tasks), 35)
        modes = {t.id: t.mode for t in tasks}
        for pair in ("T0.4", "T0.8", "T1.2", "T1.3", "T1.4", "T2.1", "T3.3"):
            self.assertEqual(modes[pair], "pair", pair)
        for human in (
            "T0.9",
            "T0.10",
            "T0.11",
            "T4.1",
            "T4.2",
            "T4.3",
            "T4.4",
            "T4.5",
            "T4.6",
            "T4.7",
        ):
            self.assertEqual(modes[human], "human", human)

    def test_tick_task(self) -> None:
        ticked = tick_task(tasks_file(), "T1.5")
        self.assertIn("- [x] **T1.5 Detection", ticked)
        self.assertIn("- [ ] **T1.6 Web", ticked)
        with self.assertRaises(TaskFileError):
            tick_task(ticked, "T1.5")  # already ticked


# --- choosing the next task ------------------------------------------------------------


class ChooseTests(unittest.TestCase):
    def pick(self, text: str, branches: Sequence[str] = (), only: str | None = None) -> Pick | Stop:
        return choose_next(parse_tasks(text), set(branches), only)

    def test_picks_first_runnable_auto_task(self) -> None:
        choice = self.pick(tasks_file())
        assert isinstance(choice, Pick)
        self.assertEqual(choice.task.id, "T1.1")  # T0.9 human and T1.2 pair are skipped

    def test_skips_task_already_on_an_unmerged_branch(self) -> None:
        choice = self.pick(tasks_file(), ["task/T1.1"])
        assert isinstance(choice, Pick)
        self.assertEqual(choice.task.id, "T1.5")

    def test_dependency_on_unmerged_branch_is_not_done(self) -> None:
        text = tasks_file().replace("- [ ] **T1.5", "- [x] **T1.5")
        choice = self.pick(text, ["task/T1.1"])
        assert isinstance(choice, Stop)
        self.assertIn(
            "T1.6 needs T1.1, which is committed on unmerged branch task/T1.1", choice.message
        )
        self.assertIn("merge it into main first", choice.message)

    def test_stops_at_unpassed_gate(self) -> None:
        choice = self.pick(tasks_file(g0_passed=False))
        assert isinstance(choice, Stop)
        self.assertIn("Gate G0 is not passed", choice.message)
        self.assertIn("gate: G0 passed <date>", choice.message)

    def test_tasks_before_an_unpassed_gate_still_run(self) -> None:
        text = tasks_file(g0_passed=False).replace("- [x] **T0.1", "- [ ] **T0.1")
        choice = self.pick(text)
        assert isinstance(choice, Pick)
        self.assertEqual(choice.task.id, "T0.1")

    def test_stop_lists_pair_and_human_blockers(self) -> None:
        text = (
            tasks_file(t11_done=True)
            .replace("- [ ] **T1.5", "- [x] **T1.5")
            .replace("- [ ] **T1.6", "- [x] **T1.6")
        )
        text = text.replace(
            "Gate G1: all rows green.", "Gate G1: all rows green.\ngate: G1 passed x"
        )
        choice = self.pick(text)
        assert isinstance(choice, Stop)
        self.assertIn("T3.1 needs T1.2, a pair task: do it yourself first", choice.message)

    def test_nothing_left(self) -> None:
        text = tasks_file(t11_done=True)
        for tid in ("T1.5", "T1.6", "T3.1"):
            text = text.replace(f"- [ ] **{tid}", f"- [x] **{tid}")
        choice = self.pick(text)
        assert isinstance(choice, Stop)
        self.assertEqual(choice.message, "No unticked auto tasks left.")

    def test_only_runs_the_named_task(self) -> None:
        choice = self.pick(tasks_file(), only="T1.5")
        assert isinstance(choice, Pick)
        self.assertEqual(choice.task.id, "T1.5")

    def test_only_refuses_pair_human_done_unknown_and_branched(self) -> None:
        cases = {
            "T1.2": "pair task",
            "T0.9": "human task",
            "T0.1": "already ticked",
            "T7.7": "No task T7.7",
        }
        for tid, message in cases.items():
            choice = self.pick(tasks_file(), only=tid)
            assert isinstance(choice, Stop)
            self.assertIn(message, choice.message, tid)
        choice = self.pick(tasks_file(), ["task/T1.5"], only="T1.5")
        assert isinstance(choice, Stop)
        self.assertIn("already has branch", choice.message)

    def test_only_refuses_task_after_unpassed_gate(self) -> None:
        choice = self.pick(tasks_file(g0_passed=False), only="T1.5")
        assert isinstance(choice, Stop)
        self.assertIn("after gate G0", choice.message)


# --- protected paths -------------------------------------------------------------------


class ProtectedTests(unittest.TestCase):
    patterns = load_patterns((REPO / ".loop" / "protected.txt").read_text())

    def test_comments_are_ignored(self) -> None:
        self.assertNotIn("#", "".join(p[0] for p in self.patterns))
        self.assertIn("docs/phase1-tasks.md", self.patterns)

    def test_protected(self) -> None:
        for path in (
            "CLAUDE.md",
            "docs/decisions.md",
            "docs/phase1-tasks.md",
            "backend/tests/ssrf/test_table.py",
            "backend/tests/e2e/rows/test_1.py",
            ".github/workflows/ci.yml",
            ".loop/prompts/fix.md",
            "scripts/loop.py",
        ):
            self.assertTrue(is_protected(path, self.patterns), path)

    def test_not_protected(self) -> None:
        for path in (
            "backend/app/engine/detect/signatures.py",
            "docs/modules/detect.md",
            "backend/tests/unit/test_ssrf_like.py",
            "backend/tests/ssrfx/a.py",
            "scripts/tests/test_loop.py",
            "docs/loop/log.md",
            "web/src/App.tsx",
        ):
            self.assertFalse(is_protected(path, self.patterns), path)

    def test_protected_changes_lists_only_offenders(self) -> None:
        changed = ["backend/app/x.py", "docs/decisions.md", "backend/tests/ssrf/new.py"]
        self.assertEqual(
            protected_changes(changed, self.patterns),
            ["docs/decisions.md", "backend/tests/ssrf/new.py"],
        )


class VersionTests(unittest.TestCase):
    def test_parse_version(self) -> None:
        self.assertEqual(parse_version("2.1.295 (Claude Code)"), (2, 1, 295))
        self.assertIsNone(parse_version("command not found"))


# --- the loop with fake git and claude -------------------------------------------------


class FakeRunner:
    """Pretends to be git, sh and claude. Records every call."""

    def __init__(
        self,
        *,
        changed: Sequence[str] = ("backend/app/engine/detect/x.py",),
        implement: Sequence[dict[str, object] | str] = (),
        reviews: Sequence[dict[str, object]] = (),
        verify_codes: Sequence[int] = (),
        version: str = "2.1.295 (Claude Code)",
        dirty: bool = False,
        branch: str = "main",
        cost: float = 0.25,
    ) -> None:
        self.calls: list[list[str]] = []
        self.stdin: list[str | None] = []
        self.changed = list(changed)
        self.implement = list(implement)
        self.reviews = list(reviews)
        self.verify_codes = list(verify_codes)
        self.version = version
        self.dirty = dirty
        self.branch = branch
        self.branches: set[str] = set()
        self.cost = cost
        self.session_counter = 0
        self.main_files: dict[Path, str] = {}  # main's copy of the loop's files
        self.committed: dict[str, dict[str, str]] = {}  # branch -> file name -> committed text

    TRACKED = ("docs/phase1-tasks.md", "docs/loop/log.md", "docs/loop/questions.md")

    def snapshot(self, cwd: Path) -> dict[Path, str]:
        return {cwd / name: (cwd / name).read_text() for name in self.TRACKED}

    def reply(self, data: dict[str, object] | str) -> Result:
        self.session_counter += 1
        if isinstance(data, str):  # raw stdout, e.g. not JSON at all
            return Result(1, data, "boom")
        payload = {
            "type": "result",
            "is_error": False,
            "session_id": "sess-1",
            "total_cost_usd": self.cost,
            "structured_output": data,
        }
        return Result(0, json.dumps(payload))

    def __call__(
        self,
        args: Sequence[str],
        *,
        cwd: Path,
        input: str | None = None,
        timeout: float | None = None,
    ) -> Result:
        args = list(args)
        self.calls.append(args)
        self.stdin.append(input)
        if args[:2] == ["claude", "--version"]:
            return Result(0, self.version)
        if args[:2] == ["claude", "-p"]:
            if args[args.index("--permission-mode") + 1] == "dontAsk":
                return self.reply(self.reviews.pop(0))
            return self.reply(self.implement.pop(0))
        if args[:2] == ["sh", "-c"]:
            code = self.verify_codes.pop(0) if self.verify_codes else 0
            return Result(code, "verify output\n" * 300 + f"exit {code}")
        if args[:2] == ["git", "status"]:
            return Result(0, " M x\n" if self.dirty else "")
        if args[:3] == ["git", "branch", "--show-current"]:
            return Result(0, self.branch + "\n")
        if args[:3] == ["git", "branch", "--list"]:
            return Result(0, "".join(f"{b}\n" for b in sorted(self.branches)))
        if args[:3] == ["git", "switch", "-c"]:
            self.main_files = self.snapshot(cwd)  # like git: main keeps its own versions
            self.branches.add(args[3])
            self.branch = args[3]
            return Result(0, "")
        if args[:2] == ["git", "switch"]:
            if args[2] == "main":
                for path, text in self.main_files.items():
                    path.write_text(text)
            self.branch = args[2]
            return Result(0, "")
        if args[:2] == ["git", "commit"]:
            self.committed[self.branch] = {p.name: s for p, s in self.snapshot(cwd).items()}
            return Result(0, "")
        if args[:4] == ["git", "diff", "--cached", "--name-only"]:
            return Result(0, "".join(f"{c}\n" for c in self.changed))
        if args[:3] == ["git", "diff", "--cached"]:
            return Result(0, "diff --git a/x b/x\n+code\n")
        if args[:2] == ["git", "add"]:
            return Result(0, "")
        raise AssertionError(f"unexpected command: {args}")

    def claude_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["claude", "-p"]]

    def verify_calls(self) -> list[list[str]]:
        return [c for c in self.calls if c[:2] == ["sh", "-c"]]

    def commits(self) -> list[str]:
        return [c[c.index("-m") + 1] for c in self.calls if c[:2] == ["git", "commit"]]


DONE = {
    "status": "done",
    "summary": "Signature table and detect_type",
    "files_changed": ["x"],
    "questions": [],
}
APPROVE = {"verdict": "approve", "problems": []}
CHANGES = {"verdict": "changes_needed", "problems": ["x.py:3 hard-coded cap"]}


class LoopTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        (self.tmp / "docs" / "loop").mkdir(parents=True)
        shutil.copytree(REPO / ".loop", self.tmp / ".loop")
        for name in ("log.md", "questions.md"):
            shutil.copy(REPO / "docs" / "loop" / name, self.tmp / "docs" / "loop" / name)
        self.write_tasks(tasks_file())
        self.output: list[str] = []

    def write_tasks(self, text: str) -> None:
        (self.tmp / "docs" / "phase1-tasks.md").write_text(text)

    def tasks_text(self) -> str:
        return (self.tmp / "docs" / "phase1-tasks.md").read_text()

    def make_loop(self, runner: FakeRunner, budget: float = 3.0, dry_run: bool = False) -> Loop:
        return Loop(
            Paths(self.tmp), runner, budget_usd=budget, dry_run=dry_run, echo=self.output.append
        )

    def run_one(
        self, runner: FakeRunner, task_id: str = "T1.5", budget: float = 3.0
    ) -> loop.Outcome:
        sections = parse_tasks(self.tasks_text())
        task = next(t for s in sections for t in s.tasks if t.id == task_id)
        return self.make_loop(runner, budget).run_task(task)


class RunTaskTests(LoopTestCase):
    def test_happy_path_ticks_logs_commits_and_returns_to_main(self) -> None:
        runner = FakeRunner(implement=[DONE], reviews=[APPROVE], verify_codes=[0])
        outcome = self.run_one(runner)
        self.assertEqual((outcome.status, outcome.corrections), ("done", 0))
        self.assertAlmostEqual(outcome.cost_usd, 0.5)
        committed = runner.committed["task/T1.5"]
        self.assertIn("- [x] **T1.5", committed["phase1-tasks.md"])  # ticked on the branch
        self.assertIn(
            "| T1.5 | task/T1.5 | done | 0 | $0.50 | Signature table and detect_type |",
            committed["log.md"],
        )
        self.assertIn("- [ ] **T1.5", self.tasks_text())  # main is unchanged
        self.assertEqual(runner.commits(), ["T1.5: Signature table and detect_type"])
        self.assertIn(["git", "switch", "-c", "task/T1.5", "main"], runner.calls)
        self.assertEqual(runner.calls[-1], ["git", "switch", "main"])
        self.assertEqual(
            runner.verify_calls(),
            [["sh", "-c", "cd backend && uv run pytest tests/unit/test_detect_type.py -q"]],
        )
        self.assertFalse(any(c[:2] in (["git", "merge"], ["git", "push"]) for c in runner.calls))

    def test_implement_call_flags(self) -> None:
        runner = FakeRunner(implement=[DONE], reviews=[APPROVE])
        self.run_one(runner)
        implement, review = runner.claude_calls()
        prompt = implement[2]
        self.assertIn("TASK: T1.5", prompt)
        self.assertIn("Accept: every format detected.", prompt)
        self.assertIn("docs/phase1-tasks.md", prompt)  # protected list included
        self.assertEqual(implement[implement.index("--permission-mode") + 1], "acceptEdits")
        self.assertEqual(implement[implement.index("--permission-prompts") + 1], "none")
        self.assertIn("Grep,Glob", implement[implement.index("--allowedTools") + 1])
        self.assertEqual(implement[implement.index("--max-budget-usd") + 1], "3.00")
        schema = json.loads(implement[implement.index("--json-schema") + 1])
        self.assertEqual(schema["required"], ["status", "summary", "files_changed", "questions"])
        self.assertEqual(review[review.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(
            review[review.index("--allowedTools") + 1], "Read,Grep,Glob,Bash(git diff *)"
        )
        self.assertEqual(review[review.index("--max-budget-usd") + 1], "2.75")  # budget minus spent
        self.assertIn("diff --git", runner.stdin[runner.calls.index(review)] or "")

    def test_verify_failure_resumes_same_session_with_output_tail(self) -> None:
        runner = FakeRunner(implement=[DONE, DONE], reviews=[APPROVE], verify_codes=[1, 0])
        outcome = self.run_one(runner)
        self.assertEqual((outcome.status, outcome.corrections), ("done", 1))
        fix = runner.claude_calls()[1]
        self.assertEqual(fix[fix.index("--resume") + 1], "sess-1")
        self.assertIn("EXIT CODE: 1", fix[2])
        self.assertIn("Fix the code, not the tests", fix[2])
        self.assertEqual(fix[2].count("verify output"), loop.OUTPUT_TAIL_LINES - 1)  # tail only

    def test_three_failed_fixes_then_blocked(self) -> None:
        runner = FakeRunner(implement=[DONE] * 4, verify_codes=[1, 1, 1, 1])
        outcome = self.run_one(runner)
        self.assertEqual((outcome.status, outcome.corrections), ("blocked", 3))
        self.assertEqual(len(runner.verify_calls()), 4)  # first try + 3 fixes
        self.assertEqual(len(runner.claude_calls()), 4)  # implement + 3 fixes, no review
        self.assertNotIn("- [x] **T1.5", self.tasks_text())
        self.assertTrue(runner.commits()[0].startswith("WIP T1.5 (blocked)"))
        self.assertEqual(runner.calls[-1], ["git", "switch", "main"])

    def test_review_rounds_count_toward_the_same_limit(self) -> None:
        runner = FakeRunner(implement=[DONE] * 4, reviews=[CHANGES] * 4)
        outcome = self.run_one(runner)
        self.assertEqual((outcome.status, outcome.corrections), ("blocked", 3))
        fixes = runner.claude_calls()[2::2]  # implement, review, fix, review, ...
        self.assertTrue(all("x.py:3 hard-coded cap" in f[2] for f in fixes))

    def test_mixed_fix_and_review_rounds(self) -> None:
        runner = FakeRunner(
            implement=[DONE] * 3, reviews=[CHANGES, APPROVE], verify_codes=[1, 0, 0]
        )
        outcome = self.run_one(runner)
        self.assertEqual((outcome.status, outcome.corrections), ("done", 2))

    def test_needs_human_writes_questions_and_parks(self) -> None:
        ask = {
            "status": "needs_human",
            "summary": "16th format is undecided",
            "files_changed": [],
            "questions": [
                "Which is the 16th format (D15)?",
                "Proposed decision: ELF counts. Rationale: x",
            ],
        }
        runner = FakeRunner(implement=[ask])
        outcome = self.run_one(runner)
        self.assertEqual(outcome.status, "needs_human")
        questions = runner.committed["task/T1.5"]["questions.md"]
        self.assertIn("## T1.5", questions)
        self.assertIn("- **Q:** Which is the 16th format (D15)?\n  **A:** ", questions)
        self.assertIn("Proposed decision: ELF counts.", questions)
        self.assertEqual(runner.verify_calls(), [])
        self.assertTrue(runner.commits()[0].startswith("WIP T1.5 (needs_human)"))
        self.assertEqual(runner.calls[-1], ["git", "switch", "main"])

    def test_protected_path_edit_is_rejected(self) -> None:
        runner = FakeRunner(implement=[DONE], changed=["backend/app/x.py", "docs/decisions.md"])
        outcome = self.run_one(runner)
        self.assertEqual(outcome.status, "rejected")
        self.assertIn("docs/decisions.md", outcome.message)
        self.assertEqual(runner.verify_calls(), [])
        self.assertEqual(len(runner.claude_calls()), 1)  # no review
        self.assertTrue(runner.commits()[0].startswith("WIP T1.5 (rejected)"))

    def test_protected_check_runs_again_after_a_fix(self) -> None:
        class TouchesSsrfInFix(FakeRunner):
            """The fix round (second implement call) adds a file under a protected folder."""

            def __call__(self, args: Sequence[str], **kwargs: object) -> Result:
                result = super().__call__(args, **kwargs)  # type: ignore[arg-type]
                implement_calls = [
                    c
                    for c in self.claude_calls()
                    if c[c.index("--permission-mode") + 1] == "acceptEdits"
                ]
                if len(implement_calls) == 2:
                    self.changed = ["backend/tests/ssrf/test_new.py"]
                return result

        runner = TouchesSsrfInFix(implement=[DONE, DONE], verify_codes=[1])
        outcome = self.run_one(runner)
        self.assertEqual((outcome.status, outcome.corrections), ("rejected", 1))
        self.assertIn("backend/tests/ssrf/test_new.py", outcome.message)
        self.assertEqual(len(runner.verify_calls()), 1)  # no verify after the bad fix

    def test_unparseable_claude_output_blocks(self) -> None:
        runner = FakeRunner(implement=["Error: something broke"])
        outcome = self.run_one(runner)
        self.assertEqual(outcome.status, "blocked")
        self.assertIn("claude exited 1", outcome.message)

    def test_budget_is_enforced_across_calls(self) -> None:
        runner = FakeRunner(implement=[DONE, DONE], verify_codes=[1, 1], cost=2.0)
        outcome = self.run_one(runner, budget=3.0)
        # implement costs 2.00, fix call gets 1.00, costs 2.00 -> nothing left for another round
        self.assertEqual(outcome.status, "blocked")
        self.assertIn("budget is used up", outcome.message)
        self.assertAlmostEqual(outcome.cost_usd, 4.0)

    def test_task_without_verify_goes_straight_to_review(self) -> None:
        self.write_tasks(
            tasks_file().replace(
                "verify: `cd backend && uv run pytest tests/unit/test_detect_type.py -q`",
                "verify: none",
            )
        )
        runner = FakeRunner(implement=[DONE], reviews=[APPROVE])
        self.assertEqual(self.run_one(runner).status, "done")
        self.assertEqual(runner.verify_calls(), [])


class InterruptTests(LoopTestCase):
    def test_ctrl_c_mid_task_parks_the_branch_and_returns_to_main(self) -> None:
        class InterruptedVerify(FakeRunner):
            def __call__(self, args: Sequence[str], **kwargs: object) -> Result:
                if list(args[:2]) == ["sh", "-c"]:
                    raise KeyboardInterrupt
                return super().__call__(args, **kwargs)  # type: ignore[arg-type]

        runner = InterruptedVerify(implement=[DONE])
        with self.assertRaises(KeyboardInterrupt):
            self.make_loop(runner).run(1, None)
        self.assertTrue(
            runner.commits()[0].startswith("WIP T1.1 (blocked): loop stopped: interrupted")
        )
        self.assertEqual(runner.calls[-1], ["git", "switch", "main"])

    def test_review_prompt_forbids_asking_for_protected_edits(self) -> None:
        review = (REPO / ".loop" / "prompts" / "review.md").read_text()
        self.assertIn("Never ask for these", review)
        self.assertIn("docs/decisions.md", review)


class RunTests(LoopTestCase):
    def test_refuses_dirty_tree(self) -> None:
        runner = FakeRunner(dirty=True)
        self.assertEqual(self.make_loop(runner).run(3, None), 2)
        self.assertIn("working tree is not clean", self.output[-1])
        self.assertEqual(runner.claude_calls(), [])

    def test_refuses_when_not_on_main(self) -> None:
        runner = FakeRunner(branch="task/T1.1")
        self.assertEqual(self.make_loop(runner).run(3, None), 2)
        self.assertIn("Switch to main", self.output[-1])

    def test_refuses_old_claude(self) -> None:
        runner = FakeRunner(version="2.1.200 (Claude Code)")
        self.assertEqual(self.make_loop(runner).run(3, None), 2)
        self.assertIn("2.1.259 or later", self.output[-1])

    def test_runs_independent_tasks_then_stops_on_unmerged_dependency(self) -> None:
        runner = FakeRunner(implement=[DONE, DONE], reviews=[APPROVE, APPROVE])
        code = self.make_loop(runner).run(5, None)
        self.assertEqual(code, 0)
        self.assertEqual(
            runner.commits(),
            ["T1.1: Signature table and detect_type", "T1.5: Signature table and detect_type"],
        )
        # T1.6 depends on T1.1, which is only on its unmerged branch now.
        self.assertIn(
            "T1.6 needs T1.1, which is committed on unmerged branch task/T1.1", self.output[-1]
        )

    def test_max_tasks_limit(self) -> None:
        runner = FakeRunner(implement=[DONE], reviews=[APPROVE])
        self.assertEqual(self.make_loop(runner).run(1, None), 0)
        self.assertIn("reached --max-tasks 1", self.output[-1])

    def test_stops_after_a_failed_task(self) -> None:
        runner = FakeRunner(implement=["not json"])
        self.assertEqual(self.make_loop(runner).run(3, None), 1)
        self.assertIn("T1.1 is blocked", self.output[-1])

    def test_dry_run_calls_neither_claude_nor_writing_git(self) -> None:
        runner = FakeRunner()
        self.assertEqual(self.make_loop(runner, dry_run=True).run(5, None), 0)
        self.assertEqual(runner.claude_calls(), [])
        self.assertFalse(
            any(
                c[:2] in (["git", "switch"], ["git", "commit"], ["git", "add"])
                for c in runner.calls
            )
        )
        self.assertIn("[dry run] would run T1.1", self.output[0])
        self.assertIn("[dry run] would run T1.5", self.output[1])
        self.assertIn("T1.6 needs T1.1", self.output[-1])

    def test_only_one_task(self) -> None:
        runner = FakeRunner(implement=[DONE], reviews=[APPROVE])
        self.assertEqual(self.make_loop(runner).run(3, "T1.5"), 0)
        self.assertEqual(runner.commits(), ["T1.5: Signature table and detect_type"])
        self.assertIn("T1.5 is done on task/T1.5", self.output[-1])


if __name__ == "__main__":
    unittest.main()
