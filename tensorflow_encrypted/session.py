import os
from typing import Dict, List, Optional, Any, Union
from collections import defaultdict

import numpy as np
import tensorflow as tf
from tensorflow.python.client import timeline
from tensorflow.python import debug as tf_debug

from .config import Config, RemoteConfig, get_config
# from .protocol.pond import PondPublicTensor  # TODO[Morten] can't do this because of circular import, should be fixed

__TFE_STATS__ = bool(os.getenv('TFE_STATS', False))
__TFE_TRACE__ = bool(os.getenv('TFE_TRACE', False))
__TFE_DEBUG__ = bool(os.getenv('TFE_DEBUG', False))
__TENSORBOARD_DIR__ = str(os.getenv('TFE_STATS_DIR', '/tmp/tensorboard'))

_run_counter = defaultdict(int)  # type: Any


class Session(tf.Session):
    """
    Wrap a Tensorflow Session
    """

    def __init__(
        self,
        graph: Optional[tf.Graph]=None,
        config: Optional[Config]=None
    ) -> None:
        if config is None:
            config = get_config()

        target, configProto = config.get_tf_config()

        if isinstance(config, RemoteConfig):
            print("Starting session on target '{}' using config {}".format(target, configProto))
        super(Session, self).__init__(target, graph, configProto)
        # self.sess = tf.Session(target, graph, configProto)

        global __TFE_DEBUG__
        if __TFE_DEBUG__:
            print('Session in debug mode')
            self = tf_debug.LocalCLIDebugWrapperSession(self)

    def sanitize_fetches(self, fetches: Any) -> Union[List[Any], tf.Tensor, tf.Operation]:

        if isinstance(fetches, (list, tuple)):
            return [self.sanitize_fetches(fetch) for fetch in fetches]

        else:
            if isinstance(fetches, (tf.Tensor, tf.Operation)):
                return fetches
            # elif isinstance(fetch, PondPublicTensor):
            else:
                return fetches.prot.decode(fetches)
            # else:
            #     raise TypeError("Don't know how to fetch {}", type(fetches))

    def run(
        self,
        fetches: Any,
        feed_dict: Dict[str, np.ndarray] = {},
        tag: Optional[str] = None,
        write_trace: bool = False
    ) -> Any:

        sanitized_fetches = self.sanitize_fetches(fetches)

        if not __TFE_STATS__ or tag is None:
            fetches_out = super(Session, self).run(
                sanitized_fetches,
                feed_dict=feed_dict
            )
        else:
            session_tag = "{}{}".format(tag, _run_counter[tag])
            run_tag = os.path.join(__TENSORBOARD_DIR__, session_tag)
            _run_counter[tag] += 1

            writer = tf.summary.FileWriter(run_tag, self.graph)
            run_options = tf.RunOptions(trace_level=tf.RunOptions.FULL_TRACE)
            run_metadata = tf.RunMetadata()

            fetches_out = super(Session, self).run(
                sanitized_fetches,
                feed_dict=feed_dict,
                options=run_options,
                run_metadata=run_metadata
            )

            writer.add_run_metadata(run_metadata, session_tag)
            writer.close()

            if __TFE_TRACE__ or write_trace:
                chrome_trace = timeline.Timeline(run_metadata.step_stats).generate_chrome_trace_format()
                with open('{}/{}.ctr'.format(__TENSORBOARD_DIR__, session_tag), 'w') as f:
                    f.write(chrome_trace)

        return fetches_out


def setMonitorStatsFlag(monitor_stats: bool = False) -> None:
    global __TFE_STATS__
    if monitor_stats is True:
        print("Tensorflow encrypted is monitoring statistics for each session.run() call using a tag")

    __TFE_STATS__ = monitor_stats


def setTFEDebugFlag(debug: bool = False) -> None:
    global __TFE_DEBUG__
    if debug is True:
        print("Tensorflow encrypted is running in DEBUG mode")

    __TFE_DEBUG__ = debug