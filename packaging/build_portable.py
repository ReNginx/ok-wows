"""Build a local Windows bundle using the verified repository virtual environment."""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def build():
    if Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
        raise RuntimeError('请使用 .venv/Scripts/python.exe 运行此脚本。')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    bundle = ROOT / 'dist' / ('ok-wows-portable-' + stamp)
    bundle.mkdir(parents=True, exist_ok=False)
    runtime = bundle / 'runtime'
    runtime.mkdir()
    base = Path(sys.base_prefix)
    ignore = shutil.ignore_patterns('__pycache__', '*.pyc', '.git', '*.log')
    for path in base.iterdir():
        if path.is_file() and path.suffix.lower() in {'.exe', '.dll', '.txt'}:
            shutil.copy2(path, runtime / path.name)
    for folder in ('DLLs', 'Lib'):
        shutil.copytree(base / folder, runtime / folder,
                        ignore=shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc'))
    shutil.copytree(Path(sys.prefix) / 'Lib/site-packages', runtime / 'Lib/site-packages', ignore=ignore)
    for folder in ('src', 'assets', 'icons', 'i18n'):
        shutil.copytree(ROOT / folder, bundle / folder, ignore=ignore)
    for filename in ('main.py', 'requirements.txt', 'pyproject.toml'):
        shutil.copy2(ROOT / filename, bundle / filename)
    # Use the public app identity without changing the developer checkout's settings.
    config_file = bundle / 'src/config.py'
    config_text = config_file.read_text(encoding='utf-8')
    config_text = config_text.replace("'gui_title': 'ok-script-app'", "'gui_title': 'ok-wows'")
    config_file.write_text(config_text, encoding='utf-8')
    compiler = Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe'
    subprocess.run([str(compiler), '/nologo', '/target:winexe', '/platform:x64',
                    '/reference:System.Windows.Forms.dll',
                    '/win32manifest:' + str(ROOT / 'packaging/launcher.manifest'),
                    '/win32icon:' + str(ROOT / 'icons/icon.ico'),
                    '/out:' + str(bundle / 'ok-wows.exe'), str(ROOT / 'packaging/Launcher.cs')], check=True)
    (bundle / '使用说明.txt').write_text(
        '完整解压后双击 ok-wows.exe，并允许管理员权限提示。无需安装 Python。\n'
        '不要单独移动 exe，runtime、src、assets 等文件夹需保留在旁边。\n'
        '打开应用不会启动游戏；启动任务后先开启 UU 加速，再启动游戏。\n'
        '首次使用请设置游戏和 UU 路径，个人配置与日志保存在本便携包目录内。\n'
        '计划任务：在侧边栏创建计划，执行前退出当前程序，保持电脑开机且桌面解锁。\n'
        '移动便携包后请重新创建计划；计划使用随包携带的 Python 环境。\n'
        '本包不包含开发机个人配置、日志或账户数据，也不启用模板项目更新器。\n', encoding='utf-8-sig')
    manifest = {'built_at': stamp, 'python': sys.version, 'files': {}}
    for file in bundle.rglob('*'):
        if file.is_file():
            manifest['files'][file.relative_to(bundle).as_posix()] = hashlib.file_digest(file.open('rb'), 'sha256').hexdigest()
    (bundle / 'build-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    env = {key: value for key, value in os.environ.items() if key not in ('PYTHONHOME', 'PYTHONPATH')}
    env['PYTHONNOUSERSITE'] = '1'
    smoke = (
        "import sys; from pathlib import Path; import cv2,win32gui,win32security,openvino; "
        "from PySide6.QtWidgets import QApplication; from src.config import config; "
        "from src.globals import Globals; from src.uu_input import click_uu; "
        "from src.uu_annotations import default_annotations; default_annotations(); "
        "assert config['gui_title']=='ok-wows'; "
        "assert Path(sys.prefix).resolve()==Path('runtime').resolve(); "
        "print('Portable runtime imports and UU annotations OK:',sys.executable)"
    )
    subprocess.run([str(runtime / 'python.exe'), '-c', smoke], cwd=bundle, env=env, check=True)
    archive = bundle.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in bundle.rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts:
                output.write(file, file.relative_to(bundle.parent))
    print(json.dumps({'folder': str(bundle), 'exe': str(bundle / 'ok-wows.exe'),
                      'zip': str(archive), 'bytes': archive.stat().st_size}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    build()
