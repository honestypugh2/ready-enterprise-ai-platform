"""Integration suites.

Most of what is here runs offline against the composition root, because
"integration" in this repository means *the planes wired together*, not *a live
Azure subscription*. The tests that genuinely need cloud dependencies carry the
``integration`` marker and are skipped unless ``REAP_RUN_INTEGRATION=1``.
"""
