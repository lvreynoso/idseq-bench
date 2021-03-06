import gzip
import os
import re
import subprocess
import time
from io import TextIOWrapper
from urllib.parse import urlparse
from fnmatch import fnmatch


class ExpectedNumFilesException(Exception):
  def __init__(self, pattern, actual, expected):
    expected_str = ' or '.join(map(str, expected))
    super().__init__(f"Expected {expected_str} files for {pattern}, found {actual}")

def remove_safely(fn):
  if os.path.isfile(fn):
    os.remove(fn)

def chop(txt, suffix):
  assert txt.endswith(suffix)
  return txt[:-len(suffix)]


def check_call(command, capture_stdout=False, quiet=False):
  # Assuming python >= 3.5
  shell = isinstance(command, str)
  if not quiet:
    command_str = command if shell else " ".join(command)
    print(repr(command_str))
  # In Python 3.7 the subprocess.run function accepts capture_output param,
  # so setting stdout like so is only done for backward compatibility with
  # python versions >= 3.5.  That's the minimum we support.
  stdout = subprocess.PIPE if capture_stdout else None
  p = subprocess.run(command, shell=shell, check=True, stdout=stdout)
  return p.stdout.decode('utf-8') if capture_stdout else None


def check_output(command, quiet=False):
  return check_call(command, capture_stdout=True, quiet=quiet)


def smart_glob(pattern, expected_num_files, ls_memory=None):
  pdir, file_pattern = pattern.rsplit("/", 1)
  listed_files = smart_ls(pdir, memory=ls_memory)
  matching_files = list(
    filter(
      lambda filename: re.match(file_pattern, filename),
      listed_files))

  actual_num_files = len(matching_files)
  if isinstance(expected_num_files, int):
    expected_num_files = [expected_num_files]

  if actual_num_files not in expected_num_files:
    raise ExpectedNumFilesException(pattern, actual_num_files, expected_num_files)
  return [f"{pdir}/{mf}" for mf in sorted(matching_files)]


def smart_ls(pdir, missing_ok=True, memory=None):
  """Return a list of files in pdir.  This pdir can be local or in s3.
  If memory dict provided, use it to memoize.  If missing_ok=True, swallow errors (default)."
  """
  result = memory.get(pdir) if memory else None
  if result == None:
    try:
      if pdir.startswith("s3"):
        s3_dir = pdir
        if not s3_dir.endswith("/"):
          s3_dir += "/"
        output = check_output(["aws", "s3", "ls", s3_dir])
        rows = output.strip().split('\n')
        result = [r.split()[-1] for r in rows]
      else:
        output = check_output(["ls", pdir])
        result = output.strip().split('\n')
    except Exception as e:
      msg = f"Could not read directory: {pdir}"
      if missing_ok and isinstance(e, subprocess.CalledProcessError):
        print(f"INFO: {msg}")
        result = []
      else:
        print(f"ERROR: {msg}")
        raise
    if memory != None:
      memory[pdir] = result
  return result


class ProgressTracker:

  def __init__(self, target):
    self.target = target
    self.current = 0
    self.t_start = time.time()

  def advance(self, amount):
    PESSIMISM = 2.0
    self.current += amount
    t_elapsed = time.time() - self.t_start
    t_remaining = (t_elapsed / self.current) * self.target - t_elapsed
    t_remaining *= PESSIMISM
    t_eta = self.t_start + t_elapsed + t_remaining
    t_eta_str = time.strftime("%H:%M:%S", time.localtime(t_eta))
    print(f"*** {self.current/self.target*100:3.1f} percent done, {t_elapsed/60:3.1f} minutes elapsed, {t_remaining/60:3.1f} minutes remaining, ETA {t_eta_str} ***\n")
