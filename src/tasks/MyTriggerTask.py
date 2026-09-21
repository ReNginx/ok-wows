from ok import TriggerTask
from src.tasks.MyBaseTask import MyBaseTask


class MyTriggerTask(TriggerTask, MyBaseTask):  # 后台任务也共用全局游戏操作等待。

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "触发器会不断调用run方法"
        self.description = "一般根据frame来判断是否需要运行"
        self.trigger_count = 0

    def run(self):
        self.trigger_count += 1
        self.log_debug(f'MyTriggerTask run {self.trigger_count}')



