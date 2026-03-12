from typing import Callable

from scrapers.sites.hardoff.adapter import run_pipeline as run_hardoff
from scrapers.sites.kitamura.adapter import run_pipeline as run_kitamura
from scrapers.sites.mercari.adapter import run_pipeline as run_mercari
from scrapers.sites.rakuma.adapter import run_pipeline as run_rakuma
from scrapers.sites.surugaya.adapter import run_pipeline as run_surugaya
from scrapers.sites.rakuten.adapter import run_pipeline as run_rakuten
from scrapers.sites.secondstreet.adapter import run_pipeline as run_secondstreet
from scrapers.sites.yafuoku.adapter import run_pipeline as run_yafuoku
from scrapers.sites.yahoofleama.adapter import run_pipeline as run_yahoofleama
from scrapers.sites.yodobashi.adapter import run_pipeline as run_yodobashi

SiteRunner = Callable[[str], dict]

SITE_RUNNERS: dict[str, SiteRunner] = {
    "yahoofleama": run_yahoofleama,
    "secondstreet": run_secondstreet,
    "mercari": run_mercari,
    "rakuma": run_rakuma,
    "surugaya": run_surugaya,
    "yafuoku": run_yafuoku,
    "yodobashi": run_yodobashi,
    "hardoff": run_hardoff,
    "kitamura": run_kitamura,
    "rakuten": run_rakuten,
}


def list_sites() -> list[str]:
    return sorted(SITE_RUNNERS.keys())
