"""Rubber Board (rubberboard.gov.in) daily RSS-4 prices — NOT IMPLEMENTED.

Investigation (2026-10-04):
* rubberboard.gov.in/rssfeed/pricelist.xml links to `rss_indianprice?type=latest`, but that
  page returns only a ~4 KB HTML shell (CSS/JS includes, no price table, no XHR endpoint
  discoverable in public_site/js/*.js). The price list appears to be rendered for browser
  sessions only, so there is no stable machine-readable endpoint to call politely.
* No published API, open-data licence, or robots.txt guidance for automated access.
* Agmarknet already carries Kerala rubber (variety RSS-4, ~11 markets incl. Kottayam) in
  Rs./quintal, which is what the pipeline uses for now.

TODO(rubberboard): if a documented feed appears (or the Board grants permission), implement
`fetch_rubberboard(day)` here: rate-limit via cropcast.ingest.http.get_json, cache raw HTML
under data/cache/rubberboard/, convert Rs./kg -> Rs./quintal (x100), and emit the standard
frame from cropcast.ingest.agmarknet.STANDARD_COLUMNS with source="rubberboard".
"""

from __future__ import annotations

from datetime import date

import pandas as pd

RS_PER_KG_TO_RS_PER_QUINTAL = 100.0


def fetch_rubberboard(day: date) -> pd.DataFrame:
    raise NotImplementedError(
        "Rubber Board has no stable public price endpoint; rubber comes from Agmarknet. "
        "See module docstring."
    )
