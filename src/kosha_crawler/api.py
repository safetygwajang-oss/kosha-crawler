def list_media(self, page: int = 1, rows: int | None = None) -> dict[str, Any]:
    payload = {
        "shpCd": settings.SHP_CD,
        "searchCondition": "all",
        "searchValue": None,
        "ascDesc": "desc",
        "page": page,
        "rowsPerPage": rows or settings.ROWS_PER_PAGE,
    }
    import time, logging
    log = logging.getLogger("kosha")
    t0 = time.time()
    r = self.s.post(settings.list_api, json=payload, timeout=settings.REQUEST_TIMEOUT)
    elapsed = time.time() - t0
    log.info(f"  [API] list_media page={page} status={r.status_code} time={elapsed:.1f}s size={len(r.content)}B")
    log.info(f"  [API] response preview: {r.text[:300]}")
    r.raise_for_status()
    return r.json().get("payload", {})
