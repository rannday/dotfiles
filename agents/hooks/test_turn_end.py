import json
import os
import shutil
import tempfile
import unittest
from io import StringIO

import turn_end


class ReviewTests(unittest.TestCase):
  def test_review_uses_api_key_and_fake_runner(self):
    root = self._dirty_note()
    seen = {}
    def fake(prompt, env, cwd):
      seen['prompt'] = prompt
      seen['child'] = env.get('TURN_END_CHILD')
      seen['key'] = env.get('XAI_API_KEY')
      return 'No issues.\n', None
    previous = turn_end.run_review
    turn_end.run_review = fake
    self.addCleanup(setattr, turn_end, 'run_review', previous)
    previous_key = os.environ.get('XAI_API_KEY')
    os.environ['XAI_API_KEY'] = 'test-key'
    def restore_key():
      if previous_key is None:
        os.environ.pop('XAI_API_KEY', None)
      else:
        os.environ['XAI_API_KEY'] = previous_key
    self.addCleanup(restore_key)
    out, err = StringIO(), StringIO()
    code = turn_end.run(['review'], StringIO(event_json(root, session='rev', prompt='1', cwd=root)), out, err)
    self.assertEqual(code, 0, err.getvalue())
    self.assertEqual(out.getvalue(), '')
    self.assertEqual(seen['child'], '1')
    self.assertEqual(seen['key'], 'test-key')
    self.assertIn('notes.txt', seen['prompt'])
    self.assertNotIn('test-key', out.getvalue())

  def test_review_blocks_on_finding(self):
    root = self._dirty_note()
    def fake(prompt, env, cwd):
      return 'notes.txt:L1: bug. fix.\n', None
    previous = turn_end.run_review
    turn_end.run_review = fake
    self.addCleanup(setattr, turn_end, 'run_review', previous)
    os.environ['XAI_API_KEY'] = 'test-key'
    self.addCleanup(os.environ.pop, 'XAI_API_KEY', None)
    out, err = StringIO(), StringIO()
    code = turn_end.run(['review'], StringIO(event_json(root, session='rev', prompt='1', cwd=root)), out, err)
    self.assertEqual(code, 0, err.getvalue())
    self.assertIn('notes.txt:L1: bug. fix.', out.getvalue())
    self.assertNotIn('test-key', out.getvalue())

  def _dirty_note(self) -> str:
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    git_init(root)
    path = os.path.join(root, 'notes.txt')
    write(path, 'ok\n')
    git(root, 'add', 'notes.txt')
    git(root, 'commit', '-m', 'init')
    event = turn_end.Event(session_id='rev', prompt_id='1', workspace_root=root, cwd=root)
    self.assertEqual(turn_end.write_snapshot(root, event, StringIO()), 0)
    write(path, 'changed\n')
    return root

  def test_subagent_skips_review(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    git_init(root)
    path = os.path.join(root, 'notes.txt')
    write(path, 'ok\n')
    git(root, 'add', 'notes.txt')
    git(root, 'commit', '-m', 'init')
    event = turn_end.Event(session_id='rev', prompt_id='1', workspace_root=root, cwd=root)
    self.assertEqual(turn_end.write_snapshot(root, event, StringIO()), 0)
    write(path, 'changed\n')
    previous_hook = os.environ.get('GROK_HOOK_EVENT')
    os.environ['GROK_HOOK_EVENT'] = 'subagent_stop'
    def restore():
      if previous_hook is None:
        os.environ.pop('GROK_HOOK_EVENT', None)
      else:
        os.environ['GROK_HOOK_EVENT'] = previous_hook
    self.addCleanup(restore)
    out, err = StringIO(), StringIO()
    code = turn_end.run(['review'], StringIO(event_json(root, session='rev', prompt='1', cwd=root)), out, err)
    self.assertEqual(code, 0, err.getvalue())
    self.assertEqual(out.getvalue(), '')

  def test_child_env_skips_gates(self):
    previous = os.environ.get('TURN_END_CHILD')
    os.environ['TURN_END_CHILD'] = '1'
    def restore():
      if previous is None:
        os.environ.pop('TURN_END_CHILD', None)
      else:
        os.environ['TURN_END_CHILD'] = previous
    self.addCleanup(restore)
    for mode in ('format', 'test', 'review'):
      out, err = StringIO(), StringIO()
      code = turn_end.run([mode], StringIO('{"reason":"end_turn"}'), out, err)
      self.assertEqual(code, 0, mode)
      self.assertEqual(out.getvalue(), '', mode)


class ModuleTests(unittest.TestCase):
  def test_modules_touched(self):
    root = make_temp(self)
    module = os.path.join(root, 'svc')
    os.makedirs(os.path.join(module, 'pkg'))
    write(os.path.join(module, 'go.mod'), 'module example\n\ngo 1.21\n')
    got = turn_end.modules_touched(root, [turn_end.Change(path='svc/pkg/page.go')])
    self.assertEqual(len(got), 1)
    self.assertEqual(got[0].pkgs, ['./pkg'])
    all_pkgs = turn_end.modules_touched(root, [turn_end.Change(path='svc/go.mod')])
    self.assertEqual(len(all_pkgs), 1)
    self.assertEqual(all_pkgs[0].pkgs, ['./...'])
    self.assertEqual(turn_end.modules_touched(root, [turn_end.Change(path='notes.txt')]), [])
    hook_mod = os.path.join(root, 'cmd', 'stop-hook')
    os.makedirs(hook_mod)
    write(os.path.join(hook_mod, 'go.mod'), 'module example.com/hook\n\ngo 1.21\n')
    hooked = turn_end.modules_touched(root, [turn_end.Change(path='cmd/stop-hook/go.mod')])
    self.assertEqual(len(hooked), 1)
    self.assertEqual(hooked[0].pkgs, ['./...'])

  def test_snapshot_path_generic(self):
    path = turn_end.snapshot_path(r'C:\repo', turn_end.Event(session_id='s', prompt_id='p'))
    lower = path.lower()
    self.assertNotIn('searx', lower)
    self.assertNotIn('web-search', path)
    self.assertIn('stophook', path)

  def test_parse_porcelain_rename(self):
    blob = b' M page.go\x00R  old.go\x00new.go\x00?? extra.go\x00'
    got = turn_end.parse_porcelain(blob)
    self.assertEqual(got, ['page.go', 'new.go', 'old.go', 'extra.go'])


class TurnTests(unittest.TestCase):
  def test_turn_edit_only(self):
    root = make_temp(self)
    git_init(root)
    write(os.path.join(root, 'page.go'), 'package main\n')
    git(root, 'add', 'page.go')
    git(root, 'commit', '-m', 'init')
    write(os.path.join(root, 'page.go'), 'package main\n\nfunc dirty() {}\n')
    event = turn_end.Event(session_id='sess', prompt_id='prompt', workspace_root=root)
    self.assertEqual(turn_end.write_snapshot(root, event, StringIO()), 0)
    changes = turn_end.load_changes(root, event)
    self.assertEqual(changes, [])
    write(os.path.join(root, 'page.go'), 'package main\n\nfunc dirty() {}\n\nfunc added() {}\n')
    changes = turn_end.load_changes(root, event)
    self.assertEqual(len(changes), 1)
    self.assertEqual(changes[0].path, 'page.go')
    self.assertIn('func added', changes[0].after)
    self.assertIn('func dirty', changes[0].before)

  def test_shutdown_skips(self):
    out, err = StringIO(), StringIO()
    code = turn_end.run(['test'], StringIO('{"reason":"shutdown"}'), out, err)
    self.assertEqual(code, 0)
    self.assertEqual(out.getvalue(), '')

  def test_stop_observe_reason_skips(self):
    previous = os.environ.get('GROK_HOOK_EVENT')
    os.environ['GROK_HOOK_EVENT'] = 'stop'
    def restore():
      if previous is None:
        os.environ.pop('GROK_HOOK_EVENT', None)
      else:
        os.environ['GROK_HOOK_EVENT'] = previous
    self.addCleanup(restore)
    out, err = StringIO(), StringIO()
    code = turn_end.run(['test'], StringIO('{"reason":"max_turns"}'), out, err)
    self.assertEqual(code, 0)
    self.assertEqual(out.getvalue(), '')
    self.assertTrue(turn_end.skip_gate('test', turn_end.Event(reason='max_turns')))
    self.assertFalse(turn_end.skip_gate('test', turn_end.Event(reason='end_turn')))
    self.assertFalse(turn_end.skip_gate('test', turn_end.Event(reason='')))
    self.assertFalse(turn_end.skip_gate('snapshot', turn_end.Event(reason='max_turns')))
    os.environ['GROK_HOOK_EVENT'] = 'subagent_stop'
    self.assertFalse(turn_end.skip_gate('review', turn_end.Event(reason='max_turns')))

  def test_skip_non_git(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    out, err = StringIO(), StringIO()
    code = turn_end.run(['review'], StringIO(event_json(root)), out, err)
    self.assertEqual(code, 0)
    self.assertEqual(out.getvalue(), '')

  def test_text_edit_skips_go_tools(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    git_init(root)
    path = os.path.join(root, 'notes.txt')
    write(path, 'ok\n')
    git(root, 'add', 'notes.txt')
    git(root, 'commit', '-m', 'init')
    event = turn_end.Event(session_id='txt', prompt_id='1', workspace_root=root, cwd=root)
    self.assertEqual(turn_end.write_snapshot(root, event, StringIO()), 0)
    write(path, 'changed\n')
    def boom(name):
      raise AssertionError(name)
    previous_which = turn_end.shutil.which
    turn_end.shutil.which = boom
    self.addCleanup(setattr, turn_end.shutil, 'which', previous_which)
    payload = event_json(root, session='txt', prompt='1', cwd=root)
    for mode in ('format', 'test'):
      out, err = StringIO(), StringIO()
      code = turn_end.run([mode], StringIO(payload), out, err)
      self.assertEqual(code, 0, err.getvalue())
      self.assertEqual(out.getvalue(), '')

  def test_go_outside_module_checks_without_test(self):
    root = make_temp(self)
    changes = [turn_end.Change(path='page.go', after='package main\n')]
    self.assertEqual(turn_end.test_cmds(root, changes), [])
    checks = turn_end.gopls_cmds(root, changes)
    self.assertEqual(len(checks), 1)
    self.assertEqual(checks[0][:3], ['gopls', 'check', '-severity=warning'])

  def test_missing_gopls_blocks_only_go(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    git_init(root)
    write(os.path.join(root, 'page.go'), 'package main\n')
    git(root, 'add', 'page.go')
    git(root, 'commit', '-m', 'init')
    event = turn_end.Event(session_id='gopls', prompt_id='1', workspace_root=root, cwd=root)
    self.assertEqual(turn_end.write_snapshot(root, event, StringIO()), 0)
    write(os.path.join(root, 'page.go'), 'package main\n\nfunc added() {}\n')
    previous_which = turn_end.shutil.which
    turn_end.shutil.which = lambda name: None
    self.addCleanup(setattr, turn_end.shutil, 'which', previous_which)
    out, err = StringIO(), StringIO()
    code = turn_end.run(['test'], StringIO(event_json(root, session='gopls', prompt='1', cwd=root)), out, err)
    self.assertEqual(code, 0, err.getvalue())
    self.assertIn('gopls is not on PATH', out.getvalue())

  @unittest.skipUnless(shutil.which('gofmt'), 'gofmt is not on PATH')
  def test_format_blocks_rewrite(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    git_init(root)
    path = os.path.join(root, 'page.go')
    write(path, 'package main\n')
    git(root, 'add', 'page.go')
    git(root, 'commit', '-m', 'init')
    event = turn_end.Event(session_id='fmt', prompt_id='1', workspace_root=root, cwd=root)
    self.assertEqual(turn_end.write_snapshot(root, event, StringIO()), 0)
    write(path, 'package main\nfunc  x( ){ }\n')
    out, err = StringIO(), StringIO()
    code = turn_end.run(['format'], StringIO(event_json(root, session='fmt', prompt='1', cwd=root)), out, err)
    self.assertEqual(code, 0, err.getvalue())
    text = out.getvalue()
    self.assertIn('"decision":"block"', text)
    self.assertIn('gofmt rewrote', text)
    with open(path, 'rb') as handle:
      self.assertNotIn(b'func  x', handle.read())

  def test_no_snapshot_skips(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    git_init(root)
    out, err = StringIO(), StringIO()
    code = turn_end.run(
      ['review'],
      StringIO(event_json(root, session='missing', prompt='none')),
      out,
      err,
    )
    self.assertEqual(code, 0)
    self.assertEqual(out.getvalue(), '')

def make_temp(test: unittest.TestCase) -> str:
  return test.enterContext(tempfile.TemporaryDirectory(ignore_cleanup_errors=True))


def write(path: str, body: str) -> None:
  with open(path, 'w', encoding='utf-8', newline='\n') as handle:
    handle.write(body)


def git_init(root: str) -> None:
  git(root, 'init')
  git(root, 'config', 'user.email', 'hook@example.com')
  git(root, 'config', 'user.name', 'hook')
  git(root, 'config', 'core.autocrlf', 'false')
  git(root, 'config', 'commit.gpgsign', 'false')


def git(root: str, *args: str) -> None:
  turn_end.git(root, *args)


def event_json(root: str, session: str = 's', prompt: str = 'p', cwd: str | None = None) -> str:
  payload = {
    'sessionId': session,
    'promptId': prompt,
    'workspaceRoot': root,
  }
  if cwd is not None:
    payload['cwd'] = cwd
  return json.dumps(payload)


class ReviewPromptTests(unittest.TestCase):
  def test_small_diff_lists_file_and_hunk(self):
    prompt = turn_end.review_prompt([
      turn_end.Change(path='a.go', before='func old()\n', after='func new()\n'),
    ])
    self.assertIn('Files: a.go', prompt)
    self.assertIn('func new()', prompt)
    self.assertNotIn('Omitted:', prompt)
    self.assertNotIn('Truncated:', prompt)

  def test_per_file_cap_keeps_later_file(self):
    big = 'x\n' * (turn_end.REVIEW_FILE_CAP + 40)
    prompt = turn_end.review_prompt([
      turn_end.Change(path='big.go', before='', after=big),
      turn_end.Change(path='late.go', before='a\n', after='late-marker\n'),
    ])
    self.assertIn('Files: big.go, late.go', prompt)
    self.assertIn('Truncated: big.go', prompt)
    self.assertIn('big.go hunks omitted', prompt)
    self.assertIn('late-marker', prompt)
    self.assertNotIn('Omitted:', prompt)

  def test_budget_names_omitted_paths(self):
    previous_cap = turn_end.REVIEW_CAP
    previous_file = turn_end.REVIEW_FILE_CAP
    turn_end.REVIEW_CAP = 40
    turn_end.REVIEW_FILE_CAP = 200
    self.addCleanup(setattr, turn_end, 'REVIEW_CAP', previous_cap)
    self.addCleanup(setattr, turn_end, 'REVIEW_FILE_CAP', previous_file)
    prompt = turn_end.review_prompt([
      turn_end.Change(path='a.go', before='a\n', after='aa\n'),
      turn_end.Change(path='b.go', before='b\n', after='bb-marker\n'),
    ])
    self.assertIn('Files: a.go, b.go', prompt)
    self.assertIn('Omitted: b.go', prompt)
    self.assertNotIn('bb-marker', prompt)
    self.assertIn('aa', prompt)

  def test_large_file_diff_and_later_file_are_complete(self):
    big = ''.join(f'large-line-{index:04d}\n' for index in range(400))
    changes = [
      turn_end.Change(path='big.go', before='', after=big),
      turn_end.Change(path='late.go', before='a\n', after='late-marker\n'),
    ]
    expected = ''.join(turn_end.change_diff(change) for change in changes)
    self.assertGreater(len(turn_end.change_diff(changes[0])), 3000)
    prompt = turn_end.review_prompt(changes, complete=True)
    self.assertIn('Files: big.go, late.go', prompt)
    self.assertTrue(prompt.endswith(expected))
    self.assertIn('+large-line-0399\n', prompt)
    self.assertIn('+late-marker\n', prompt)
    self.assertNotIn('Truncated:', prompt)
    self.assertNotIn('Omitted:', prompt)

  def test_multiple_large_diffs_exceeding_old_budget_are_complete(self):
    changes = [
      turn_end.Change(
        path=f'file-{number}.go',
        before='old-marker\n',
        after=''.join(f'file-{number}-line-{index:04d}\n' for index in range(400)),
      )
      for number in range(4)
    ]
    diffs = [turn_end.change_diff(change) for change in changes]
    self.assertTrue(all(len(diff) > 3000 for diff in diffs))
    expected = ''.join(diffs)
    self.assertGreater(len(expected), 12000)
    prompt = turn_end.review_prompt(changes, complete=True)
    self.assertTrue(prompt.endswith(expected))
    for number in range(4):
      self.assertIn(f'+file-{number}-line-0399\n', prompt)
    self.assertNotIn('Truncated:', prompt)
    self.assertNotIn('Omitted:', prompt)

  def test_deleted_text_file_has_full_deletion_diff(self):
    for complete in (False, True):
      with self.subTest(complete=complete):
        prompt = turn_end.review_prompt([
          turn_end.Change(path='gone.go', before='first\nsecond\n', after='', after_deleted=True),
        ], complete=complete)
        self.assertIn('Files: gone.go', prompt)
        self.assertIn('--- gone.go\n+++ /dev/null\n', prompt)
        self.assertIn('-first\n-second\n', prompt)
        self.assertNotIn('binary', prompt)

  def test_deleted_binary_file_still_omits_content(self):
    prompt = turn_end.review_prompt([
      turn_end.Change(path='gone.bin', before='private\0data', after='', after_deleted=True),
    ], complete=True)
    self.assertIn('gone.bin: binary diff omitted', prompt)
    self.assertNotIn('private', prompt)


if __name__ == '__main__':
  unittest.main()
