import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET

from ok.util.windows_schedule import TriggerType, WindowsScheduleManager
from src.config import config
from src.tasks.AutoPveBattleTask import AutoPveBattleTask
from src.tasks.ScreenRecognitionTestTask import ScreenRecognitionTestTask


class TestTaskSchedule(unittest.TestCase):
    def test_battle_is_available_to_schedule_but_diagnostic_is_not(self):
        executor = Mock(scene=None)
        self.assertTrue(AutoPveBattleTask(executor, None).support_schedule_task)
        self.assertFalse(ScreenRecognitionTestTask(executor, None).support_schedule_task)
        self.assertNotIn(['src.tasks.UUStartupTestTask', 'UUStartupTestTask'], config['onetime_tasks'])

    def test_schedule_launches_registered_battle_through_normal_entrypoint(self):
        manager = object.__new__(WindowsScheduleManager)
        index = config['onetime_tasks'].index(['src.tasks.AutoPveBattleTask', 'AutoPveBattleTask']) + 1
        with patch.object(manager, '_resolve_current_user_id', return_value='TestUser'):
            xml = manager._generate_task_xml('Battle', index, TriggerType.DAILY,
                                            timeout_hours=0, start_hour=9, start_minute=30, auto_exit=True)
        root = ET.fromstring(xml)
        namespace = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
        self.assertEqual(f'main.py -t {index} -e', root.findtext('.//t:Arguments', namespaces=namespace))
        self.assertEqual('HighestAvailable', root.findtext('.//t:RunLevel', namespaces=namespace))
        self.assertEqual('InteractiveToken', root.findtext('.//t:LogonType', namespaces=namespace))
        self.assertTrue(root.findtext('.//t:StartBoundary', namespaces=namespace).endswith('T09:30:00'))


if __name__ == '__main__':
    unittest.main()
