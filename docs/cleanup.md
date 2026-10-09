# Code cleanup audit

Date: 2026-10-09

The repository does not declare or install Vulture or Knip. Neither executable is
available in the current environment, so this pass did not use heuristic dead
code findings to remove code. No entry point, data, configuration, or source
module was deleted based on an unverified guess.

The touched Python files pass py_compile; the full pytest suite passes. The
Next.js production build also passes TypeScript. git diff --check reports no
whitespace errors. Review the diff before merging. To run the requested
dead-code scan in CI, add Vulture and Knip as explicit development tools and
review each reported symbol with repository-wide references before removal.
