# Architecture

Two paths, never one process: the **indexer Job** is the only writer to Chroma; the **api** only reads.
Both read `EMBED_MODEL` from the one ConfigMap (`k8s/base/configmap.yaml`); the indexer also stamps the
model name and vector dimension into the collection metadata, and the api refuses readiness on mismatch.

```
Ingress ─ /     ─> ui (nginx)
        └ /api  ─> api x3 ──> chroma (StatefulSet, PVC)   [read]
                       └────> redis  (Deployment, PVC)    [semantic cache]
indexer Job / reindex CronJob ──> chroma [write], redis [flush cache]
```

## Why Chroma is a StatefulSet, not a Deployment

Chroma owns on-disk state that must outlive and stay bound to one pod identity.
A StatefulSet gives it (1) `volumeClaimTemplates`, so the PVC is created per pod and re-attached to
`chroma-0` after a delete or reschedule; a Deployment would share one hand-made PVC and, on a rolling
update, briefly run two pods against the same volume (two writers, a corrupt index);
(2) a stable network identity (`chroma-0`) behind the `chroma` ClusterIP Service; (3) ordered,
one-at-a-time updates. Deleting the pod therefore loses no index.

Redis is a Deployment + PVC (single replica, cache only; losing it costs hits, never correctness).
