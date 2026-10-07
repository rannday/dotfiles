import json
import os
from pathlib import Path
import tempfile
import unittest
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

  def test_deny_shell_git(self):
    with patch.object(antigravity_hooks, 'ensure_snapshot', return_value={}):
      raw = event('run_command', args={'CommandLine': 'git diff'})
      result = antigravity_hooks.dispatch(raw)
    self.assertEqual(result['decision'], 'deny')
    self.assertIn('gk__git_log_or_diff', result['reason'])

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

  def test_stop_blocks_missing_gopls_diagnostics(self):
    session = 'antigravity-conv-1'
    prompt = '1'
    tool_gate.state_path(session, prompt, 'gopls-edited').write_text('foo.go', encoding='utf-8')
    raw_stop = dict(conversationId='conv-1', stepIdx=1, terminationReason='model_stop', fullyIdle=True)
    result = antigravity_hooks.dispatch(raw_stop)
    self.assertEqual(result['decision'], 'continue')
    self.assertIn('gopls__go_diagnostics', result['reason'])


if __name__ == '__main__':
  unittest.main()
