"""Event worker application.

Consumes platform events out of the request path. Holds no connector, so a
subscriber cannot write to a system of record.

Deliberately empty of imports: ``make worker`` runs ``python -m worker.main``,
and re-exporting from the package here makes the module load twice.
"""
