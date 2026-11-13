The localhost certificate and key are disposable public test fixtures.
They identify only localhost and must never be installed in the Windows trust
store or used outside the local TLS regression tests. The tests deliberately
verify that the production trust context rejects this self-signed certificate.
