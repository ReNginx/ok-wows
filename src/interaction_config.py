"""所有游戏任务共用的操作等待设置。"""

import math

from ok import ConfigOption
from ok.util.GlobalConfig import create_basic_options


BUTTON_WAIT = "Button Wait (Seconds)"
DEFAULT_BUTTON_WAIT = 3.0

# 在框架注册基础选项之前提供项目默认值，保留用户已保存的配置。
basic_options = create_basic_options()
basic_options.default_config["Trigger Interval"] = 100


def validate_interaction_config(key, value):  # 全局配置校验返回框架要求的结果和提示。
    if key == BUTTON_WAIT and (not isinstance(value, (int, float)) or isinstance(value, bool)
                              or not math.isfinite(value) or value < 0):
        return False, "Button wait must be a finite number greater than or equal to 0."
    return True, None


interaction_options = ConfigOption(
    "Game Interaction",
    {BUTTON_WAIT: DEFAULT_BUTTON_WAIT},
    description="Shared input settings for all game tasks.",
    config_description={
        BUTTON_WAIT: "Minimum seconds to wait after menu clicks or key presses. Battle controls keep their original timing. Longer existing waits are preserved; 0 keeps only the original waits.",
    },
    validator=validate_interaction_config,
)
