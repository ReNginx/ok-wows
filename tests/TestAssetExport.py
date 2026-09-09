import importlib
import inspect
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import cv2
import numpy as np

import src.resolution_assets  # Install the same export entry point used by the dev UI.
from src.asset_export import export_assets


feature_module = importlib.import_module("ok.feature.FeatureSet")
compress = inspect.unwrap(feature_module.compress_copy_coco)


class TestAssetExport(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "templates"
        self.source.mkdir()
        self.target = self.root / "assets"
        self.coco = self.source / "coco_annotations.json"
        self.data = {"images": [], "annotations": [], "categories": []}
        for i in range(3):
            # Overlapping boxes force three packed pages, as in the real resource pack.
            cv2.imwrite(str(self.source / f"{i}.png"), np.full((24, 32, 3), 40 + i * 50, np.uint8))
            self.data["images"].append({"id": i, "file_name": f"{i}.png", "width": 32, "height": 24})
            self.data["annotations"].append({"id": i, "image_id": i, "category_id": i,
                                              "bbox": [4, 5, 8, 9], "area": 72, "iscrowd": 0})
            self.data["categories"].append({"id": i, "name": f"Feature-{i}", "supercategory": ""})
        self.coco.write_text(json.dumps(self.data), encoding="utf-8")

    def save(self, compressor=compress):
        return Path(export_assets(self.coco, self.target, self.source, compressor))

    def snapshot(self):
        return {path.relative_to(self.target).as_posix(): path.read_bytes()
                for path in self.target.rglob("*") if path.is_file()}

    def assert_previous_unchanged(self, before):
        for name, content in before.items():
            self.assertEqual(content, (self.target / name).read_bytes(), name)

    def assert_crops_match(self, destination):
        data = json.loads(destination.read_text(encoding="utf-8"))
        images = {image["id"]: image for image in data["images"]}
        for ann in data["annotations"]:
            image = images[ann["image_id"]]
            actual = cv2.imread(str(destination.parent / image["file_name"]))
            source = cv2.imread(str(self.source / f'{image["id"]}.png'))
            x, y, w, h = ann["bbox"]
            np.testing.assert_array_equal(actual[y:y+h, x:x+w], source[y:y+h, x:x+w])
        self.assertEqual(self.data["categories"], data["categories"])

    def lock_file(self, path):
        import win32con
        import win32file

        return win32file.CreateFile(str(path), win32con.GENERIC_READ, win32con.FILE_SHARE_READ,
                                    None, win32con.OPEN_EXISTING, 0, None)

    def test_export_preserves_annotations_and_repeated_save_reuses_images(self):
        source_before = self.coco.read_bytes()
        destination = self.save()
        self.assert_crops_match(destination)
        before = self.snapshot()
        self.save()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(source_before, self.coco.read_bytes())

    @unittest.skipUnless(os.name == "nt", "Requires Windows file sharing semantics")
    def test_original_export_reproduces_winerror_32_on_2_png(self):
        original_save = feature_module.save_image_with_metadata
        handles = []

        def lock_before_replace(image, image_path, new_path):
            result = original_save(image, image_path, new_path)
            if Path(new_path).name == "temp_packed_2.png":
                handles.append(self.lock_file(Path(new_path).parent / "2.png"))
            return result

        try:
            with patch.object(feature_module, "save_image_with_metadata", side_effect=lock_before_replace):
                with self.assertRaises(PermissionError) as raised:
                    compress(str(self.coco), str(self.target), str(self.source))
            self.assertEqual(32, raised.exception.winerror)
            self.assertEqual("2.png", Path(raised.exception.filename).name)
            self.assertTrue((self.target / "images/temp_packed_2.png").exists())
            # The index was already published even though the third page is still a source image.
            self.assertTrue((self.target / "coco_annotations.json").exists())
            self.assertEqual(140, int(cv2.imread(str(self.target / "images/2.png"))[0, 0, 0]))
        finally:
            for handle in handles:
                handle.Close()

    @unittest.skipUnless(os.name == "nt", "Requires Windows file sharing semantics")
    def test_save_succeeds_with_old_2_png_locked(self):
        compress(str(self.coco), str(self.target), str(self.source))
        before = self.snapshot()
        handle = self.lock_file(self.target / "images/2.png")
        try:
            cv2.imwrite(str(self.source / "2.png"), np.full((24, 32, 3), 210, np.uint8))
            destination = self.save()
            self.assert_crops_match(destination)
            self.assertEqual(before["images/2.png"], (self.target / "images/2.png").read_bytes())
        finally:
            handle.Close()

    @unittest.skipUnless(os.name == "nt", "Requires Windows file sharing semantics")
    def test_locked_index_leaves_previous_pack_intact(self):
        destination = self.save()
        before = self.snapshot()
        handle = self.lock_file(destination)
        try:
            cv2.imwrite(str(self.source / "2.png"), np.full((24, 32, 3), 210, np.uint8))
            with self.assertRaises(PermissionError):
                self.save()
            self.assert_previous_unchanged(before)
        finally:
            handle.Close()

    def test_compressor_failure_leaves_previous_pack_intact(self):
        self.save()
        before = self.snapshot()

        def fail(coco, target, images, enum):
            compress(coco, target, images, enum)
            raise RuntimeError("Interrupted compression")

        with self.assertRaisesRegex(RuntimeError, "Interrupted compression"):
            self.save(fail)
        self.assertEqual(before, self.snapshot())

    def test_transient_sharing_error_retries_private_export(self):
        def export_on_second_attempt(*args):
            if failing.call_count == 1:
                raise PermissionError("Transient file lock")
            return compress(*args)

        failing = MagicMock(side_effect=export_on_second_attempt)
        self.assert_crops_match(self.save(failing))
        self.assertEqual(2, failing.call_count)

    def test_missing_source_does_not_publish_incomplete_pack(self):
        self.save()
        before = self.snapshot()
        (self.source / "2.png").unlink()
        with self.assertRaises(FileNotFoundError):
            self.save()
        self.assertEqual(before, self.snapshot())

    def test_dev_save_button_calls_safe_export_and_reloads_features(self):
        template_tab = importlib.import_module("ok.ui.qt.tasks.TemplateTab")
        tab = SimpleNamespace(window=MagicMock(), tr=lambda text: text, template_tab_config={})
        executor = SimpleNamespace(feature_set=MagicMock())
        radio_tasks, radio_assets = MagicMock(), MagicMock()
        radio_tasks.isChecked.return_value = False
        checkbox = MagicMock()
        checkbox.isChecked.return_value = False
        with patch.object(template_tab, "get_coco_path", return_value=str(self.coco)), \
                patch.object(template_tab, "ensure_template_folder", return_value=str(self.source)), \
                patch.object(template_tab, "og", SimpleNamespace(app=SimpleNamespace(debug=True), executor=executor)), \
                patch("qfluentwidgets.MessageBoxBase"), patch("qfluentwidgets.SubtitleLabel"), \
                patch("qfluentwidgets.RadioButton", side_effect=[radio_tasks, radio_assets]), \
                patch("qfluentwidgets.CheckBox", return_value=checkbox), patch("qfluentwidgets.LineEdit"), \
                patch("PySide6.QtWidgets.QButtonGroup"), patch.object(template_tab, "BodyLabel"), \
                patch("src.resolution_assets.redirect_asset_target", return_value=str(self.target)) as redirect, \
                patch("ok.ui.qt.util.Alert.alert_info") as success, \
                patch("ok.ui.qt.util.Alert.alert_error") as error:
            template_tab.TemplateTab.save_compressed(tab)
        redirect.assert_called_once()
        self.assertEqual(Path.cwd() / "assets", Path(redirect.call_args.args[0]))
        success.assert_called_once()
        error.assert_not_called()
        executor.feature_set.process_data.assert_called_once()
        self.assert_crops_match(self.target / self.coco.name)


if __name__ == "__main__":
    unittest.main()
