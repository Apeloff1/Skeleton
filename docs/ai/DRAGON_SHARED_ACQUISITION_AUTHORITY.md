# Dragon shared acquisition authority

The bounded canonical crawler uses an admitted-host stripe pool (4,096 fixed
identities) in a shared Mongo command collection. Sessions and owner command
storage can be bound to a different database, but all cooperating upgraded
workers must use the same coordination authority. This is not an authorization
grant and does not bypass robots, consent, host holds, or transport policy.

The application constructor accepts a server-controlled optional
`coordination_database` handle. By default it pins the original command store.
A later storage handle swap must not change the coordination handle. The real
Motor collection uses primary reads, majority read concern and majority
journaled writes. Incompatible or unavailable coordination storage holds
dispatch; no alternative database is selected. Stripe collisions deliberately
serialize unrelated canonical hosts.

Before moving storage, stop all writers and physically drain all workers.
Coordinate the deployment of every instance, retain a single verified
coordination collection, and preserve access to it. Do not run a legacy
uncoordinated application beside an upgraded one. A Mongo cutover must
separately qualify user, session and command authority; pinning stripes does
not reconcile the other records or turn an offline migration into a live one.
The migration stack and its deployment dependencies must be reconciled before
production use. An expired lease is not proof of physical exit from a crashed
remote process; bounded canonical transport and the pre-I/O margin remain
required. No cross-cluster atomicity is claimed.

## Qualification

Source-only tests: from repository root, with the approved backend Python
environment, run:

    PYTHONPATH=.:backend:tests python -m unittest discover -s backend/tests -p test_dragon_sanctuary_boundary.py -v

Independent disposable Mongo fixture:

    PYTHONPATH=.:backend:tests python -m unittest discover -s backend/tests -p test_dragon_acquisition_coordination_mongo.py -v

For the second command set `SKL_DRAGON_COORDINATION_TEST_MONGO_URL` privately
to a disposable approved Mongo instance. The fixture creates three random
database namespaces and uses two independent clients. Only those generated
namespaces are removed. The source-only workflow deliberately leaves this
variable empty, so its skipped integration tests do not qualify real Mongo.
Do not supply a production database or credentials. Multi-process failure
injection, primary failover, deployment cutover and sustained-scale testing
remain distinct evidence requirements.
