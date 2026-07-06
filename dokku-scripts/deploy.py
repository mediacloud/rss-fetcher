"""
rss-fetcher deploy script using mc-deploy (in system-dev-ops repo)
replaces push.sh, instance.sh, config.sh, vars.py etc
"""

import sys

from mc_deploy.dokku import DokkuDBMixin, DokkuDeploy
from mc_deploy.pyproject import PyProjectMixin


class RssFetcherDeploy(PyProjectMixin, DokkuDBMixin, DokkuDeploy):  # type: ignore
    DOKKU_SCALE = ["fetcher=1", "web=1", "stats=1"]
    DOKKU_SERVICES = [("postgres", "")]  # list of service, suffix tuples:
    # DOKKU_STOP = True                  # stop while deploying

    INST_BASE = "rss-fetcher"   # app base name
    PROJECT_REPO = "rss-fetcher"

    def settings_get_new(self) -> None:
        """
        load project settings
        """
        super().settings_get_new()

        # used in fetcher/__init__.py to set APP
        # ('cause I didn't see it available any other way -phil)
        self.settings_add("MC_APP", self.inst_name)

        # mcweb wants STATSD_HOST, so here:
        self.settings_add("STATSD_URL", self.statsd_url)
        # STATSD_PREFIX provided by base!

        # from push.sh, config.sh:
        if self.is_prod_staging():
            # currently only prod.sh, no staging overrides
            files = ["prod.sh"]
            self.settings_load_private_files(f"{self.PROJECT_REPO}-config",
                                             files)
        else:
            self.settings_load_file(".env.template")
            self.settings.pop("DATABASE_URL", None)

            # push.sh used to this with random user/password:
            self.settings_load_file(f".pw.{self.inst_id}")


d = RssFetcherDeploy()
sys.exit(d.run())
