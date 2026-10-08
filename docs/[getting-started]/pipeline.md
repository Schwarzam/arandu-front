# Pipeline

## Current input

For now, the producer creates fake alerts using the [RAPID v01.00 Avro schema](https://github.com/Schwarzam/arandu/blob/main/arandu/producer.py#L121-L329). This tests database behavior under heavy load. It is not telescope input.

## Flow

`producer → Redis → enricher → Redis → worker → Postgres`

![Pipeline flow](pipeline-flow.png)

1. The producer encodes a fake RAPID alert and adds it to `rapid:alerts`.
2. The enricher reads the raw stream, runs the configured enrichers, and adds the alert plus enrichment metadata to `rapid:alerts:enriched`.
3. The worker reads the enriched stream and writes the alert to Postgres. It also writes FITS cutouts when enabled.

## Redis

Redis provides the two work queues: `rapid:alerts` and `rapid:alerts:enriched`. The enricher and worker use consumer groups. A message is acknowledged only after the next stage succeeds. Pending messages are reclaimed after a consumer stops.

Redis is not the archive. Processed stream entries are deleted. Postgres stores the alert records.

## Enrichers

Enrichers are Python modules configured by `ENRICHER_PLUGINS`. They run in order for each alert. An enricher receives the alert and may read its history from the payload, Postgres, or both. It returns the alert and a result containing a name, version, value, and additional fields.

The worker stores each result in `arandu.enrichment`. One detection can have results from multiple enrichers and versions.

## Worker

The worker decodes the enriched Avro payload and upserts `dia_object`, `dia_source`, forced-source, solar-system, orbit, alert, and enrichment records in Postgres. It acknowledges the Redis message after the database transaction commits. Replayed messages are safe because inserts ignore existing primary keys.
