"""Check shipped Git rules with Codex itself; never execute policy mutations."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / 'confs/codex/rules'
CODEX = shutil.which('codex')
GIT = shutil.which('git')


@unittest.skipUnless(CODEX, 'codex CLI is required for execution-policy checks')
class GitPolicyTests(unittest.TestCase):
  def check_policy(self, platform, *command):
    rules = sorted(path for path in RULES.glob('*.rules')
      if path.name != ('windows.rules' if platform == 'linux' else 'linux.rules'))
    argv = [CODEX, 'execpolicy', 'check']
    for path in rules:
      argv.extend(['--rules', str(path)])
    result = subprocess.run(argv + ['--', *command], capture_output=True, text=True, timeout=20, check=False)
    self.assertEqual(result.returncode, 0, result.stderr)
    return json.loads(result.stdout)

  def test_reads_keep_native_sandbox_without_allow(self):
    for platform in ('linux', 'windows'):
      for args in (['status', '--short'], ['diff'], ['diff', '--cached'],
          ['log', '-8', '--', 'src/main.py'], ['show', 'HEAD:src/main.py'],
          ['blame', '-L', '1,8', '--', 'src/main.py'],
          ['log', '-8', '-S', 'marker', '--', 'src/main.py'],
          ['log', '-8', '-G', 'marker', '--', 'src/main.py']):
        with self.subTest(platform=platform, args=args):
          result = self.check_policy(platform, 'git', *args)
          self.assertNotIn('decision', result)
          self.assertEqual(result['matchedRules'], [])

  def test_mutations_and_mixed_prefix_listings_prompt(self):
    commands = (
      ['add', 'file.txt'], ['rm', 'file.txt'], ['mv', 'old', 'new'],
      ['commit', '-m', 'fixture'], ['checkout', 'main'], ['switch', 'main'],
      ['restore', 'file.txt'], ['reset', 'HEAD', 'file.txt'],
      ['stash', 'push'], ['fetch'], ['pull'], ['merge', 'topic'],
      ['rebase', 'main'], ['push', 'origin', 'main'], ['clone', 'fixture'],
      ['branch', 'topic'], ['branch', '--list'], ['branch', '--show-current'],
      ['tag', 'v1'], ['tag', '--list'], ['worktree', 'list'],
      ['worktree', 'add', '../fixture'], ['worktree', 'remove', '../fixture'],
      ['bisect', 'start'], ['bisect', 'reset'], ['remote', 'set-url', 'origin', 'fixture'],
    )
    for platform in ('linux', 'windows'):
      for args in commands:
        with self.subTest(platform=platform, args=args):
          self.assertEqual(self.check_policy(platform, 'git', *args)['decision'], 'prompt')

  def test_forbidden_wins_over_mutation_prompt(self):
    for platform in ('linux', 'windows'):
      for executable in ('git', 'git.exe'):
        for args in (['reset', '--hard', 'HEAD'], ['clean', '-fd'],
            ['stash', 'drop'], ['stash', 'clear'],
            ['push', '--force', 'origin'], ['push', '--force-with-lease', 'origin'],
            ['push', '-f', 'origin']):
          with self.subTest(platform=platform, executable=executable, args=args):
            self.assertEqual(self.check_policy(platform, executable, *args)['decision'], 'forbidden')

  def test_prefix_limits_do_not_gain_an_allow(self):
    # Known policy limits, not permission to execute or evade review.
    for platform in ('linux', 'windows'):
      for args, expected in (
          (['git', 'reset', 'HEAD', '--hard'], 'prompt'),
          (['git', 'push', 'origin', '--force'], 'prompt'),
          (['git', '-C', 'fixture', 'status'], None),
          (['git', '-C', 'fixture', 'add', 'file.txt'], None),
          (['git', '-c', 'core.pager=cat', 'log', '-3'], None)):
        with self.subTest(platform=platform, args=args):
          self.assertEqual(self.check_policy(platform, *args).get('decision'), expected)


@unittest.skipUnless(GIT, 'git CLI is required for disposable repository checks')
class GitReadPreservationTests(unittest.TestCase):
  def test_reads_preserve_staged_unstaged_and_untracked_work(self):
    with tempfile.TemporaryDirectory() as directory:
      root = Path(directory)
      # Isolate configuration, hooks, signing, and inherited Git repository state.
      env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
      env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
        GIT_TERMINAL_PROMPT='0')
      hooks = root / 'empty-hooks'
      hooks.mkdir()

      def git(*args):
        result = subprocess.run([GIT, '-c', 'core.autocrlf=false',
          '-c', 'commit.gpgsign=false', '-c', 'core.hooksPath=' + str(hooks),
          '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', *args],
          cwd=root, env=env, capture_output=True, timeout=20, check=False)
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
        return result.stdout

      git('init', '--quiet')
      tracked = root / 'tracked.txt'
      tracked.write_text('original\n', encoding='utf-8')
      git('add', 'tracked.txt')
      git('commit', '--quiet', '-m', 'fixture')
      tracked.write_text('staged\n', encoding='utf-8')
      git('add', 'tracked.txt')
      tracked.write_text('staged\nunstaged\n', encoding='utf-8')
      untracked = root / 'untracked.txt'
      untracked.write_text('user work\n', encoding='utf-8')

      def baseline():
        return (git('rev-parse', 'HEAD'), git('symbolic-ref', 'HEAD'),
          git('status', '--porcelain=v1', '--untracked-files=all'),
          git('diff', '--cached', '--binary'), git('diff', '--binary'),
          git('show', ':tracked.txt'), tracked.read_bytes(), untracked.read_bytes())

      before = baseline()
      for args in (['rev-parse', '--show-toplevel'], ['branch', '--show-current'],
          ['log', '-8', '--oneline', '--', 'tracked.txt'],
          ['show', 'HEAD', '--', 'tracked.txt'],
          ['blame', '-L', '1,1', '--', 'tracked.txt'],
          ['log', '-8', '-S', 'original', '--', 'tracked.txt'],
          ['log', '-8', '-G', 'original', '--', 'tracked.txt'],
          ['branch', '--list'], ['worktree', 'list']):
        git(*args)
      self.assertEqual(baseline(), before)


if __name__ == '__main__':
  unittest.main()
