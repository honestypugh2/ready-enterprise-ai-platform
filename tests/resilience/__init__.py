"""Failure injection.

Every dependency here is allowed to fail, and the assertion is always the same
shape: the platform degrades to a *safe* state, records why, and does not write.
Availability is negotiable; unsupervised action is not.

Nothing in this file uses wall-clock sleeps or retries against a real network,
so the suite is deterministic and fast enough to run on every commit.
"""
