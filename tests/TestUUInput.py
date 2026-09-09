import unittest
from unittest.mock import Mock, patch


class TestUUPynputInput(unittest.TestCase):
    def test_real_framework_backend_converts_coordinates_and_uses_pynput(self):
        from src.uu_input import click_uu
        from pynput.mouse import Button

        mouse = Mock()
        with patch('src.uu_input.is_window_focused', return_value=True), \
                patch('src.uu_input.win32gui.GetWindowRect', return_value=(200, 100, 1200, 788)), \
                patch('ok.device.interaction_methods.pynput.is_admin', return_value=True), \
                patch('ok.device.interaction_methods.pynput.time.sleep'), \
                patch('pynput.mouse.Controller', return_value=mouse), \
                patch('win32api.mouse_event') as native_click:
            click_uu(10, (200, 100, 1200, 788), (617, 254))
        self.assertEqual((817, 354), mouse.position)
        mouse.press.assert_called_once_with(Button.left)
        mouse.release.assert_called_once_with(Button.left)
        native_click.assert_not_called()


if __name__ == '__main__':
    unittest.main()
