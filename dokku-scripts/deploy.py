"""
rss-fetcher deploy script using mc-deploy (in system-dev-ops repo,
installed in development venv thru "dev" optional-dependencies in
pyproject.toml)

replaces shell scripts: push.sh, instance.sh, config.sh, common.sh,
dburl.sh, clone-db.sh plus vars.py
"""

import sys

from mc_deploy.dokku import DokkuDBDeploy
from mc_deploy.pyproject import PyProjectMixin

# Have (so far) been unable to get mc-deploy installed so that mypy
# can see the type information, so disabled checking:


class RssFetcherDeploy(PyProjectMixin, DokkuDBDeploy):
    # Much better to increase WEB_CONCURRENCY setting (gunicorn workers)
    # than number of web containers (parallel containers don't cooperate,
    # or report stats properly)!
    DOKKU_SCALE = {"fetcher": 1, "web": 1, "stats": 1}

    # map of plugin name to service name suffix:
    DOKKU_SERVICES = {"postgres": "", "storage": "-storage"}

    # DOKKU_STOP = True                  # stop while deploying
    DOKKU_STORAGE_MOUNT_POINT = "/app/storage"  # rss-fetcher is odd

    INST_BASE = "rss-fetcher"   # app base name
    PROJECT_REPO = "rss-fetcher"

    def settings_get_new(self) -> None:
        """
        load project settings
        """
        super().settings_get_new()

        # used in fetcher/__init__.py to set APP
        # used to set process title so visible in ps!
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
            # load template config file for external development
            # (avoid multiple places with default dev settings):
            self.settings_load_file(".env.template")

            # but remove static, external database URL
            # (dokku supplies it for linked database):
            self.settings.pop("DATABASE_URL", None)

            # push.sh used to create this with random API user/password
            # (could add that back here if file doesn't exist)
            self.settings_load_file(f".pw.{self.inst_id}")


d = RssFetcherDeploy()
sys.exit(d.run())
