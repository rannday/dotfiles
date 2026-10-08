import os
import subprocess
import unittest
from io import StringIO
from unittest.mock import patch

import grok_review
import turn_end


class ReviewTests(unittest.TestCase):
  def setUp(self):
    self.enterContext(patch.dict(os.environ, {'XAI_API_KEY': 'test-key'}, clear=True))
    self.enterContext(patch.object(grok_review, 'user_api_key', side_effect=AssertionError('live credential lookup')))
    self.changes = [turn_end.Change(path='notes.txt', before='ok\n', after='changed\n')]
    self.enterContext(patch.object(grok_review, 'load_changes', return_value=self.changes))
    self.event = turn_end.Event(session_id='rev', prompt_id='1', workspace_root='fixture')

  def review(self):
    out, err = StringIO(), StringIO()
    code = grok_review.gate_review('fixture', self.event, out, err)
    return code, out.getvalue(), err.getvalue()

  def test_review_uses_api_key_and_fake_runner(self):
    with patch.object(grok_review, 'run_review', return_value=('No issues.\n', None)) as runner:
      code, out, err = self.review()
    self.assertEqual(code, 0, err)
    self.assertEqual(out, '')
    prompt, env, cwd = runner.call_args.args
    self.assertEqual(env.get('TURN_END_CHILD'), '1')
    self.assertEqual(env.get('XAI_API_KEY'), 'test-key')
    self.assertEqual(cwd, 'fixture')
    self.assertIn('notes.txt', prompt)
    self.assertNotIn('test-key', prompt)

  def test_review_blocks_on_finding_and_redacts_key(self):
    with patch.object(grok_review, 'run_review', return_value=('notes.txt:L1: test-key bug. fix.\n', None)):
      code, out, err = self.review()
    self.assertEqual(code, 0, err)
    self.assertIn('notes.txt:L1: [redacted] bug. fix.', out)
    self.assertIn('"decision":"block"', out)
    self.assertNotIn('test-key', out + err)

  def test_failure_redacts_output_and_exception(self):
    for output in ('failed test-key', ''):
      with self.subTest(output=output), patch.object(grok_review, 'run_review', return_value=(output, OSError('test-key rejected'))):
        code, out, err = self.review()
      self.assertEqual(code, 0, err)
      self.assertIn('review failed:', out)
      self.assertIn('[redacted]', out)
      self.assertNotIn('test-key', out + err)

  def test_timeout_blocks_without_exposing_key(self):
    with patch.object(grok_review, 'run_review', return_value=('test-key', TimeoutError('test-key'))):
      code, out, err = self.review()
    self.assertEqual(code, 0, err)
    self.assertIn('review timed out', out)
    self.assertNotIn('test-key', out + err)

  def test_subagent_skips_review(self):
    with patch.dict(os.environ, {'GROK_HOOK_EVENT': 'subagent_stop'}), patch.object(grok_review, 'run_review') as runner:
      code, out, err = self.review()
    self.assertEqual(code, 0, err)
    self.assertEqual(out, '')
    runner.assert_not_called()

  def test_child_skips_review(self):
    with patch.dict(os.environ, {'TURN_END_CHILD': '1'}), patch.object(grok_review, 'run_review') as runner:
      code, out, err = self.review()
    self.assertEqual(code, 0, err)
    self.assertEqual(out, '')
    runner.assert_not_called()

  def test_no_snapshot_skips_review(self):
    with patch.object(grok_review, 'load_changes', side_effect=turn_end.NoSnapshot()), patch.object(grok_review, 'run_review') as runner:
      code, out, err = self.review()
    self.assertEqual(code, 0, err)
    self.assertEqual(out, '')
    runner.assert_not_called()

  def test_no_changes_skips_review(self):
    with patch.object(grok_review, 'load_changes', return_value=[]), patch.object(grok_review, 'run_review') as runner:
      code, out, err = self.review()
    self.assertEqual(code, 0, err)
    self.assertEqual(out, '')
    runner.assert_not_called()

  def test_snapshot_failure_reports_error_without_runner(self):
    with patch.object(grok_review, 'load_changes', side_effect=OSError('snapshot unavailable')), patch.object(grok_review, 'run_review') as runner:
      code, out, err = self.review()
    self.assertEqual(code, 1)
    self.assertEqual(out, '')
    self.assertIn('snapshot unavailable', err)
    runner.assert_not_called()


class RunnerTests(unittest.TestCase):
  def setUp(self):
    self.enterContext(patch.dict(os.environ, {}, clear=True))
    self.process = self.enterContext(patch.object(grok_review.subprocess, 'run'))
    self.enterContext(patch.object(grok_review.shutil, 'which', return_value='fake-grok'))

  def test_missing_cli_does_not_spawn(self):
    with patch.object(grok_review.shutil, 'which', return_value=None):
      out, err = grok_review.run_review('diff', {'XAI_API_KEY': 'fake-key'}, 'fixture')
    self.assertEqual(out, '')
    self.assertIn('grok is not on PATH', str(err))
    self.process.assert_not_called()

  def test_missing_key_does_not_spawn(self):
    out, err = grok_review.run_review('diff', {}, 'fixture')
    self.assertEqual(out, '')
    self.assertIn('XAI_API_KEY is not set', str(err))
    self.process.assert_not_called()

  def test_runner_uses_single_turn_and_restricted_tools(self):
    self.process.return_value = subprocess.CompletedProcess([], 0, b'No issues.\n', b'')
    env = {'XAI_API_KEY': 'fake-key', 'TURN_END_CHILD': '1'}
    out, err = grok_review.run_review('diff', env, 'fixture')
    self.assertEqual((out, err), ('No issues.\n', None))
    args = self.process.call_args.args[0]
    self.assertEqual(args[:3], ['grok', '-p', 'diff'])
    self.assertEqual(args[args.index('--max-turns') + 1], '1')
    self.assertEqual(args[args.index('--disallowed-tools') + 1], 'Agent,search_replace,write,run_terminal_command')
    self.assertEqual(self.process.call_args.kwargs['env'], env)
    self.assertEqual(self.process.call_args.kwargs['cwd'], 'fixture')
    self.assertFalse(self.process.call_args.kwargs.get('shell', False))

  def test_nonzero_exit_preserves_diagnostic_for_redaction(self):
    self.process.return_value = subprocess.CompletedProcess([], 2, b'output', b'failure')
    out, err = grok_review.run_review('diff', {'XAI_API_KEY': 'fake-key'}, 'fixture')
    self.assertEqual(out, 'outputfailure')
    self.assertIn('exit 2', str(err))

  def test_timeout_is_reported(self):
    self.process.side_effect = subprocess.TimeoutExpired('grok', 1)
    out, err = grok_review.run_review('diff', {'XAI_API_KEY': 'fake-key'}, 'fixture')
    self.assertEqual(out, '')
    self.assertIsInstance(err, TimeoutError)

  def test_os_failure_is_reported(self):
    self.process.side_effect = OSError('spawn failed')
    out, err = grok_review.run_review('diff', {'XAI_API_KEY': 'fake-key'}, 'fixture')
    self.assertEqual(out, '')
    self.assertIn('spawn failed', str(err))

  def test_supplied_key_avoids_live_lookup(self):
    with patch.dict(os.environ, {'XAI_API_KEY': 'fake-key'}), patch.object(grok_review, 'user_api_key', side_effect=AssertionError('live credential lookup')):
      env = grok_review.review_env()
    self.assertEqual(env['XAI_API_KEY'], 'fake-key')
    self.assertEqual(env['TURN_END_CHILD'], '1')

  def test_missing_key_uses_mocked_fallback(self):
    with patch.object(grok_review, 'user_api_key', return_value='fallback-key') as fallback:
      env = grok_review.review_env()
    fallback.assert_called_once_with()
    self.assertEqual(env['XAI_API_KEY'], 'fallback-key')

  def test_missing_fallback_does_not_invent_key(self):
    with patch.object(grok_review, 'user_api_key', return_value=''):
      env = grok_review.review_env()
    self.assertNotIn('XAI_API_KEY', env)
    self.assertEqual(env['TURN_END_CHILD'], '1')


class ReviewPromptTests(unittest.TestCase):
  def test_small_diff_lists_file_and_hunk(self):
    prompt = grok_review.review_prompt([
      turn_end.Change(path='a.go', before='func old()\n', after='func new()\n'),
    ])
    self.assertIn('Files: a.go', prompt)
    self.assertIn('func new()', prompt)
    self.assertNotIn('Omitted:', prompt)
    self.assertNotIn('Truncated:', prompt)

  def test_per_file_cap_keeps_later_file(self):
    big = 'x\n' * (grok_review.REVIEW_FILE_CAP + 40)
    prompt = grok_review.review_prompt([
      turn_end.Change(path='big.go', before='', after=big),
      turn_end.Change(path='late.go', before='a\n', after='late-marker\n'),
    ])
    self.assertIn('Files: big.go, late.go', prompt)
    self.assertIn('Truncated: big.go', prompt)
    self.assertIn('big.go hunks omitted', prompt)
    self.assertIn('late-marker', prompt)
    self.assertNotIn('Omitted:', prompt)

  def test_budget_names_omitted_paths(self):
    previous_cap = grok_review.REVIEW_CAP
    previous_file = grok_review.REVIEW_FILE_CAP
    grok_review.REVIEW_CAP = 40
    grok_review.REVIEW_FILE_CAP = 200
    self.addCleanup(setattr, grok_review, 'REVIEW_CAP', previous_cap)
    self.addCleanup(setattr, grok_review, 'REVIEW_FILE_CAP', previous_file)
    prompt = grok_review.review_prompt([
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
    prompt = grok_review.review_prompt(changes, complete=True)
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
    prompt = grok_review.review_prompt(changes, complete=True)
    self.assertTrue(prompt.endswith(expected))
    for number in range(4):
      self.assertIn(f'+file-{number}-line-0399\n', prompt)
    self.assertNotIn('Truncated:', prompt)
    self.assertNotIn('Omitted:', prompt)

  def test_deleted_text_file_has_full_deletion_diff(self):
    for complete in (False, True):
      with self.subTest(complete=complete):
        prompt = grok_review.review_prompt([
          turn_end.Change(path='gone.go', before='first\nsecond\n', after='', after_deleted=True),
        ], complete=complete)
        self.assertIn('Files: gone.go', prompt)
        self.assertIn('--- gone.go\n+++ /dev/null\n', prompt)
        self.assertIn('-first\n-second\n', prompt)
        self.assertNotIn('binary', prompt)

  def test_deleted_binary_file_still_omits_content(self):
    prompt = grok_review.review_prompt([
      turn_end.Change(path='gone.bin', before='private\0data', after='', after_deleted=True),
    ], complete=True)
    self.assertIn('gone.bin: binary diff omitted', prompt)
    self.assertNotIn('private', prompt)


if __name__ == '__main__':
  unittest.main()
