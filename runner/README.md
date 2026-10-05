# Starslab runner

Implementation in progress. This package currently provides the local accounting
journal; it does not submit orders and is not yet a usable live runner.

Exchange credentials and execution will remain on the account owner's machine.
Account displays will receive a separate reporting token and allowlisted data.
Neither a Starslab database password nor hosted exchange credentials are required.

The journal uses SQLite with full synchronous writes, one executor lock, unique
signal actions, durable pending intents and atomic terminal fill application.
Confirmed funding limits purchases; only an owned position can be sold. Actual
fees affect cash and quantity. A pending submission blocks subsequent intents
until the exchange outcome is reconciled.

Run the accounting tests from the repository root:

```sh
python -m unittest discover -s runner/tests -v
```

Migration integration tests additionally require psycopg2 and `RUNNER_TEST_DSN`
pointing to an empty disposable database named `starslab_runner_test`. They create
and remove fixture schemas and refuse any other database name.

The source is covered by the repository's MIT license. Full delivery requirements
are in [the change specification](../docs/changes/2026-10-06-self-hosted-execution.md).
