"""A basic kernel monitor with autorestarting.

This watches a kernel's state using KernelManager.is_alive and auto
restarts the kernel if it dies.

It is an incomplete base class, and must be subclassed.
"""
# Copyright (c) Jupyter Development Team.
# Distributed under the terms of the Modified BSD License.
import time

from traitlets import Bool
from traitlets import default
from traitlets import Dict
from traitlets import Float
from traitlets import Instance
from traitlets import Integer
from traitlets.config.configurable import LoggingConfigurable


class KernelRestarter(LoggingConfigurable):
    """Monitor and autorestart a kernel."""

    kernel_manager = Instance("jupyter_client.KernelManager")

    debug = Bool(
        False,
        config=True,
        help="""Whether to include every poll event in debugging output.

        Has to be set explicitly, because there will be *a lot* of output.
        """,
    )

    time_to_dead = Float(3.0, config=True, help="""Kernel heartbeat interval in seconds.""")

    stable_start_time = Float(
        10.0,
        config=True,
        help="""The time in seconds to consider the kernel to have completed a stable start up.""",
    )

    restart_limit = Integer(
        5,
        config=True,
        help="""The number of consecutive autorestarts before the kernel is presumed dead.""",
    )

    random_ports_until_alive = Bool(
        True,
        config=True,
        help="""Whether to choose new random ports when restarting before the kernel is alive.""",
    )
    _restarting = Bool(False)
    _restart_count = Integer(0)
    _initial_startup = Bool(True)
    _last_dead = Float()

    @default("_last_dead")
    def _default_last_dead(self):
        return time.time()

    callbacks = Dict()

    def _callbacks_default(self):
        return dict(restart=[], dead=[])

    def start(self):
        """Start the polling of the kernel."""
        raise NotImplementedError("Must be implemented in a subclass")

    def stop(self):
        """Stop the kernel polling."""
        raise NotImplementedError("Must be implemented in a subclass")

    def add_callback(self, f, event="restart"):
        """register a callback to fire on a particular event

        Possible values for event:

          'restart' (default): kernel has died, and will be restarted.
          'dead': restart has failed, kernel will be left dead.

        """
        self.callbacks[event].append(f)

    def remove_callback(self, f, event="restart"):
        """unregister a callback to fire on a particular event

        Possible values for event:

          'restart' (default): kernel has died, and will be restarted.
          'dead': restart has failed, kernel will be left dead.

        """
        try:
            self.callbacks[event].remove(f)
        except ValueError:
            pass

    def _fire_callbacks(self, event):
        """fire our callbacks for a particular event"""
        for callback in self.callbacks[event]:
            try:
                callback()
            except Exception:
                self.log.error(
                    "KernelRestarter: %s callback %r failed",
                    event,
                    callback,
                    exc_info=True,
                )

    def poll(self):
        if hasattr(self.parent, "starting_port") and hasattr(self.parent, "max_kernels") and self.parent.starting_port != 0 and self.parent.max_kernels != 0:
           ports_type = "user specified"
        else:
           ports_type = "random"

        if self.debug:
            self.log.debug("Polling kernel...")
        if self.kernel_manager.shutting_down:
            self.log.debug("Kernel shutdown in progress...")
            return
        now = time.time()
        if not self.kernel_manager.is_alive():
            self._last_dead = now
            if self._restarting:
                self._restart_count += 1
            else:
                self._restart_count = 1

            if self._restart_count > self.restart_limit:
                self.log.warning("KernelRestarter: restart failed")
                self._fire_callbacks("dead")
                self._restarting = False
                self._restart_count = 0
                self.stop()
            else:
                newports = self.random_ports_until_alive and self._initial_startup
                self.log.info(
                    "KernelRestarter: restarting kernel (%i/%i), %s %s ports",
                    self._restart_count,
                    self.restart_limit,
                    "new" if newports else "keep",
      	      	    ports_type,
                )
                self._fire_callbacks("restart")
                self.kernel_manager.restart_kernel(now=True, newports=newports)
                self._restarting = True
        else:
            # Since `is_alive` only tests that the kernel process is alive, it does not
            # indicate that the kernel has successfully completed startup. To solve this
            # correctly, we would need to wait for a kernel info reply, but it is not
            # necessarily appropriate to start a kernel client + channels in the
            # restarter. Therefore, we use "has been alive continuously for X time" as a
            # heuristic for a stable start up.
            # See https://github.com/jupyter/jupyter_client/pull/717 for details.
            stable_start_time = self.stable_start_time
            if self.kernel_manager.provisioner:
                stable_start_time = self.kernel_manager.provisioner.get_stable_start_time(
                    recommended=stable_start_time
                )
            if self._initial_startup and now - self._last_dead >= stable_start_time:
                self._initial_startup = False
            if self._restarting and now - self._last_dead >= stable_start_time:
                self.log.debug("KernelRestarter: restart apparently succeeded")
                self._restarting = False
