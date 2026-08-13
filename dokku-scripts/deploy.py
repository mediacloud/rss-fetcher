"""
rss-fetcher deploy script using mc-deploy (in system-dev-ops repo,
installed in development venv thru "dev" optional-dependencies in
pyproject.toml)

replaces shell scripts: push.sh, instance.sh, config.sh, common.sh,
dburl.sh, clone-db.sh plus vars.py
"""

import os
import sys

from mc_deploy.base import CmdArgs, ParserArgs
from mc_deploy.dokku import DokkuDBMixin, DokkuDeploy
from mc_deploy.pyproject import PyProjectMixin


class RssFetcherDeploy(PyProjectMixin, DokkuDBMixin, DokkuDeploy):
    # Much better to increase WEB_CONCURRENCY setting (gunicorn workers)
    # than number of web containers (parallel containers don't cooperate,
    # or report stats properly)!
    DOKKU_SCALE = {"fetcher": 1, "web": 1, "stats": 1}

    # map of plugin name to service name suffix:
    DOKKU_SERVICES = {"postgres": "", "storage": "-storage"}
    DOKKU_STOP = True                          # stop while deploying
    DOKKU_STORAGE_MOUNT_POINT = "/app/storage"  # rss-fetcher is odd

    INST_BASE = "rss-fetcher"   # app base name
    PROJECT_REPO = "rss-fetcher"
    SQLALCHEMY2 = True

    def settings_get_new(self, args: ParserArgs) -> None:
        """
        load project settings
        """
        super().settings_get_new(args)

        # used in fetcher/__init__.py to set APP
        # used to set process title so visible in ps!
        # ('cause I didn't see it available any other way -phil)

        # mcweb wants STATSD_HOST, so here:
        self.settings_add("STATSD_URL", self.statsd_url)
        # STATSD_PREFIX provided by base!

        # Have avoided conditionalizing on inst_type/id
        # (checking for "prod") in favor of fine grained
        # enables.

        # from push.sh, config.sh:
        if self.is_prod_staging():
            self.settings_load_management_config()  # AIRTABLE, SENTRY

            files = ["common.sh"]
            if self.is_prod():
                files.append("prod.sh")  # overrides
            elif self.is_staging():
                files.append("staging.sh")  # overrides
            else:
                self.fatal("is_prod_staging but not is_prod or is_staging???")
            self.settings_load_private_files(self.PROJECT_REPO, files)
        else:
            # load template config file for external development
            # (avoid multiple places with default dev settings):
            self.settings_load_file(".env.template")

            # but remove static, external database URL
            # (dokku supplies it for linked database):
            self.settings_del("DATABASE_URL")

            # push.sh used to create this with random API user/password
            # (could add that back here if file doesn't exist)
            self.settings_load_file(f".pw.{self.inst_id}")

    def deploy_cmd_helper(self, args: CmdArgs) -> None:
        super().deploy_cmd_helper(args)  # load config
        self.settings_add("MC_APP", self.inst_name)

        crontab = os.path.join("/etc/cron.d", self.inst_name)
        if os.path.exists(crontab):
            self.fatal(f"remove {crontab}!!")


d = RssFetcherDeploy()
sys.exit(d.run())
