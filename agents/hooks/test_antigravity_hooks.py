import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import nullcontext
from unittest.mock import patch

import antigravity_hooks
import tool_gate
import turn_end


def event(tool='', **fields):
  tool_call = {'name': tool, 'args': fields.pop('args', {})}
  return dict(conversationId='conv-1', stepIdx=1, toolCall=tool_call, **fields)


class AntigravityHooksTests(unittest.TestCase):
  def setUp(self):
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.env = patch.dict(os.environ, {'GROK_TOOL_GATE_STATE': self.temp.name})
    self.env.start()
    self.addCleanup(self.env.stop)

  def test_normalize_run_command(self):
    raw = event('run_command', args={'CommandLine': 'git status'})
    parsed = antigravity_hooks.normalize(raw)
    self.assertEqual(parsed['sessionId'], 'antigravity-conv-1')
    self.assertEqual(parsed['promptId'], '1')
    self.assertEqual(parsed['toolName'], 'run_terminal_command')
    self.assertEqual(parsed['tool_input'], {'command': 'git status'})
    self.assertEqual(parsed['hook_event_name'], 'PreToolUse')

  def test_normalize_file_tools(self):
    raw = event('replace_file_content', args={'TargetFile': 'foo.go'})
    parsed = antigravity_hooks.normalize(raw)
    self.assertEqual(parsed['toolName'], 'write')
    self.assertEqual(parsed['tool_input'], {'file_path': 'foo.go'})

    raw_view = event('view_file', args={'AbsolutePath': 'foo.go'})
    parsed_view = antigravity_hooks.normalize(raw_view)
    self.assertEqual(parsed_view['toolName'], 'read_file')
    self.assertEqual(parsed_view['tool_input'], {'file_path': 'foo.go'})

  def test_malformed_continuation_state_is_ignored(self):
    state = tool_gate.state_path('antigravity-conv-1', 'session', 'continuation.json')
    invalid = [[], None, True, 7, 'state',
      {'turn': '1', 'origin': []}, {'turn': True, 'origin': 'old'},
      {'turn': [], 'origin': 'old'}, {'turn': '1', 'reason': []},
      {'turn': '1', 'repeats': -1}, {'turn': '1', 'repeats': True}]
    for value in invalid:
      with self.subTest(value=value):
        state.write_text(json.dumps(value), encoding='utf-8')
        parsed = antigravity_hooks.normalize(event())
        self.assertEqual(parsed['promptId'], '1')
    for content in (b'not JSON', b'\xff'):
      with self.subTest(content=content):
        state.write_bytes(content)
        self.assertEqual(antigravity_hooks.normalize(event())['promptId'], '1')
    with patch.object(Path, 'read_text', side_effect=PermissionError('unreadable state')):
      self.assertEqual(antigravity_hooks.normalize(event())['promptId'], '1')

  def test_continuation_matches_integer_steps_and_keeps_origin(self):
    state = tool_gate.state_path('antigravity-conv-1', 'session', 'continuation.json')
    raw = dict(event(), stepIdx=12)
    for turn in (12, '12'):
      with self.subTest(turn=turn):
        state.write_text(json.dumps({'turn': turn, 'origin': '3'}), encoding='utf-8')
        parsed = antigravity_hooks.normalize(raw)
        self.assertEqual(parsed['promptId'], '3')
        result = {'decision': 'continue', 'reason': 'Fix tests.'}
        self.assertEqual(antigravity_hooks.remember_block(parsed, result), result)
        stored = json.loads(state.read_text(encoding='utf-8'))
        self.assertEqual(stored['turn'], '12')
        self.assertEqual(stored['origin'], '3')
        self.assertEqual(antigravity_hooks.normalize(raw)['promptId'], '3')

  def test_malformed_repeat_counts_recover_with_bounded_retries(self):
    parsed = antigravity_hooks.normalize(event())
    state = tool_gate.state_path(parsed['sessionId'], 'session', 'continuation.json')
    result = {'decision': 'continue', 'reason': 'Fix tests.'}
    invalid = [[], None, True, 7, 'state']
    invalid.extend({'reason': 'Fix tests.', 'repeats': count}
      for count in (None, True, -100, 1.5, '2', [], {}))
    contents = [json.dumps(value).encode('utf-8') for value in invalid]
    contents.extend((b'not JSON', b'\xff'))
    for content in contents:
      with self.subTest(content=content):
        state.write_bytes(content)
        self.assertEqual(antigravity_hooks.remember_block(parsed, result), result)
        self.assertEqual(antigravity_hooks.remember_block(parsed, result), result)
        self.assertEqual(antigravity_hooks.remember_block(parsed, result), {})
        self.assertEqual(antigravity_hooks.remember_block(parsed, result), {})

  def test_changed_failure_resets_retry_count(self):
    parsed = antigravity_hooks.normalize(event())
    old = {'decision': 'continue', 'reason': 'Old failure.'}
    for _ in range(3):
      antigravity_hooks.remember_block(parsed, old)
    result = {'decision': 'continue', 'reason': 'New failure.'}
    self.assertEqual(antigravity_hooks.remember_block(parsed, result), result)
    state = tool_gate.state_path(parsed['sessionId'], 'session', 'continuation.json')
    self.assertEqual(json.loads(state.read_text(encoding='utf-8'))['repeats'], 1)

  def test_allow_shell_git(self):
    with patch.object(antigravity_hooks, 'ensure_snapshot', return_value={}):
      raw = event('run_command', args={'CommandLine': 'git diff'})
      result = antigravity_hooks.dispatch(raw)
    self.assertEqual(result['decision'], 'allow')

  def test_deny_protected_secret_path(self):
    with patch.object(antigravity_hooks, 'ensure_snapshot', return_value={}):
      raw = event('replace_file_content', args={'TargetFile': '.env.production'})
      result = antigravity_hooks.dispatch(raw)
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('.env', result['reason'])

  def test_allow_safe_command(self):
    with patch.object(antigravity_hooks, 'ensure_snapshot', return_value={}):
      raw = event('run_command', args={'CommandLine': 'echo hello'})
      result = antigravity_hooks.dispatch(raw)
    self.assertEqual(result['decision'], 'allow')

  def test_stop_runs_local_checks_without_provider_review(self):
    raw = dict(conversationId='conv-1', stepIdx=1, terminationReason='model_stop', fullyIdle=True)
    changes = [turn_end.Change('foo.py', 'old', 'new')]
    with patch.object(antigravity_hooks, 'run_stage', return_value={}) as stage, \
         patch.object(turn_end, 'ensure_git'), \
         patch.object(turn_end, 'load_changes', return_value=changes):
      self.assertEqual(antigravity_hooks.dispatch(raw), {})
    self.assertEqual([call.args[0] for call in stage.call_args_list], ['format', 'test'])

  def test_unreadable_test_cache_preserves_test_failure(self):
    parsed = antigravity_hooks.normalize(event(), 'Stop')
    changes = [turn_end.Change('foo.py', 'old', 'new')]
    cache = tool_gate.state_path(parsed['sessionId'], parsed['promptId'], 'test.passed')
    cache.write_bytes(b'\xff')
    failure = {'decision': 'continue', 'reason': 'Tests failed.'}
    for read_error in (None, PermissionError('unreadable cache'), OSError('cache unavailable')):
      with self.subTest(read_error=read_error), \
           patch.object(antigravity_hooks, 'run_stage', side_effect=[{}, failure]) as stage, \
           patch.object(turn_end, 'ensure_git'), \
           patch.object(turn_end, 'load_changes', return_value=changes), \
           (patch.object(Path, 'read_text', side_effect=read_error) if read_error else nullcontext()):
        self.assertEqual(antigravity_hooks.stop(parsed), failure)
      self.assertEqual([call.args[0] for call in stage.call_args_list], ['format', 'test'])
      self.assertEqual(cache.read_bytes(), b'\xff')

  def test_corrupt_test_cache_is_replaced_and_changed_diff_reruns_tests(self):
    parsed = antigravity_hooks.normalize(event(), 'Stop')
    changes = [turn_end.Change('foo.py', 'old', 'new')]
    cache = tool_gate.state_path(parsed['sessionId'], parsed['promptId'], 'test.passed')
    cache.write_bytes(b'\xff')
    with patch.object(antigravity_hooks, 'run_stage', return_value={}) as stage, \
         patch.object(turn_end, 'ensure_git'), \
         patch.object(turn_end, 'load_changes', return_value=changes):
      self.assertEqual(antigravity_hooks.stop(parsed), {})
      self.assertEqual(cache.read_text(encoding='utf-8'), antigravity_hooks.changes_key(changes))
      self.assertEqual([call.args[0] for call in stage.call_args_list], ['format', 'test'])
      stage.reset_mock()
      self.assertEqual(antigravity_hooks.stop(parsed), {})
      self.assertEqual([call.args[0] for call in stage.call_args_list], ['format'])
      stage.reset_mock()
      changes[0].after = 'changed again'
      self.assertEqual(antigravity_hooks.stop(parsed), {})
      self.assertEqual([call.args[0] for call in stage.call_args_list], ['format', 'test'])


if __name__ == '__main__':
  unittest.main()
