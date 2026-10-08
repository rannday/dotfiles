import json
import os
import shutil
import tempfile
import unittest
from io import StringIO
from unittest.mock import patch

import turn_end


class ModuleTests(unittest.TestCase):
  def test_protected_paths_never_read_by_snapshot(self):
    root = make_temp(self)
    with patch.object(turn_end, 'git', return_value=b'?? .env\0?? keys/server.pem\0?? notes.txt\0'), patch.object(turn_end, 'read_bytes', return_value=b'notes') as read:
      files = turn_end.capture(root, protect_secrets=True)
      self.assertEqual(list(files), ['notes.txt'])
      read.assert_called_once_with(os.path.join(root, 'notes.txt'))

  def test_stale_snapshot_cannot_restore_protected_reads(self):
    snapshot = turn_end.Snapshot(files={'.env': turn_end.FileState(hash='old'), 'key.pem': turn_end.FileState(hash='old')})
    for client in ('grok', 'antigravity'):
      with self.subTest(client=client), patch.object(turn_end, 'read_snapshot', return_value=snapshot), patch.object(turn_end, 'capture', return_value={}), patch.object(turn_end, 'worktree_state') as read:
        self.assertEqual(turn_end.load_changes('fixture', turn_end.Event(client=client)), [])
        read.assert_not_called()

  def test_child_env_skips_gates(self):
    previous = os.environ.get('TURN_END_CHILD')
    os.environ['TURN_END_CHILD'] = '1'
    def restore():
      if previous is None:
        os.environ.pop('TURN_END_CHILD', None)
      else:
        os.environ['TURN_END_CHILD'] = previous
    self.addCleanup(restore)
    for mode in ('format', 'test'):
      out, err = StringIO(), StringIO()
      code = turn_end.run([mode], StringIO('{"reason":"end_turn"}'), out, err)
      self.assertEqual(code, 0, mode)
      self.assertEqual(out.getvalue(), '', mode)

  def test_review_mode_is_not_available(self):
    out, err = StringIO(), StringIO()
    code = turn_end.run(['review'], StringIO('{}'), out, err)
    self.assertEqual(code, 1)
    self.assertNotIn('|review', err.getvalue())

  def test_malformed_snapshot_shapes_report_errors(self):
    shapes = [
      [],
      {'files': []},
      {'prompt': 1},
      {'files': {'page.go': []}},
      {'files': {'page.go': {'hash': []}}},
      {'files': {'page.go': {'content': {}}}},
      {'files': {'page.go': {'deleted': 'false'}}},
    ]
    for raw in shapes:
      with self.subTest(raw=raw), patch.object(turn_end, 'read_bytes', return_value=json.dumps(raw).encode()):
        with self.assertRaisesRegex(OSError, 'parse snapshot:'):
          turn_end.read_snapshot('fixture', turn_end.Event())

  def test_valid_snapshot_shape_preserves_file_state(self):
    raw = {'files': {'page.go': {'hash': 'digest', 'content': 'package main\n', 'deleted': False}}, 'prompt': 'task'}
    with patch.object(turn_end, 'read_bytes', return_value=json.dumps(raw).encode()):
      snapshot = turn_end.read_snapshot('fixture', turn_end.Event())
    self.assertEqual(snapshot.prompt, 'task')
    self.assertEqual(snapshot.files['page.go'].content, 'package main\n')
    self.assertFalse(snapshot.files['page.go'].deleted)

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
  def test_nested_cwd_edit_requires_validation(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    git_init(root)
    nested = os.path.join(root, 'svc', 'pkg')
    os.makedirs(nested)
    path = os.path.join(nested, 'page.go')
    write(os.path.join(root, 'svc', 'go.mod'), 'module example\n\ngo 1.21\n')
    write(path, 'package pkg\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'init')
    for client in ('', 'codex', 'antigravity'):
      for dirty in (False, True):
        with self.subTest(client=client, dirty=dirty), patch.dict(os.environ):
          os.environ.pop('GROK_WORKSPACE_ROOT', None)
          os.environ.pop('CLAUDE_PROJECT_DIR', None)
          before = 'package pkg\n' + ('\nfunc dirty() {}\n' if dirty else '')
          write(path, before)
          payload = json.dumps({
            'sessionId': 'nested-' + client,
            'promptId': str(dirty),
            'cwd': nested,
            'client': client,
          })
          out, err = StringIO(), StringIO()
          self.assertEqual(turn_end.run(['snapshot'], StringIO(payload), out, err), 0, err.getvalue())
          write(path, before + '\nfunc added() {}\n')
          event = turn_end.parse_event(json.loads(payload))
          resolved = turn_end.workspace(event)
          changes = turn_end.load_changes(resolved, event)
          self.assertEqual(len(changes), 1)
          self.assertEqual(changes[0].path, 'svc/pkg/page.go')
          self.assertEqual(changes[0].before, before)
          self.assertFalse(changes[0].after_deleted)
          commands = turn_end.test_cmds(resolved, changes)
          self.assertEqual(len(commands), 2)
          self.assertEqual(commands[0].directory, os.path.join(root, 'svc'))
          with patch.object(turn_end.shutil, 'which', return_value=None):
            out, err = StringIO(), StringIO()
            self.assertEqual(turn_end.run(['test'], StringIO(payload), out, err), 0, err.getvalue())
          self.assertIn('gopls is not on PATH', out.getvalue())

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
    self.assertFalse(turn_end.skip_gate('test', turn_end.Event(reason='max_turns')))

  def test_skip_non_git(self):
    root = make_temp(self)
    previous = os.getcwd()
    self.addCleanup(os.chdir, previous)
    self.assertEqual(turn_end.workspace(turn_end.Event(cwd=root)), root)
    out, err = StringIO(), StringIO()
    code = turn_end.run(['test'], StringIO(event_json(root)), out, err)
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
      ['test'],
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


if __name__ == '__main__':
  unittest.main()
