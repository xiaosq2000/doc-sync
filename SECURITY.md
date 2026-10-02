# Security policy

Docstale runs Git commands, writes `docstale.lock` when you stamp a document,
and keeps hook state under Git metadata. It does not edit agent settings or
execute configured source or documentation paths.

Please report suspected command injection, unsafe path handling, unintended file
replacement, or package supply-chain issues privately through GitHub's security
advisory interface. Do not open a public issue until a fix or mitigation is
available.

Before the first public release, only the latest revision of the standalone
repository will receive security fixes. A version support policy will be
documented when releases begin.
