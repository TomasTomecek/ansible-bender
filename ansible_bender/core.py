import os
import logging
import subprocess
import tempfile
import shutil

from ansible_bender import callback_plugins
from ansible_bender.exceptions import AbBuildUnsuccesful
from ansible_bender.utils import run_cmd, ap_command_exists


logger = logging.getLogger(__name__)
A_CFG_TEMPLATE = """\
[defaults]
retry_files_enabled = False
# when user is changed, ansible might not be able to write to /.ansible
remote_tmp = /tmp
callback_plugins={0}
callback_whitelist=snapshoter\n
"""


def run_playbook(playbook_path, inventory_path, a_cfg_path, connection, extra_variables=None,
                 ansible_args=None, debug=False, environment=None):
    ap_command_exists()
    cmd_args = [
        "ansible-playbook-3",  # FIXME: find ansible, prefer python 3
        "-i", inventory_path,
        "-c", connection,

    ]
    if debug:
        cmd_args += ["-vvv"]
    if extra_variables:
        cmd_args += ["--extra-vars"] + \
                    [" ".join(
                        ["{}={}".format(k, v)
                         for k, v in extra_variables.items()]
                    )]
    cmd_args += [playbook_path]
    logger.debug("%s", " ".join(cmd_args))

    env = os.environ.copy()
    if environment:
        env.update(environment)
    env["ANSIBLE_CONFIG"] = a_cfg_path

    # TODO: does ansible have an API?
    try:
        run_cmd(
            cmd_args,
            print_output=True,
            env=env,
        )
    except subprocess.CalledProcessError as ex:
        raise AbBuildUnsuccesful("ansible-playbook execution failed: %s" % ex)


class AnsibleRunner:
    """
    Run ansible on provided artifact using the Builder interface
    """

    def __init__(self, playbook_path, builder, build, debug=False):
        self.build_i = build
        self.pb = playbook_path
        self.builder = builder
        self.debug = debug

    def _create_inventory_file(self, fd, python_interpreter):
        fd.write(
            '%s ansible_connection="%s" ansible_python_interpreter="%s"\n' % (
                self.builder.ansible_host,
                self.builder.ansible_connection,
                python_interpreter
            )
        )

    def _create_ansible_cfg(self, fd):
        callback_plugins_dir = os.path.dirname(callback_plugins.__file__)
        fd.write(A_CFG_TEMPLATE.format(callback_plugins_dir))

    def build(self, python_interpreter="/usr/bin/python3"):
        """
        run the playbook against the container

        :return:
        """
        tmp = tempfile.mkdtemp(prefix="ab")
        try:
            environment = {
                "AB_BUILD_ID": self.build_i.build_id,
            }
            inv_path = os.path.join(tmp, "inventory")
            logger.info("creating inventory file %s", inv_path)
            with open(inv_path, "w") as fd:
                self._create_inventory_file(fd, python_interpreter)
            a_cfg_path = os.path.join(tmp, "ansible.cfg")
            with open(a_cfg_path, "w") as fd:
                self._create_ansible_cfg(fd)
            run_playbook(self.pb, inv_path, a_cfg_path, self.builder.ansible_connection,
                         debug=self.debug, environment=environment)
        finally:
            shutil.rmtree(tmp)