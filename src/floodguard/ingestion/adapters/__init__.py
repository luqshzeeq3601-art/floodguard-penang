"""Source adapters: bytes of one captured payload -> source-faithful ``ParsedRow`` objects.

Adapters parse structure only. They never resolve FloodGuard identity (see
``floodguard.ingestion.station_mapping``) and never perform network I/O.
"""
